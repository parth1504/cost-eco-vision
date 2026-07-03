"""
Specialized S3 intelligence sub-agents.

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

logger = logging.getLogger(__name__)

from typing import Any, Dict, List, Optional

from agent.s3_agent.signals import signals_by_name
from agent.s3_agent.types import (
    RecCategory,
    Recommendation,
    RecType,
    Severity,
    Signal,
    TelemetryBundle,
)


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
    blast_radius: str = "bucket",
    operational_risk: str = "low",
    rollback: str = "",
    estimated_savings: Any = "N/A",
    cost_basis: str = "",
    retrieval_impact: str = "",
    durability_impact: str = "",
    solution_steps: Optional[List[Dict[str, Any]]] = None,
    boto3_sequence: Optional[List[Dict[str, Any]]] = None,
    manual_only: bool = False,
) -> Recommendation:
    """
    Centralized recommendation builder.

    Enforces:
        - evidence
        - confidence
        - rollback
        - operational safety metadata
    """

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

        retrieval_impact=retrieval_impact,
        durability_impact=durability_impact,

        solution_steps=solution_steps or [],
        boto3_sequence=boto3_sequence or [],

        manual_only=manual_only,
    )


# ---------------------------------------------------------------------------
# Storage Utilization Agent
# ---------------------------------------------------------------------------

def storage_utilization_agent(
    bundle: TelemetryBundle,
    signals: List[Signal],
) -> List[Recommendation]:

    by = signals_by_name(signals)

    out: List[Recommendation] = []

    #
    # Excessive small objects
    #
    if "excessive_small_objects_detected" in by:
        s = by["excessive_small_objects_detected"]

        out.append(
            _build_rec(
                rule_id="s3.storage.small_objects",
                title="Excessive Small Object Storage Pattern",
                rec_type=RecType.PERFORMANCE,
                severity=Severity.MEDIUM,
                category=RecCategory.OPTIMIZATION,
                confidence=s.confidence,

                description=(
                    "Large numbers of very small objects increase "
                    "request overhead, metadata operations, and "
                    "storage inefficiency."
                ),

                issue=s.description,

                reasoning=(
                    "High small-object ratio detected from "
                    "bucket storage telemetry."
                ),

                supporting_signals=[s],

                impact="medium",
                blast_radius="bucket",

                operational_risk="low",

                estimated_savings=round(
                    bundle.monthly_cost * 0.15,
                    2,
                ),

                cost_basis=(
                    "Reduced request charges and metadata overhead."
                ),

                retrieval_impact=(
                    "No direct retrieval impact expected."
                ),

                durability_impact=(
                    "No durability impact."
                ),

                rollback="No rollback required.",

                manual_only=True,

                solution_steps=[
                    {
                        "step": 1,
                        "command": (
                            "Aggregate small files into larger "
                            "compressed objects where feasible."
                        ),
                        "description": (
                            "Reduce request and metadata overhead."
                        ),
                    }
                ],
            )
        )

    #
    # Abnormal growth
    #
    if "bucket_growth_abnormal" in by:
        s = by["bucket_growth_abnormal"]

        out.append(
            _build_rec(
                rule_id="s3.storage.abnormal_growth",
                title="Abnormal Bucket Storage Growth",
                rec_type=RecType.OPERATIONAL,
                severity=Severity.HIGH,
                category=RecCategory.WARNING,
                confidence=s.confidence,

                description=(
                    "Bucket growth exceeds expected operational "
                    "baseline and may indicate retention leaks, "
                    "duplicate uploads, or lifecycle gaps."
                ),

                issue=s.description,

                reasoning=(
                    "Growth-rate telemetry significantly exceeds "
                    "normal bucket growth patterns."
                ),

                supporting_signals=[s],

                impact="high",
                blast_radius="bucket",

                operational_risk="medium",

                estimated_savings="Unknown",

                retrieval_impact=(
                    "Investigation required before lifecycle changes."
                ),

                durability_impact=(
                    "Avoid aggressive cleanup before confirming "
                    "workload retention requirements."
                ),

                rollback="Revert lifecycle changes if needed.",

                manual_only=True,
            )
        )

    return out


# ---------------------------------------------------------------------------
# Cost Optimization Agent
# ---------------------------------------------------------------------------

def cost_optimization_agent(
    bundle: TelemetryBundle,
    signals: List[Signal],
) -> List[Recommendation]:

    by = signals_by_name(signals)

    out: List[Recommendation] = []

    #
    # Missing lifecycle
    #
    if "missing_lifecycle_policy" in by:
        s = by["missing_lifecycle_policy"]

        out.append(
            _build_rec(
                rule_id="s3.cost.lifecycle_missing",
                title="Lifecycle Policy Missing",
                rec_type=RecType.COST,
                severity=Severity.MEDIUM,
                category=RecCategory.OPTIMIZATION,
                confidence=s.confidence,

                description=(
                    "Bucket lacks lifecycle automation for "
                    "archival or cleanup of stale objects."
                ),

                issue=s.description,

                reasoning=(
                    "Lifecycle configuration disabled despite "
                    "ongoing storage growth."
                ),

                supporting_signals=[s],

                impact="medium",
                blast_radius="bucket",

                operational_risk="medium",

                estimated_savings=round(
                    bundle.monthly_cost * 0.25,
                    2,
                ),

                cost_basis=(
                    "Estimated savings from archival transitions "
                    "and stale object cleanup."
                ),

                retrieval_impact=(
                    "Potential retrieval latency increase if "
                    "objects transition to Glacier tiers."
                ),

                durability_impact=(
                    "Durability remains unchanged across S3 tiers."
                ),

                rollback=(
                    "Disable lifecycle policy and restore "
                    "storage class if needed."
                ),

                manual_only=True,
            )
        )

    #
    # Glacier opportunity
    #
    if "cold_storage_candidate" in by:
        s = by["cold_storage_candidate"]

        out.append(
            _build_rec(
                rule_id="s3.cost.glacier_candidate",
                title="Cold Storage Archival Opportunity",
                rec_type=RecType.COST,
                severity=Severity.LOW,
                category=RecCategory.OPTIMIZATION,
                confidence=s.confidence,

                description=(
                    "Large amount of cold data appears suitable "
                    "for Glacier archival storage classes."
                ),

                issue=s.description,

                reasoning=(
                    "High stale-object ratio with low access activity."
                ),

                supporting_signals=[s],

                impact="medium",
                blast_radius="bucket",

                operational_risk="medium",

                estimated_savings=round(
                    bundle.monthly_cost * 0.40,
                    2,
                ),

                cost_basis=(
                    "Estimated based on Glacier storage pricing delta."
                ),

                retrieval_impact=(
                    "Archive retrieval latency may increase from "
                    "minutes to hours depending on retrieval tier."
                ),

                durability_impact=(
                    "Glacier maintains high durability guarantees."
                ),

                rollback=(
                    "Restore archived objects to standard tiers."
                ),

                manual_only=True,
            )
        )

    #
    # Intelligent Tiering
    #
    if "intelligent_tiering_underutilized" in by:
        s = by["intelligent_tiering_underutilized"]

        out.append(
            _build_rec(
                rule_id="s3.cost.intelligent_tiering",
                title="Enable Intelligent Tiering",
                rec_type=RecType.COST,
                severity=Severity.LOW,
                category=RecCategory.OPTIMIZATION,
                confidence=s.confidence,

                description=(
                    "Bucket exhibits mixed access patterns that "
                    "may benefit from automatic storage tier movement."
                ),

                issue=s.description,

                reasoning=(
                    "Intelligent Tiering adoption is low despite "
                    "variable access behavior."
                ),

                supporting_signals=[s],

                impact="low",
                blast_radius="bucket",

                operational_risk="low",

                estimated_savings=round(
                    bundle.monthly_cost * 0.10,
                    2,
                ),

                cost_basis=(
                    "Savings estimate from automatic tier placement."
                ),

                retrieval_impact=(
                    "No meaningful retrieval latency impact expected."
                ),

                durability_impact="No durability impact.",

                rollback="Disable Intelligent Tiering policy.",
            )
        )

    return out


# ---------------------------------------------------------------------------
# Reliability + Durability Agent
# ---------------------------------------------------------------------------

def reliability_agent(
    bundle: TelemetryBundle,
    signals: List[Signal],
) -> List[Recommendation]:

    by = signals_by_name(signals)

    out: List[Recommendation] = []

    #
    # Versioning disabled
    #
    if "versioning_disabled" in by:
        s = by["versioning_disabled"]

        out.append(
            _build_rec(
                rule_id="s3.reliability.versioning_disabled",
                title="Enable Bucket Versioning",
                rec_type=RecType.RELIABILITY,
                severity=Severity.HIGH,
                category=RecCategory.WARNING,
                confidence=s.confidence,

                description=(
                    "Bucket versioning protects against accidental "
                    "deletion, overwrite, and ransomware-style corruption."
                ),

                issue=s.description,

                reasoning=(
                    "Versioning configuration disabled."
                ),

                supporting_signals=[s],

                impact="high",
                blast_radius="bucket",

                operational_risk="low",

                retrieval_impact=(
                    "No retrieval latency impact expected."
                ),

                durability_impact=(
                    "Significantly improves recovery capability."
                ),

                rollback="Suspend bucket versioning.",

                solution_steps=[
                    {
                        "step": 1,
                        "command": (
                            f"aws s3api put-bucket-versioning "
                            f"--bucket {bundle.bucket_name} "
                            f'--versioning-configuration Status=Enabled'
                        ),
                        "description": (
                            "Enable bucket versioning."
                        ),
                    }
                ],

                boto3_sequence=[
                    {
                        "service": "s3",
                        "operation": "put_bucket_versioning",
                        "params": {
                            "Bucket": bundle.bucket_name,
                            "VersioningConfiguration": {
                                "Status": "Enabled"
                            },
                        },
                    }
                ],
            )
        )

    #
    # Replication failures
    #
    if "replication_failures_detected" in by:
        s = by["replication_failures_detected"]

        out.append(
            _build_rec(
                rule_id="s3.reliability.replication_failures",
                title="Replication Failures Detected",
                rec_type=RecType.RELIABILITY,
                severity=Severity.CRITICAL,
                category=RecCategory.CRITICAL,
                confidence=s.confidence,

                description=(
                    "Bucket replication operations are failing, "
                    "creating durability and disaster recovery risk."
                ),

                issue=s.description,

                reasoning=(
                    "Replication failure telemetry observed."
                ),

                supporting_signals=[s],

                impact="high",
                blast_radius="cross-region",

                operational_risk="high",

                retrieval_impact=(
                    "Replication gaps may impact failover readiness."
                ),

                durability_impact=(
                    "Reduced redundancy protection until resolved."
                ),

                rollback="Restore previous replication configuration.",

                manual_only=True,
            )
        )

    return out


# ---------------------------------------------------------------------------
# Security + Compliance Agent
# ---------------------------------------------------------------------------

def security_agent(
    bundle: TelemetryBundle,
    signals: List[Signal],
) -> List[Recommendation]:

    by = signals_by_name(signals)

    out: List[Recommendation] = []

    #
    # Public bucket
    #
    if "public_access_risk_detected" in by:
        s = by["public_access_risk_detected"]

        out.append(
            _build_rec(
                rule_id="s3.security.public_access",
                title="Public Bucket Exposure Detected",
                rec_type=RecType.SECURITY,
                severity=Severity.CRITICAL,
                category=RecCategory.CRITICAL,
                confidence=s.confidence,

                description=(
                    "Bucket allows public access and may expose "
                    "sensitive organizational data."
                ),

                issue=s.description,

                reasoning=(
                    "Public access configuration detected."
                ),

                supporting_signals=[s],

                impact="high",
                blast_radius="account",

                operational_risk="medium",

                retrieval_impact=(
                    "Restricting access may impact public workloads."
                ),

                durability_impact="No durability impact.",

                rollback="Restore public access settings if required.",

                manual_only=True,
            )
        )

    #
    # Encryption disabled
    #
    if "unencrypted_storage_detected" in by:
        s = by["unencrypted_storage_detected"]

        out.append(
            _build_rec(
                rule_id="s3.security.encryption_disabled",
                title="Enable Bucket Encryption",
                rec_type=RecType.SECURITY,
                severity=Severity.HIGH,
                category=RecCategory.WARNING,
                confidence=s.confidence,

                description=(
                    "Bucket encryption at rest is disabled."
                ),

                issue=s.description,

                reasoning=(
                    "Server-side encryption configuration missing."
                ),

                supporting_signals=[s],

                impact="high",
                blast_radius="account",

                operational_risk="low",

                retrieval_impact="No retrieval impact.",

                durability_impact="No durability impact.",

                rollback="Disable default encryption if necessary.",

                solution_steps=[
                    {
                        "step": 1,
                        "command": (
                            f"aws s3api put-bucket-encryption "
                            f"--bucket {bundle.bucket_name}"
                        ),
                        "description": (
                            "Enable default bucket encryption."
                        ),
                    }
                ],

                manual_only=True,
            )
        )

    return out


# ---------------------------------------------------------------------------
# Access Pattern Correlation Agent
# ---------------------------------------------------------------------------

def access_pattern_agent(
    bundle: TelemetryBundle,
    signals: List[Signal],
) -> List[Recommendation]:

    by = signals_by_name(signals)

    out: List[Recommendation] = []

    #
    # Retrieval spikes + transfer anomalies
    #
    if (
        "retrieval_spike_detected" in by
        and "transfer_cost_anomaly_detected" in by
    ):
        sigs = [
            by["retrieval_spike_detected"],
            by["transfer_cost_anomaly_detected"],
        ]

        out.append(
            _build_rec(
                rule_id="s3.access.transfer_spike",
                title="Retrieval Activity Driving Transfer Costs",
                rec_type=RecType.OPERATIONAL,
                severity=Severity.HIGH,
                category=RecCategory.WARNING,
                confidence=max(s.confidence for s in sigs),

                description=(
                    "Abnormal retrieval activity appears correlated "
                    "with elevated transfer costs."
                ),

                issue=(
                    "Retrieval spikes detected alongside "
                    "high transfer charges."
                ),

                reasoning=(
                    "Cross-correlation between retrieval activity "
                    "and transfer-cost telemetry."
                ),

                supporting_signals=sigs,

                impact="high",
                blast_radius="bucket",

                operational_risk="medium",

                retrieval_impact=(
                    "Potential workload or CDN inefficiency."
                ),

                durability_impact="No durability impact.",

                rollback="No rollback required.",

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
        - correlate multiple S3 signals
        - identify probable workload patterns
        - explain storage anomalies
        - identify lifecycle strategy gaps
        - explain transfer-cost anomalies

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

    access_patterns = (
        bundle.access_patterns or {}
    )

    trends = (
        bundle.historical_trends or {}
    )

    prompt = (
        "You are a senior cloud storage SRE.\n\n"

        "Analyze the following S3 operational signals.\n"

        "Focus on:\n"
        "- workload access patterns\n"
        "- lifecycle inefficiencies\n"
        "- retrieval anomalies\n"
        "- storage growth behavior\n"
        "- transfer-cost patterns\n\n"

        f"Signals:\n"
        f"{json.dumps(signal_summary, default=str)}\n\n"

        f"Access patterns:\n"
        f"{json.dumps(access_patterns, default=str)}\n\n"

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
            "S3 workload intelligence LLM failed: %s",
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
            "S3 workload intelligence parse failed"
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
            rule_id="s3.root_cause.workload_analysis",

            title=(
                parsed.get("title")
                or "S3 Workload Intelligence Analysis"
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

            impact="medium",

            blast_radius="bucket",

            operational_risk="low",

            retrieval_impact=(
                "Review workload access behavior before "
                "applying lifecycle optimizations."
            ),

            durability_impact=(
                "No direct durability risk identified."
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
    storage_utilization_agent,
    cost_optimization_agent,
    reliability_agent,
    security_agent,
    access_pattern_agent,
    root_cause_agent,
]