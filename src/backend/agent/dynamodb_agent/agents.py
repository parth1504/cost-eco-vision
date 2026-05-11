"""
Specialized DynamoDB intelligence sub-agents.

Each agent consumes:
    (TelemetryBundle, signals)

And emits:
    List[Recommendation]

IMPORTANT:
Agents NEVER reason over raw telemetry directly.

They consume ONLY structured signals extracted from the
signal extraction layer.

This prevents:
    - hallucinated recommendations
    - generic advice
    - unsafe automation
    - threshold-only behavior

Architecture:
    signals
        →
    specialized agents
        →
    validated recommendations
"""

from __future__ import annotations

import json
import logging

from typing import Any, Dict, List, Optional

from agent.dynamodb_agent.signals import (
    signals_by_name,
)

from agent.dynamodb_agent.types import (
    RecCategory,
    Recommendation,
    RecType,
    Severity,
    Signal,
    TelemetryBundle,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared Recommendation Builder
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
    blast_radius: str = "table",
    operational_risk: str = "low",
    rollback: str = "",
    estimated_savings: Any = "N/A",
    cost_basis: str = "",
    latency_impact: str = "",
    durability_impact: str = "",
    solution_steps: Optional[List[Dict[str, Any]]] = None,
    boto3_sequence: Optional[List[Dict[str, Any]]] = None,
    manual_only: bool = False,
) -> Recommendation:

    evidence = {}

    for signal in supporting_signals:
        evidence[signal.name] = signal.evidence

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

        supporting_signals=[
            signal.name
            for signal in supporting_signals
        ],

        impact=impact,
        blast_radius=blast_radius,
        operational_risk=operational_risk,

        rollback=rollback,

        estimated_savings=estimated_savings,
        cost_basis=cost_basis,

        latency_impact=latency_impact,
        durability_impact=durability_impact,

        solution_steps=solution_steps or [],
        boto3_sequence=boto3_sequence or [],

        manual_only=manual_only,
    )


# ---------------------------------------------------------------------------
# Capacity Optimization Agent
# ---------------------------------------------------------------------------

def capacity_optimization_agent(
    bundle: TelemetryBundle,
    signals: List[Signal],
) -> List[Recommendation]:

    by = signals_by_name(signals)

    out: List[Recommendation] = []

    #
    # Overprovisioned RCU
    #
    if "overprovisioned_rcu_detected" in by:

        s = by["overprovisioned_rcu_detected"]

        out.append(
            _build_rec(
                rule_id="dynamodb.cost.overprovisioned_rcu",

                title="Provisioned Read Capacity Overallocated",

                rec_type=RecType.COST,

                severity=Severity.MEDIUM,

                category=RecCategory.OPTIMIZATION,

                confidence=s.confidence,

                description=(
                    "Provisioned read capacity significantly "
                    "exceeds observed workload utilization."
                ),

                issue=s.description,

                reasoning=(
                    "Consumed RCU remains consistently below "
                    "provisioned baseline."
                ),

                supporting_signals=[s],

                impact="medium",

                blast_radius="table",

                operational_risk="medium",

                estimated_savings=round(
                    bundle.monthly_cost * 0.20,
                    2,
                ),

                cost_basis=(
                    "Estimated reduction from lowering "
                    "provisioned read throughput."
                ),

                latency_impact=(
                    "Aggressive reductions may increase "
                    "throttling risk during bursts."
                ),

                durability_impact="No durability impact.",

                rollback=(
                    "Restore previous provisioned "
                    "read capacity."
                ),

                manual_only=True,
            )
        )

    #
    # Overprovisioned WCU
    #
    if "overprovisioned_wcu_detected" in by:

        s = by["overprovisioned_wcu_detected"]

        out.append(
            _build_rec(
                rule_id="dynamodb.cost.overprovisioned_wcu",

                title="Provisioned Write Capacity Overallocated",

                rec_type=RecType.COST,

                severity=Severity.MEDIUM,

                category=RecCategory.OPTIMIZATION,

                confidence=s.confidence,

                description=(
                    "Provisioned write capacity significantly "
                    "exceeds observed workload utilization."
                ),

                issue=s.description,

                reasoning=(
                    "Consumed WCU remains consistently below "
                    "allocated write throughput."
                ),

                supporting_signals=[s],

                impact="medium",

                blast_radius="table",

                operational_risk="medium",

                estimated_savings=round(
                    bundle.monthly_cost * 0.18,
                    2,
                ),

                cost_basis=(
                    "Estimated reduction from lowering "
                    "provisioned write throughput."
                ),

                latency_impact=(
                    "Aggressive write reductions may "
                    "increase retry pressure."
                ),

                durability_impact="No durability impact.",

                rollback=(
                    "Restore previous provisioned "
                    "write capacity."
                ),

                manual_only=True,
            )
        )

    return out


# ---------------------------------------------------------------------------
# Performance + Scalability Agent
# ---------------------------------------------------------------------------

