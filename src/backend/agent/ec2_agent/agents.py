"""
Specialized sub-agents.

Each agent consumes (TelemetryBundle, signals) and emits Recommendations.
The first four agents are deterministic — they map signals to
recommendation templates with concrete evidence and savings calc. The
fifth agent (Root Cause) is LLM-based and only runs if there's enough
material for a meaningful timeline.

Architectural choice: the deterministic agents share an internal helper
`_build_rec(...)` that enforces the safety contract (every recommendation
MUST have evidence, confidence, severity, blast_radius, rollback). This
is the guardrail that prevents generic / unsafe output.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from agent.ec2_agent.types import (
    RecCategory,
    RecType,
    Recommendation,
    Severity,
    Signal,
    TelemetryBundle,
)
from agent.ec2_agent.signals import signals_by_name

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper for deterministic agents
# ---------------------------------------------------------------------------

def _build_rec(
    *,
    rule_id: str,
    title: str,
    rec_type: RecType,
    severity: Severity,
    category: RecCategory,
    confidence: float,
    description: str,
    issue: str,
    reasoning: str,
    supporting_signals: List[Signal],
    impact: str = "medium",
    blast_radius: str = "instance",
    operational_risk: str = "low",
    rollback: str = "",
    estimated_savings: Any = "N/A",
    cost_basis: str = "",
    solution_steps: Optional[List[Dict[str, Any]]] = None,
    boto3_sequence: Optional[List[Dict[str, Any]]] = None,
    manual_only: bool = False,
) -> Recommendation:
    """
    Single chokepoint that enforces the safety contract.
    """
    evidence = {}
    for s in supporting_signals:
        evidence[s.name] = s.evidence
    return Recommendation(
        rule_id=rule_id,
        title=title,
        type=rec_type,
        category=category,
        severity=severity,
        confidence=round(confidence, 2),
        description=description,
        issue=issue,
        reasoning=reasoning,
        evidence=evidence,
        supporting_signals=[s.name for s in supporting_signals],
        impact=impact,
        blast_radius=blast_radius,
        operational_risk=operational_risk,
        rollback=rollback,
        estimated_savings=estimated_savings,
        cost_basis=cost_basis,
        solution_steps=solution_steps or [],
        boto3_sequence=boto3_sequence or [],
        manual_only=manual_only,
    )


# ---------------------------------------------------------------------------
# Metric Analyzer Agent
# ---------------------------------------------------------------------------

def metric_analyzer_agent(bundle: TelemetryBundle, signals: List[Signal]) -> List[Recommendation]:
    """
    Threshold + trend + anomaly observations. Surfaces *findings*; the
    cost/reliability agents convert them into actionable changes when
    appropriate. This agent only emits *informational* findings unless the
    signal severity is critical.
    """
    by = signals_by_name(signals)
    out: List[Recommendation] = []

    if "cpu_sustained_high" in by:
        s = by["cpu_sustained_high"]
        out.append(_build_rec(
            rule_id="ec2.metric.cpu_sustained_high",
            title="Sustained High CPU Detected",
            rec_type=RecType.PERFORMANCE,
            severity=s.severity,
            category=RecCategory.WARNING,
            confidence=s.confidence,
            description=(
                "Average CPU has been high across the observed window. Sustained "
                "saturation degrades user-facing latency and risks request timeouts."
            ),
            issue=s.description,
            reasoning="Threshold rule + sustained-trend check.",
            supporting_signals=[s],
            impact="high",
            blast_radius="service",
            operational_risk="medium",
        ))

    if "memory_pressure_detected" in by or "swap_exhaustion" in by or "oom_killed" in by:
        crit = "oom_killed" in by
        sigs = [by[n] for n in ("memory_pressure_detected", "swap_exhaustion", "oom_killed") if n in by]
        out.append(_build_rec(
            rule_id="ec2.metric.memory_pressure",
            title="Memory Pressure / OOM Risk",
            rec_type=RecType.RELIABILITY,
            severity=Severity.CRITICAL if crit else Severity.HIGH,
            category=RecCategory.CRITICAL if crit else RecCategory.WARNING,
            confidence=max(s.confidence for s in sigs),
            description=(
                "Memory pressure detected. OOM kills cause hard process restarts; "
                "swap exhaustion cascades into latency. Investigate per-process "
                "memory before scaling up the instance."
            ),
            issue="; ".join(s.description for s in sigs),
            reasoning="Memory + swap thresholds + OOM log signal.",
            supporting_signals=sigs,
            impact="high",
            blast_radius="service",
            operational_risk="medium",
        ))

    if "ebs_burst_balance_low" in by:
        s = by["ebs_burst_balance_low"]
        out.append(_build_rec(
            rule_id="ec2.metric.ebs_burst_low",
            title="EBS Burst Balance Depleted",
            rec_type=RecType.PERFORMANCE,
            severity=Severity.MEDIUM,
            category=RecCategory.WARNING,
            confidence=s.confidence,
            description=(
                "EBS burst balance dipped low — gp2 volumes throttle hard once "
                "credits drain. Consider migrating to gp3 (no burst behavior) or "
                "increasing volume size to raise baseline IOPS."
            ),
            issue=s.description,
            reasoning="Direct CloudWatch BurstBalance signal.",
            supporting_signals=[s],
            impact="medium",
            blast_radius="instance",
            operational_risk="low",
        ))

    if "network_saturation_detected" in by:
        s = by["network_saturation_detected"]
        out.append(_build_rec(
            rule_id="ec2.metric.network_saturation",
            title="Network Bandwidth Saturation",
            rec_type=RecType.PERFORMANCE,
            severity=Severity.WARNING,
            category=RecCategory.WARNING,
            confidence=s.confidence,
            description=(
                "Peak network throughput approaches the instance class's limit. "
                "Larger instance types or ENA-enabled families have higher caps."
            ),
            issue=s.description,
            reasoning="Network throughput peak vs instance-class baseline.",
            supporting_signals=[s],
            impact="medium",
            blast_radius="service",
            operational_risk="low",
        ))

    return out


# ---------------------------------------------------------------------------
# Cost Optimization Agent
# ---------------------------------------------------------------------------

def cost_optimization_agent(bundle: TelemetryBundle, signals: List[Signal]) -> List[Recommendation]:
    by = signals_by_name(signals)
    out: List[Recommendation] = []
    instance_id = bundle.instance_id

    # Idle → stop. High-confidence cost win when corroborated.
    if "instance_idle_high_cost" in by or "cpu_sustained_low" in by:
        sigs = [by[n] for n in ("instance_idle_high_cost", "cpu_sustained_low") if n in by]
        # Boost confidence when both fire
        conf = min(1.0, max(s.confidence for s in sigs) + (0.1 if len(sigs) > 1 else 0))
        out.append(_build_rec(
            rule_id="ec2.cost.idle_stop",
            title="Idle Instance — Stop or Schedule",
            rec_type=RecType.COST,
            severity=Severity.HIGH,
            category=RecCategory.OPTIMIZATION,
            confidence=conf,
            description=(
                "This instance shows sustained idle behavior across CPU. Stopping "
                "(or scheduling start/stop windows) eliminates compute cost; "
                "running EBS still incurs storage cost."
            ),
            issue="Idle EC2 with non-zero monthly cost.",
            reasoning=(
                "CPU sustained-low signal + monthly cost > 0. Cross-checked "
                "against autoscaling attachment to avoid stopping ASG members."
            ),
            supporting_signals=sigs,
            impact="medium",
            blast_radius="instance",
            operational_risk="medium",
            rollback="aws ec2 start-instances --instance-ids <id>",
            estimated_savings=round(bundle.monthly_cost, 2),
            cost_basis="100% of monthly compute cost (storage continues).",
            solution_steps=[{
                "step": 1,
                "command": f"aws ec2 stop-instances --instance-ids {instance_id}",
                "description": "Stop the instance to eliminate compute cost.",
            }],
            boto3_sequence=[{
                "service": "ec2",
                "operation": "stop_instances",
                "params": {"InstanceIds": [instance_id]},
            }],
        ))

    # Bursty → ASG (manual_only because ASG params can't be inferred safely)
    if "cpu_bursty" in by:
        s = by["cpu_bursty"]
        out.append(_build_rec(
            rule_id="ec2.cost.bursty_to_asg",
            title="Bursty Workload — Move to Auto Scaling",
            rec_type=RecType.COST,
            severity=Severity.MEDIUM,
            category=RecCategory.OPTIMIZATION,
            confidence=s.confidence,
            description=(
                "Average usage is low but peaks are high. A right-sized base "
                "instance + ASG that handles peaks is cheaper than provisioning "
                "for the worst case."
            ),
            issue=s.description,
            reasoning="Spread (max - avg) above bursty threshold.",
            supporting_signals=[s],
            impact="medium",
            blast_radius="service",
            operational_risk="medium",
            rollback="Detach ASG; revert to fixed instance.",
            estimated_savings=round(bundle.monthly_cost * 0.3, 2),
            cost_basis="Approx 30% — depends on peak duration; verify with usage shape.",
            manual_only=True,  # ASG creation needs human input
            solution_steps=[{
                "step": 1,
                "command": "Configure Auto Scaling Group manually with min=1 max=N",
                "description": "Cannot be safely auto-applied — needs launch template + scaling policy.",
            }],
        ))

    # Graviton candidate
    if "graviton_migration_candidate" in by:
        s = by["graviton_migration_candidate"]
        out.append(_build_rec(
            rule_id="ec2.cost.graviton_migration",
            title="Graviton Migration Opportunity",
            rec_type=RecType.COST,
            severity=Severity.LOW,
            category=RecCategory.OPTIMIZATION,
            confidence=s.confidence,
            description=(
                "Running on x86. Graviton (ARM) instances are typically ~20% "
                "cheaper at equivalent performance. Verify workload compatibility "
                "(native binaries, JIT runtimes, container base images)."
            ),
            issue=s.description,
            reasoning="x86 family + monthly_cost > $50.",
            supporting_signals=[s],
            impact="low",
            blast_radius="service",
            operational_risk="medium",
            rollback="Switch back to x86 instance type.",
            estimated_savings=round(bundle.monthly_cost * 0.20, 2),
            cost_basis="~20% list price difference vs equivalent x86.",
            manual_only=True,  # arch migration is not a one-API-call change
        ))

    # Spot candidate
    if "spot_candidate" in by:
        s = by["spot_candidate"]
        out.append(_build_rec(
            rule_id="ec2.cost.spot_candidate",
            title="Move Non-Production Workload to Spot",
            rec_type=RecType.COST,
            severity=Severity.LOW,
            category=RecCategory.OPTIMIZATION,
            confidence=s.confidence,
            description=(
                "Tagged as non-production. Spot instances can be interrupted with "
                "2-min notice but cost up to 70% less. Safe for dev/test/CI."
            ),
            issue=s.description,
            reasoning="Environment tag + on-demand status.",
            supporting_signals=[s],
            impact="low",
            blast_radius="instance",
            operational_risk="low",
            rollback="Re-launch as on-demand.",
            estimated_savings=round(bundle.monthly_cost * 0.6, 2),
            cost_basis="Conservative 60% (real spot discount varies 50-90%).",
            manual_only=True,
        ))

    return out


# ---------------------------------------------------------------------------
# Reliability Agent
# ---------------------------------------------------------------------------

def reliability_agent(bundle: TelemetryBundle, signals: List[Signal]) -> List[Recommendation]:
    by = signals_by_name(signals)
    out: List[Recommendation] = []
    instance_id = bundle.instance_id

    if "status_check_failures" in by or "reboot_loop_detected" in by:
        sigs = [by[n] for n in ("status_check_failures", "reboot_loop_detected") if n in by]
        out.append(_build_rec(
            rule_id="ec2.reliability.health_failures",
            title="Instance Health Degraded — Reboot Recommended",
            rec_type=RecType.RELIABILITY,
            severity=Severity.CRITICAL,
            category=RecCategory.CRITICAL,
            confidence=max(s.confidence for s in sigs),
            description=(
                "EC2 status checks are failing or instance is in a reboot loop. "
                "Reboot resolves transient hypervisor/hardware issues; if it "
                "persists, replace via stop/start (moves to new hardware)."
            ),
            issue="; ".join(s.description for s in sigs),
            reasoning="StatusCheckFailed metric + reboot count.",
            supporting_signals=sigs,
            impact="high",
            blast_radius="instance",
            operational_risk="medium",
            rollback="If reboot worsens, restore from snapshot.",
            solution_steps=[{
                "step": 1,
                "command": f"aws ec2 reboot-instances --instance-ids {instance_id}",
                "description": "Reboot to recover from transient health failures.",
            }],
            boto3_sequence=[{
                "service": "ec2",
                "operation": "reboot_instances",
                "params": {"InstanceIds": [instance_id]},
            }],
        ))

    if "no_autoscaling" in by:
        s = by["no_autoscaling"]
        out.append(_build_rec(
            rule_id="ec2.reliability.no_asg",
            title="Single Instance — No Auto Scaling Group",
            rec_type=RecType.RELIABILITY,
            severity=Severity.MEDIUM,
            category=RecCategory.WARNING,
            confidence=s.confidence,
            description=(
                "Workload runs on a single instance. Hardware failure = full "
                "outage. ASG with min=1 ensures replacement on instance death; "
                "min=2+ across AZs ensures continuous availability."
            ),
            issue=s.description,
            reasoning="No ASG attachment detected.",
            supporting_signals=[s],
            impact="high",
            blast_radius="service",
            operational_risk="medium",
            rollback="Disassociate ASG; revert to standalone.",
            manual_only=True,
        ))

    if "single_az_deployment" in by:
        s = by["single_az_deployment"]
        out.append(_build_rec(
            rule_id="ec2.reliability.single_az",
            title="Single-AZ Deployment — AZ Failure Risk",
            rec_type=RecType.RELIABILITY,
            severity=Severity.HIGH,
            category=RecCategory.WARNING,
            confidence=s.confidence,
            description=(
                "ASG runs in only one Availability Zone. AZ outages happen "
                "(rare but real); spreading across ≥2 AZs eliminates that "
                "blast radius for free."
            ),
            issue=s.description,
            reasoning="ASG az_count < 2.",
            supporting_signals=[s],
            impact="high",
            blast_radius="account",
            operational_risk="low",
            rollback="Set ASG VPCZoneIdentifier back to single subnet.",
            manual_only=True,
        ))

    return out


# ---------------------------------------------------------------------------
# Security + Compliance Agent
# ---------------------------------------------------------------------------

def security_agent(bundle: TelemetryBundle, signals: List[Signal]) -> List[Recommendation]:
    by = signals_by_name(signals)
    out: List[Recommendation] = []
    instance_id = bundle.instance_id

    if "imdsv1_in_use" in by:
        s = by["imdsv1_in_use"]
        out.append(_build_rec(
            rule_id="ec2.security.imdsv2_required",
            title="Enforce IMDSv2 (Disable IMDSv1)",
            rec_type=RecType.SECURITY,
            severity=Severity.HIGH,
            category=RecCategory.WARNING,
            confidence=s.confidence,
            description=(
                "IMDSv1 is vulnerable to SSRF-based credential theft (Capital "
                "One breach pattern). IMDSv2 requires session tokens which "
                "neutralize that attack class."
            ),
            issue=s.description,
            reasoning="HttpTokens != 'required' in instance metadata options.",
            supporting_signals=[s],
            impact="high",
            blast_radius="account",
            operational_risk="medium",
            rollback="Set HttpTokens back to optional.",
            solution_steps=[{
                "step": 1,
                "command": (
                    f"aws ec2 modify-instance-metadata-options --instance-id {instance_id} "
                    "--http-tokens required --http-endpoint enabled"
                ),
                "description": "Require IMDSv2 session tokens for metadata calls.",
            }],
            boto3_sequence=[{
                "service": "ec2",
                "operation": "modify_instance_metadata_options",
                "params": {
                    "InstanceId": instance_id,
                    "HttpTokens": "required",
                    "HttpEndpoint": "enabled",
                },
            }],
        ))

    if "ebs_unencrypted" in by:
        s = by["ebs_unencrypted"]
        out.append(_build_rec(
            rule_id="ec2.security.ebs_unencrypted",
            title="Encrypt EBS Volumes",
            rec_type=RecType.SECURITY,
            severity=Severity.HIGH,
            category=RecCategory.WARNING,
            confidence=s.confidence,
            description=(
                "Volumes are not encrypted at rest. SOC2 / HIPAA / PCI-DSS "
                "all require encryption. Migration is not in-place — snapshot, "
                "create encrypted volume from snapshot, swap."
            ),
            issue=s.description,
            reasoning="EBS volume Encrypted attribute is False.",
            supporting_signals=[s],
            impact="high",
            blast_radius="account",
            operational_risk="medium",
            rollback="Re-attach original unencrypted volume.",
            manual_only=True,
        ))

    if "ssh_rdp_open_to_world" in by:
        s = by["ssh_rdp_open_to_world"]
        out.append(_build_rec(
            rule_id="ec2.security.ssh_open",
            title="Restrict Admin Ports From Internet",
            rec_type=RecType.SECURITY,
            severity=Severity.CRITICAL,
            category=RecCategory.CRITICAL,
            confidence=s.confidence,
            description=(
                "Admin ports (SSH/RDP) are exposed to 0.0.0.0/0. Replace with "
                "Session Manager (no inbound port at all) or restrict to office VPN CIDR."
            ),
            issue=s.description,
            reasoning="Security group ingress 0.0.0.0/0 on port 22 or 3389.",
            supporting_signals=[s],
            impact="high",
            blast_radius="account",
            operational_risk="low",
            rollback="Re-add ingress rule.",
            manual_only=True,
        ))

    if "ami_outdated" in by:
        s = by["ami_outdated"]
        out.append(_build_rec(
            rule_id="ec2.security.ami_outdated",
            title="AMI Older Than 1 Year — Security Patches Pending",
            rec_type=RecType.SECURITY,
            severity=Severity.MEDIUM,
            category=RecCategory.WARNING,
            confidence=s.confidence,
            description=(
                "AMI hasn't been refreshed in over a year. Likely missing kernel "
                "and OS-level security patches. Build a fresh AMI from the "
                "current base image and rotate the ASG launch template."
            ),
            issue=s.description,
            reasoning="AMI creation date older than 365 days.",
            supporting_signals=[s],
            impact="medium",
            blast_radius="service",
            operational_risk="medium",
            rollback="Pin previous AMI ID in launch template.",
            manual_only=True,
        ))

    return out


# ---------------------------------------------------------------------------
# Root Cause Correlation Agent (LLM)
# ---------------------------------------------------------------------------

def root_cause_agent(
    bundle: TelemetryBundle,
    signals: List[Signal]
) -> List[Recommendation]:

    """
    LLM-powered root-cause correlation engine.

    Purpose:
        Build a concise operational narrative
        across:
            - extracted signals
            - deployments
            - scaling events
            - restarts
            - failures

    Output format intentionally mirrors
    the legacy recommendation shape used
    by the frontend.
    """

    #
    # Need enough evidence
    #
    if len(signals) < 2 or not bundle.events:
        return []

    #
    # Compact signal summary
    # NEVER dump raw telemetry
    #
    signal_summary = [

        {
            "name":
                s.name,

            "severity":
                s.severity.value,

            "confidence":
                s.confidence,

            "description":
                s.description,

            "evidence":
                s.evidence,
        }

        for s in signals
    ]

    #
    # Most recent operational events
    #
    event_summary = bundle.events[-10:]

    #
    # Prompt
    #
    prompt = (

        "You are a senior Site Reliability Engineer "
        "performing production root-cause analysis.\n\n"

        "You are given:\n"

        "1. Signals already extracted from telemetry\n"

        "2. Operational events "
        "(deployments, scaling, restarts, incidents)\n\n"

        "Your job:\n"

        "- infer the MOST likely causal chain\n"

        "- build a SHORT operational timeline\n"

        "- suggest next remediation actions\n\n"

        "IMPORTANT:\n"

        "- Return STRICT JSON only\n"

        "- No markdown\n"

        "- No explanations outside JSON\n\n"

        f"SIGNALS:\n"
        f"{json.dumps(signal_summary, default=str)}\n\n"

        f"EVENTS:\n"
        f"{json.dumps(event_summary, default=str)}\n\n"

        "Return JSON in EXACTLY this shape:\n\n"

        "{\n"

        '  "title": "...",\n'

        '  "description": "...",\n'

        '  "issue": "...",\n'

        '  "severity": "critical|high|medium|low",\n'

        '  "confidence": 0.0,\n'

        '  "timeline": [\n'
        '       "14:02 deployment started",\n'
        '       "14:06 latency increased",\n'
        '       "14:10 instance restarted"\n'
        "  ],\n"

        '  "impact": "low|medium|high",\n'

        '  "blast_radius": "instance|service|cluster",\n'

        '  "operational_risk": "low|medium|high",\n'

        '  "next_actions": [\n'
        '       "Rollback latest deployment",\n'
        '       "Increase instance capacity"\n'
        "  ]\n"

        "}\n\n"

        "If insufficient evidence exists return:\n"

        '{"timeline": []}'
    )

    #
    # LLM call
    #
    try:

        from agent.llm.llm_client import (
            get_llm_client
        )

        text = (
            get_llm_client()
            .generate(prompt)
            or ""
        )

    except Exception as e:

        logger.warning(
            "Root-cause LLM call failed: %s",
            e,
        )

        return []

    #
    # Tolerant JSON extraction
    #
    import re

    fenced = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```",
        text,
        re.DOTALL,
    )

    if fenced:

        text = fenced.group(1)

    else:

        start = text.find("{")
        end = text.rfind("}")

        if start >= 0 and end > start:
            text = text[start:end + 1]

    #
    # Parse JSON
    #
    try:

        parsed = json.loads(text)

    except Exception:

        logger.warning(
            "Failed to parse root-cause JSON"
        )

        return []

    #
    # No confident timeline
    #
    if not parsed.get("timeline"):
        return []

    #
    # Severity mapping
    #
    sev = {

        "critical":
            Severity.CRITICAL,

        "high":
            Severity.HIGH,

        "medium":
            Severity.MEDIUM,

        "low":
            Severity.LOW,

    }.get(

        (
            parsed.get("severity")
            or "medium"
        ).lower(),

        Severity.MEDIUM,
    )

    #
    # Build frontend-compatible recommendation
    #
    return [

        {
            "title":
                parsed.get("title")
                or "Correlated Root Cause Analysis",

            "description":
                parsed.get("description")
                or "AI-correlated operational incident timeline.",

            "type":
                "operational",

            "severity":
                sev.value,

            "saving":
                "N/A",

            "issue":
                parsed.get("issue")
                or parsed.get("description")
                or "Operational incident detected.",

            "impact":
                parsed.get("impact")
                or "high",

            "status":
                "active",

            #
            # New SRE metadata
            #
            "reasoning":
                "Timeline:\n"
                + "\n".join(
                    parsed.get("timeline") or []
                ),

            "supporting_signals": [
                s.name
                for s in signals
            ],

            "confidence":
                float(
                    parsed.get("confidence")
                    or 0.5
                ),

            "blast_radius":
                parsed.get("blast_radius")
                or "service",

            "operational_risk":
                parsed.get("operational_risk")
                or "medium",

            "rollback":
                "Rollback recent deployment or "
                "revert operational change if applicable.",

            #
            # Actionable steps
            #
            "solution_steps": [

                {
                    "step": i + 1,

                    "command":
                        "Manual action",

                    "description":
                        action,
                }

                for i, action in enumerate(
                    parsed.get("next_actions")
                    or []
                )
            ],

            #
            # Manual only
            #
            "manual_only":
                True,

            #
            # Root-cause recs
            # should NEVER auto-execute
            #
            "boto3_sequence": [],

            #
            # Evidence
            #
            "evidence": {

                s.name: s.evidence
                for s in signals
            },
        }
    ]


ALL_AGENTS = [
    metric_analyzer_agent,
    cost_optimization_agent,
    reliability_agent,
    security_agent,
    root_cause_agent,
]
