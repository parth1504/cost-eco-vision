"""
Human-readable report generation for S3 intelligence analysis.

Two outputs:

    1. to_legacy_dict(rec)
       → frontend-compatible dictionary shape
       → compatible with existing recommendation UI

    2. to_markdown(rec)
       → operator-friendly report block
       → useful for:
            - Slack
            - email digests
            - PDFs
            - incident reviews
            - FinOps reports
            - operational audits

Design goals:
    - explain WHY recommendation exists
    - expose evidence transparently
    - clearly communicate retrieval/durability impact
    - avoid black-box AI behavior
"""

from __future__ import annotations

from typing import Any, Dict

from agent.s3_agent.types import Recommendation


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

    Existing UI fields remain compatible.

    Additional S3 intelligence metadata is included
    progressively for newer UI capabilities.
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
        # Evidence + intelligence
        #
        "evidence": rec.evidence,
        "supporting_signals": rec.supporting_signals,

        #
        # Operational metadata
        #
        "blast_radius": rec.blast_radius,
        "operational_risk": rec.operational_risk,

        #
        # S3-specific operational context
        #
        "retrieval_impact": rec.retrieval_impact,
        "durability_impact": rec.durability_impact,

        #
        # Financial context
        #
        "saving": rec.estimated_savings,
        "cost_basis": rec.cost_basis,

        #
        # Recovery context
        #
        "rollback": rec.rollback,

        #
        # Existing frontend fields
        #
        "impact": rec.impact,
        "status": rec.status,

        #
        # Safety
        #
        "manual_only": rec.manual_only,

        #
        # Remediation
        #
        "solution_steps": rec.solution_steps,
        "boto3_sequence": rec.boto3_sequence,

        #
        # Detection metadata
        #
        "detected_at": rec.detected_at.isoformat(),
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
            f"**Severity**: {rec.severity.value.title()}  ·  "
            f"**Confidence**: {int(rec.confidence * 100)}%  ·  "
            f"**Category**: {rec.category.value}"
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
    # Operational impact
    #
    parts.extend([
        f"**Blast radius**: {rec.blast_radius}",

        f"**Operational risk**: {rec.operational_risk}",

        "",
    ])

    #
    # Retrieval implications
    #
    if rec.retrieval_impact:

        parts.extend([
            (
                f"**Retrieval impact**: "
                f"{rec.retrieval_impact}"
            ),
            "",
        ])

    #
    # Durability implications
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
    # Cost context
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
    # Rollback
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

        parts.append("**Suggested actions**:")

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
    # Durability warning
    #
    if (
        rec.retrieval_impact
        and (
            "hours" in rec.retrieval_impact.lower()
            or "glacier" in rec.title.lower()
        )
    ):

        parts.append(
            "\n_⚠️ Archived retrieval operations may "
            "introduce substantial recovery latency._"
        )

    return "\n".join(parts)