def performance_scalability_agent(
    bundle: TelemetryBundle,
    signals: List[Signal],
) -> List[Recommendation]:

    by = signals_by_name(signals)

    out: List[Recommendation] = []

    #
    # Throttling
    #
    if "throttling_detected" in by:

        s = by["throttling_detected"]

        out.append(
            _build_rec(
                rule_id="dynamodb.performance.throttling",

                title="DynamoDB Throttling Detected",

                rec_type=RecType.PERFORMANCE,

                severity=Severity.HIGH,

                category=RecCategory.WARNING,

                confidence=s.confidence,

                description=(
                    "Request throttling detected. "
                    "Application latency and retries may increase."
                ),

                issue=s.description,

                reasoning=(
                    "Throttle metrics exceeded "
                    "acceptable operational baseline."
                ),

                supporting_signals=[s],

                impact="high",

                blast_radius="service",

                operational_risk="medium",

                latency_impact=(
                    "Tail latency and retries may "
                    "increase significantly."
                ),

                durability_impact="No durability impact.",

                rollback="Restore prior throughput settings.",

                manual_only=True,
            )
        )

    #
    # Hot partition
    #
    if "hot_partition_detected" in by:

        s = by["hot_partition_detected"]

        out.append(
            _build_rec(
                rule_id="dynamodb.performance.hot_partition",

                title="Hot Partition Detected",

                rec_type=RecType.PERFORMANCE,

                severity=Severity.HIGH,

                category=RecCategory.WARNING,

                confidence=s.confidence,

                description=(
                    "Partition imbalance detected. "
                    "Specific partition keys appear overloaded."
                ),

                issue=s.description,

                reasoning=(
                    "Partition skew ratio indicates "
                    "uneven workload distribution."
                ),

                supporting_signals=[s],

                impact="high",

                blast_radius="table",

                operational_risk="high",

                latency_impact=(
                    "Hot partitions may create severe "
                    "tail-latency amplification."
                ),

                durability_impact="No durability impact.",

                rollback="Restore previous access strategy.",

                manual_only=True,
            )
        )

    #
    # Retry storm
    #
    if "retry_storm_detected" in by:

        s = by["retry_storm_detected"]

        out.append(
            _build_rec(
                rule_id="dynamodb.performance.retry_storm",

                title="Retry Amplification Detected",

                rec_type=RecType.PERFORMANCE,

                severity=Severity.CRITICAL,

                category=RecCategory.CRITICAL,

                confidence=s.confidence,

                description=(
                    "Excessive retry activity detected. "
                    "This may amplify load and destabilize workloads."
                ),

                issue=s.description,

                reasoning=(
                    "Retry rate strongly correlates "
                    "with throttling activity."
                ),

                supporting_signals=[s],

                impact="high",

                blast_radius="service",

                operational_risk="high",

                latency_impact=(
                    "Retry amplification may drastically "
                    "increase request latency."
                ),

                durability_impact="No durability impact.",

                rollback="Restore previous retry behavior.",

                manual_only=True,
            )
        )

    return out


# ---------------------------------------------------------------------------
# Reliability + DR Agent
# ---------------------------------------------------------------------------

def reliability_agent(
    bundle: TelemetryBundle,
    signals: List[Signal],
) -> List[Recommendation]:

    by = signals_by_name(signals)

    out: List[Recommendation] = []

    #
    # PITR disabled
    #
    if "pitr_disabled" in by:

        s = by["pitr_disabled"]

        out.append(
            _build_rec(
                rule_id="dynamodb.reliability.pitr",

                title="Point-in-Time Recovery Disabled",

                rec_type=RecType.RELIABILITY,

                severity=Severity.HIGH,

                category=RecCategory.WARNING,

                confidence=s.confidence,

                description=(
                    "Point-in-Time Recovery is disabled "
                    "for this table."
                ),

                issue=s.description,

                reasoning=(
                    "Continuous backup protection "
                    "is not enabled."
                ),

                supporting_signals=[s],

                impact="high",

                blast_radius="table",

                operational_risk="low",

                latency_impact="No latency impact.",

                durability_impact=(
                    "Recovery capability significantly reduced."
                ),

                rollback="Disable PITR if necessary.",

                solution_steps=[
                    {
                        "step": 1,
                        "command": (
                            f"aws dynamodb update-continuous-backups "
                            f"--table-name {bundle.table_name}"
                        ),
                        "description": (
                            "Enable Point-in-Time Recovery."
                        ),
                    }
                ],

                manual_only=True,
            )
        )

    #
    # Replication lag
    #
    if "replication_lag_detected" in by:

        s = by["replication_lag_detected"]

        out.append(
            _build_rec(
                rule_id="dynamodb.reliability.replication_lag",

                title="Global Table Replication Lag",

                rec_type=RecType.RELIABILITY,

                severity=Severity.CRITICAL,

                category=RecCategory.CRITICAL,

                confidence=s.confidence,

                description=(
                    "Cross-region replication lag detected."
                ),

                issue=s.description,

                reasoning=(
                    "Global table replication latency "
                    "exceeds operational threshold."
                ),

                supporting_signals=[s],

                impact="high",

                blast_radius="multi-region",

                operational_risk="high",

                latency_impact=(
                    "Cross-region reads may observe stale data."
                ),

                durability_impact=(
                    "Replication instability may impact "
                    "disaster recovery readiness."
                ),

                rollback=(
                    "Restore previous replication configuration."
                ),

                manual_only=True,
            )
        )

    return out


