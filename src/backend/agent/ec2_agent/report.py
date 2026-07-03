"""
Human-readable report generation.

Two outputs:
  - to_dict(rec): the SHAPE the existing frontend expects (compatible with
    the legacy `generate_ec2_recommendations` output) so this slots in
    without UI changes.
  - to_markdown(rec): a formatted block suitable for emails/Slack/PDF.
    Optional, only used by future report-export endpoints.
"""

from __future__ import annotations

from typing import Any, Dict

from agent.ec2_agent.types import Recommendation


def _severity_legacy(sev_value: str) -> str:
    """
    Legacy frontend uses lowercase severities like 'critical' / 'high' /
    'warning'. Our enum already uses lowercase string values, so this is
    mostly a passthrough — but documents the expectation.
    """
    return (sev_value or "medium").lower()


def to_legacy_dict(rec: Recommendation) -> Dict[str, Any]:
    """
    Project a Recommendation onto the dict shape the existing frontend
    consumes (alerts page, resources page).

    Adds the new SRE-agent fields (reasoning, evidence, blast_radius,
    operational_risk, rollback) under their snake_case names — old UI
    components ignore them; new ones can render them progressively.
    """
    return {
        "rule_id": rec.rule_id,
        "title": rec.title,
        "type": rec.type.value,
        "category": rec.category.value,
        "severity": _severity_legacy(rec.severity.value),
        "confidence": rec.confidence,
        "description": rec.description,
        "issue": rec.issue,
        # SRE-agent specific (new fields)
        "reasoning": rec.reasoning,
        "evidence": rec.evidence,
        "supporting_signals": rec.supporting_signals,
        "blast_radius": rec.blast_radius,
        "operational_risk": rec.operational_risk,
        "rollback": rec.rollback,
        "cost_basis": rec.cost_basis,
        # Legacy fields the existing UI already renders
        "impact": rec.impact,
        "saving": rec.estimated_savings,
        "status": rec.status,
        "manual_only": rec.manual_only,
        "solution_steps": rec.solution_steps,
        "boto3_sequence": rec.boto3_sequence,
        "detected_at": rec.detected_at.isoformat(),
    }


def to_markdown(rec: Recommendation) -> str:
    """Operator-friendly multi-line block — for runbooks / exports."""
    parts = [
        f"## {rec.title}",
        f"**Severity**: {rec.severity.value.title()}  ·  "
        f"**Confidence**: {int(rec.confidence * 100)}%  ·  "
        f"**Category**: {rec.category.value}",
        "",
        f"**Issue**: {rec.issue}",
        f"**Description**: {rec.description}",
        "",
    ]
    if rec.reasoning:
        parts.append(f"**Reasoning**:\n{rec.reasoning}")
        parts.append("")
    if rec.evidence:
        parts.append("**Evidence**:")
        for k, v in rec.evidence.items():
            parts.append(f"  - `{k}`: {v}")
        parts.append("")
    parts.extend([
        f"**Blast radius**: {rec.blast_radius}",
        f"**Operational risk**: {rec.operational_risk}",
        f"**Estimated savings**: {rec.estimated_savings}",
        f"**Cost basis**: {rec.cost_basis or '—'}",
        f"**Rollback**: {rec.rollback or '—'}",
        "",
    ])
    if rec.solution_steps:
        parts.append("**Suggested actions**:")
        for step in rec.solution_steps:
            parts.append(f"  {step.get('step')}. {step.get('description')}")
            cmd = step.get("command")
            if cmd and cmd != "Manual action":
                parts.append(f"     `{cmd}`")
    if rec.manual_only:
        parts.append("\n_⚠️ Manual review required — Apply Fix is disabled for this recommendation._")
    return "\n".join(parts)
