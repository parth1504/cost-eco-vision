"""
Human-readable report generation
for DynamoDB intelligence analysis.

Two outputs:

    1. to_legacy_dict(rec)
       → frontend-compatible dictionary shape
       → compatible with existing recommendation UI

    2. to_markdown(rec)
       → operator-friendly markdown block
       → useful for:
            - Slack alerts
            - incident reviews
            - PDFs
            - DBRE reports
            - operational audits
            - FinOps exports

Design goals:
    - explain WHY recommendation exists
    - expose evidence transparently
    - explain latency/durability implications
    - avoid black-box AI behavior
    - preserve frontend compatibility
"""

from __future__ import annotations

from typing import Any, Dict

from agent.dynamodb_agent.types import (
    Recommendation,
)


# ---------------------------------------------------------------------------
# Severity Adapter
# ---------------------------------------------------------------------------

def _severity_legacy(
    sev_value: str,
) -> str:
    """
    Existing frontend expects lowercase severity strings.
    """

    return (
        sev_value or "medium"
    ).lower()


# ---------------------------------------------------------------------------
# Frontend-Compatible Projection
# ---------------------------------------------------------------------------

def to_legacy_dict(
    rec: Recommendation,
) -> Dict[str, Any]:

    """
    Convert Recommendation into the dict shape
    consumed by the current frontend.

    Existing fields remain compatible.

    Additional DBRE metadata is progressively added
    for newer UI capabilities.
    """

    return {

        #
        # Core identity
        #
        "rule_id": rec.rule_id,
        "title": rec.title,

        #
        # Classification
        #
        "type": rec.type.value,
        "category": rec.category.value,
        "severity": _severity_legacy(
            rec.severity.value
        ),

        #
        # Confidence
        #
        "confidence": rec.confidence,

        #
        # Core explanation
        #
        "description": rec.description,
        "issue": rec.issue,
        "reasoning": rec.reasoning,

        #
        # Intelligence metadata
        #
        "evidence": rec.evidence,

        "supporting_signals":
            rec.supporting_signals,

        #
        # Operational metadata
        #
        "blast_radius":
            rec.blast_radius,

        "operational_risk":
            rec.operational_risk,

        #
        # DynamoDB-specific operational context
        #
        "latency_impact":
            rec.latency_impact,

        "durability_impact":
            rec.durability_impact,

        #
        # Financial context
        #
        "saving":
            rec.estimated_savings,

        "cost_basis":
            rec.cost_basis,

        #
        # Recovery context
        #
        "rollback":
            rec.rollback,

        #
        # Existing frontend fields
        #
        "impact":
            rec.impact,

        "status":
            rec.status,

        #
        # Safety
        #
        "manual_only":
            rec.manual_only,

        #
        # Remediation
        #
        "solution_steps":
            rec.solution_steps,

        "boto3_sequence":
            rec.boto3_sequence,

        #
        # Detection metadata
        #
        "detected_at":
            rec.detected_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Markdown Report Rendering
# ---------------------------------------------------------------------------

def to_markdown(
    rec: Recommendation,
) -> str:

    """
    Render recommendation into operator-friendly markdown.
    """

    parts = [

        f"## {rec.title}",

        (
            f"**Severity**: "
            f"{rec.severity.value.title()}  ·  "

            f"**Confidence**: "
            f"{int(rec.confidence * 100)}%  ·  "

            f"**Category**: "
            f"{rec.category.value}"
        ),

        "",

        f"**Issue**: {rec.issue}",

        f"**Description**: {rec.description}",

        "",
    ]

    #
    # Reasoning
    #
    if rec.reasoning:

        parts.append(
            f"**Reasoning**:\n{rec.reasoning}"
        )

        parts.append("")

    #
    # Evidence
    #
    if rec.evidence:

        parts.append("**Evidence**:")

        for key, value in rec.evidence.items():

            parts.append(
                f"  - `{key}`: {value}"
            )

        parts.append("")

    #
    # Operational context
    #
    parts.extend([

        (
            f"**Blast radius**: "
            f"{rec.blast_radius}"
        ),

        (
            f"**Operational risk**: "
            f"{rec.operational_risk}"
        ),

        "",
    ])

    #
    # Latency impact
    #
    if rec.latency_impact:

        parts.extend([

            (
                f"**Latency impact**: "
                f"{rec.latency_impact}"
            ),

            "",
        ])

    #
    # Durability impact
    #
    if rec.durability_impact:

        parts.extend([

            (
                f"**Durability impact**: "
                f"{rec.durability_impact}"
            ),

            "",
        ])

    #
    # Financial context
    #
    parts.extend([

        (
            f"**Estimated savings**: "
            f"{rec.estimated_savings}"
        ),

        (
            f"**Cost basis**: "
            f"{rec.cost_basis or '—'}"
        ),

        "",
    ])

    #
    # Rollback guidance
    #
    parts.extend([

        (
            f"**Rollback guidance**: "
            f"{rec.rollback or '—'}"
        ),

        "",
    ])

    #
    # Suggested actions
    #
    if rec.solution_steps:

        parts.append(
            "**Suggested actions**:"
        )

        for step in rec.solution_steps:

            parts.append(
                f"  {step.get('step')}. "
                f"{step.get('description')}"
            )

            command = step.get("command")

            if (
                command
                and command != "Manual action"
            ):

                parts.append(
                    f"     `{command}`"
                )

        parts.append("")

    #
    # Manual review warning
    #
    if rec.manual_only:

        parts.append(
            "_⚠️ Manual review required — "
            "automatic remediation disabled "
            "for this recommendation._"
        )

    #
    # Latency-risk warning
    #
    if (
        rec.latency_impact
        and (
            "tail latency"
            in rec.latency_impact.lower()

            or "retry"
            in rec.latency_impact.lower()

            or "throttling"
            in rec.latency_impact.lower()
        )
    ):

        parts.append(
            "\n_⚠️ This issue may significantly "
            "impact application latency and "
            "request stability under load._"
        )

    #
    # Reliability warning
    #
    if (
        rec.durability_impact
        and (
            "recovery"
            in rec.durability_impact.lower()

            or "consistency"
            in rec.durability_impact.lower()
        )
    ):

        parts.append(
            "\n_⚠️ Reliability and recovery posture "
            "may be degraded until resolved._"
        )

    return "\n".join(parts)