# ---------------------------------------------------------------------------
# Root Cause + Workload Intelligence Agent (LLM)
# ---------------------------------------------------------------------------

def root_cause_agent(
    bundle: TelemetryBundle,
    signals: List[Signal],
) -> List[Recommendation]:

    """
    LLM-powered workload reasoning layer.

    Purpose:
        - correlate multiple DynamoDB signals
        - identify workload bottlenecks
        - explain retry amplification
        - explain partition imbalance
        - identify inefficient access patterns
        - explain autoscaling instability

    IMPORTANT:
        This agent NEVER generates direct boto3 actions.

    The LLM is used ONLY for:
        - operational explanation
        - workload interpretation
        - correlation reasoning
    """

    #
    # Need enough signal density
    #
    if len(signals) < 2:
        return []

    signal_summary = [
        {
            "name": s.name,
            "severity": s.severity.value,
            "confidence": s.confidence,
            "description": s.description,
            "evidence": s.evidence,
        }
        for s in signals
    ]

    workload_patterns = (
        bundle.workload_patterns or {}
    )

    trends = (
        bundle.historical_trends or {}
    )

    prompt = (
        "You are a senior DynamoDB SRE.\n\n"

        "Analyze the following DynamoDB operational signals.\n\n"

        "Focus on:\n"
        "- partition imbalance\n"
        "- throttling root causes\n"
        "- retry amplification\n"
        "- inefficient scans\n"
        "- autoscaling instability\n"
        "- workload access patterns\n"
        "- hot partitions\n"
        "- latency anomalies\n\n"

        f"Signals:\n"
        f"{json.dumps(signal_summary, default=str)}\n\n"

        f"Workload patterns:\n"
        f"{json.dumps(workload_patterns, default=str)}\n\n"

        f"Historical trends:\n"
        f"{json.dumps(trends, default=str)}\n\n"

        "Return ONLY valid JSON:\n"
        "{\n"
        '  "title": "...",\n'
        '  "summary": "...",\n'
        '  "severity": "critical|high|medium|low",\n'
        '  "confidence": 0.0-1.0,\n'
        '  "root_cause": "...",\n'
        '  "next_actions": ["...", "..."]\n'
        "}\n"
    )

    try:

        from agent.llm.llm_client import (
            get_llm_client,
        )

        text = (
            get_llm_client().generate(prompt)
            or ""
        )

    except Exception as e:

        logger.warning(
            "DynamoDB workload intelligence "
            "LLM failed: %s",
            e,
        )

        return []

    #
    # Tolerant JSON extraction
    #
    try:

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

        parsed = json.loads(text)

    except Exception:

        logger.warning(
            "DynamoDB workload intelligence "
            "parse failed"
        )

        return []

    sev = {
        "critical": Severity.CRITICAL,
        "high": Severity.HIGH,
        "medium": Severity.MEDIUM,
        "low": Severity.LOW,
    }.get(
        (
            parsed.get("severity")
            or "medium"
        ).lower(),
        Severity.MEDIUM,
    )

    return [
        _build_rec(
            rule_id="dynamodb.root_cause.workload_analysis",

            title=(
                parsed.get("title")
                or "DynamoDB Workload Intelligence Analysis"
            ),

            rec_type=RecType.OPERATIONAL,

            severity=sev,

            category=RecCategory.WARNING,

            confidence=float(
                parsed.get("confidence")
                or 0.5
            ),

            description=(
                parsed.get("summary")
                or "AI-generated workload analysis."
            ),

            issue=(
                parsed.get("root_cause")
                or parsed.get("summary")
                or ""
            ),

            reasoning=(
                parsed.get("summary")
                or ""
            ),

            supporting_signals=signals,

            impact="high",

            blast_radius="table",

            operational_risk="medium",

            latency_impact=(
                "Workload inefficiencies may increase "
                "tail latency and retry pressure."
            ),

            durability_impact=(
                "No direct durability degradation identified."
            ),

            rollback="No rollback required.",

            manual_only=True,

            solution_steps=[
                {
                    "step": i + 1,
                    "command": "Manual action",
                    "description": action,
                }
                for i, action in enumerate(
                    parsed.get("next_actions") or []
                )
            ],
        )
    ]


ALL_AGENTS = [
    capacity_optimization_agent,
    performance_scalability_agent,
    reliability_agent,
    root_cause_agent,
]