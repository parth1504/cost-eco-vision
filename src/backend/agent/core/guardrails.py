"""
Unified guardrails for the multi-agent system.

Guardrails operate at three levels:
  1. Pre-execution  — validate inputs before an agent runs
  2. Inter-agent    — validate messages between agents (prevent loops, injection)
  3. Post-execution — validate recommendations before they reach the user

Each gate returns a VerificationGate result that's recorded in the session
trace for full auditability.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agent.core.types import VerificationGate, VerificationResult

logger = logging.getLogger(__name__)

MIN_CONFIDENCE = 0.4
MAX_CONVERSATION_DEPTH = 20
COST_ACCURACY_THRESHOLD = 0.05  # ±5%


def verify_recommendation(rec: Dict[str, Any]) -> VerificationGate:
    """Post-execution: validate a single recommendation before emission."""
    issues = []

    if not rec.get("evidence") and not rec.get("supporting_signals"):
        issues.append("No evidence or supporting signals")

    confidence = rec.get("confidence", 0)
    if confidence < MIN_CONFIDENCE:
        issues.append(f"Confidence {confidence:.2f} below floor {MIN_CONFIDENCE}")

    if not rec.get("title"):
        issues.append("Missing title")

    if not rec.get("description"):
        issues.append("Missing description")

    severity = (rec.get("severity") or "").lower()
    if severity in ("critical", "high") and not rec.get("rollback"):
        rec["rollback"] = "Reverse the applied action manually. See solution steps."

    if severity in ("critical", "high") and confidence < 0.6:
        old = rec.get("severity", "medium")
        rec["severity"] = "medium" if old == "high" else "high"
        issues.append(f"Downgraded severity from {old} due to low confidence")

    for cmd in rec.get("boto3_sequence", []):
        if not cmd.get("params"):
            rec["manual_only"] = True
            issues.append("Empty boto3 params — forced manual_only")

    if issues:
        return VerificationGate(
            gate_name="recommendation_validation",
            result=VerificationResult.NEEDS_REVIEW if len(issues) <= 2 else VerificationResult.FAILED,
            details="; ".join(issues),
            actual_value=confidence,
            threshold=MIN_CONFIDENCE,
        )

    return VerificationGate(
        gate_name="recommendation_validation",
        result=VerificationResult.PASSED,
        details="All checks passed",
        actual_value=confidence,
        threshold=MIN_CONFIDENCE,
    )


def verify_cost_projection(
    projected_savings: float,
    baseline_cost: float,
) -> VerificationGate:
    """Verify that a cost projection is within reasonable bounds."""
    if baseline_cost <= 0:
        return VerificationGate(
            gate_name="cost_projection",
            result=VerificationResult.SKIPPED,
            details="No baseline cost available",
        )

    ratio = projected_savings / baseline_cost
    if ratio > 1.0:
        return VerificationGate(
            gate_name="cost_projection",
            result=VerificationResult.FAILED,
            details=f"Projected savings ({projected_savings}) exceed baseline cost ({baseline_cost})",
            threshold=1.0,
            actual_value=ratio,
        )

    if ratio > 0.8:
        return VerificationGate(
            gate_name="cost_projection",
            result=VerificationResult.NEEDS_REVIEW,
            details=f"Savings ratio {ratio:.1%} is unusually high — verify",
            threshold=0.8,
            actual_value=ratio,
        )

    return VerificationGate(
        gate_name="cost_projection",
        result=VerificationResult.PASSED,
        details=f"Savings ratio {ratio:.1%} within bounds",
        threshold=0.8,
        actual_value=ratio,
    )


def verify_conversation_depth(message_count: int) -> VerificationGate:
    """Prevent infinite agent conversation loops."""
    if message_count > MAX_CONVERSATION_DEPTH:
        return VerificationGate(
            gate_name="conversation_depth",
            result=VerificationResult.FAILED,
            details=f"Conversation depth {message_count} exceeds max {MAX_CONVERSATION_DEPTH}",
            threshold=float(MAX_CONVERSATION_DEPTH),
            actual_value=float(message_count),
        )
    return VerificationGate(
        gate_name="conversation_depth",
        result=VerificationResult.PASSED,
        details=f"Depth {message_count}/{MAX_CONVERSATION_DEPTH}",
        threshold=float(MAX_CONVERSATION_DEPTH),
        actual_value=float(message_count),
    )


def verify_safety(rec: Dict[str, Any]) -> VerificationGate:
    """Check for operationally dangerous recommendations."""
    dangerous_patterns = [
        ("delete", "Deletion operation detected"),
        ("terminate", "Termination operation detected"),
        ("remove", "Removal operation detected"),
    ]

    for step in rec.get("solution_steps", []):
        cmd = (step.get("command") or "").lower()
        for pattern, warning in dangerous_patterns:
            if pattern in cmd and not rec.get("manual_only"):
                rec["manual_only"] = True
                return VerificationGate(
                    gate_name="safety_check",
                    result=VerificationResult.NEEDS_REVIEW,
                    details=f"{warning} — forced manual_only: {cmd[:80]}",
                )

    blast = (rec.get("blast_radius") or "").lower()
    if blast in ("account", "organization") and not rec.get("manual_only"):
        rec["manual_only"] = True
        return VerificationGate(
            gate_name="safety_check",
            result=VerificationResult.NEEDS_REVIEW,
            details=f"Account/org blast radius — forced manual_only",
        )

    return VerificationGate(
        gate_name="safety_check",
        result=VerificationResult.PASSED,
        details="No dangerous operations detected",
    )


def run_all_gates(rec: Dict[str, Any]) -> List[VerificationGate]:
    """Run all verification gates on a recommendation."""
    gates = [
        verify_recommendation(rec),
        verify_safety(rec),
    ]

    savings = rec.get("saving") or rec.get("estimated_savings")
    if isinstance(savings, (int, float)) and savings > 0:
        baseline = rec.get("_baseline_cost", 0)
        if baseline > 0:
            gates.append(verify_cost_projection(savings, baseline))

    return gates
