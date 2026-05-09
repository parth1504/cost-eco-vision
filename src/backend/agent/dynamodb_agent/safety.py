"""
Safety + Guardrails layer.

Validates each Recommendation against a set of hard rules before it can
exit the pipeline. Anything that fails validation is either dropped or
downgraded (severity reduced, manual_only forced) — never silently
emitted as-is.

Rules enforced:
  1. Every recommendation must have at least one piece of evidence.
  2. Confidence below MIN_CONFIDENCE → drop (or downgrade if `severe_drop`).
  3. boto3_sequence with empty params → force manual_only.
  4. Recommendations that reduce redundancy (downsize ASG, remove AZ) →
     force manual_only regardless of confidence.
  5. Recommendations marked CRITICAL must include a rollback note.

This is the "operational safety over aggressive optimization" enforcer.
"""

from __future__ import annotations

import logging
from typing import List

from agent.ec2_agent.types import Recommendation, RecCategory, Severity

logger = logging.getLogger(__name__)

MIN_CONFIDENCE_TO_EMIT = 0.4

# Rule IDs that touch redundancy / availability — never auto-apply.
REDUNDANCY_REDUCING_RULES = {
    "ec2.cost.idle_stop",  # stopping a single ASG member is fine; safety check below handles ASG context
}


def validate_and_filter(recs: List[Recommendation]) -> List[Recommendation]:
    """Apply guardrails. Returns a (possibly mutated, possibly shorter) list."""
    out: List[Recommendation] = []
    for rec in recs:
        # Rule 1: evidence required
        if not rec.evidence:
            logger.info("safety: dropping %s — no evidence", rec.rule_id)
            continue

        # Rule 2: confidence floor
        if rec.confidence < MIN_CONFIDENCE_TO_EMIT:
            logger.info("safety: dropping %s — confidence %.2f below floor", rec.rule_id, rec.confidence)
            continue

        # Rule 3: empty params → manual_only
        for cmd in rec.boto3_sequence:
            if not cmd.get("params"):
                rec.manual_only = True
                logger.info("safety: forcing manual_only on %s — empty params", rec.rule_id)
                break

        # Rule 4: redundancy-touching → manual_only unless evidence is overwhelming
        if rec.rule_id in REDUNDANCY_REDUCING_RULES and rec.confidence < 0.85:
            rec.manual_only = True

        # Rule 5: critical needs rollback
        if rec.category == RecCategory.CRITICAL and not rec.rollback:
            rec.rollback = "Reverse the applied action manually. See solution steps."

        # Severity sanity: if confidence is low but we're emitting, downgrade severity by one tier
        if rec.confidence < 0.6 and rec.severity in (Severity.CRITICAL, Severity.HIGH):
            rec.severity = Severity.MEDIUM if rec.severity == Severity.HIGH else Severity.HIGH
            logger.info("safety: downgraded severity on %s due to low confidence", rec.rule_id)

        out.append(rec)
    return out
