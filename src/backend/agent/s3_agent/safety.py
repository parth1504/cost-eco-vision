"""
Safety + Guardrails layer for S3 intelligence recommendations.

This layer exists to prevent:
    - unsafe storage automation
    - dangerous archival actions
    - destructive lifecycle recommendations
    - accidental durability reduction
    - hallucinated optimization advice

Operational safety ALWAYS overrides aggressive cost reduction.

Recommendations failing safety validation are:
    - dropped
    - downgraded
    - forced to manual_only

Rules enforced:
    1. Every recommendation must contain evidence.
    2. Confidence below threshold → drop.
    3. Risky storage-class transitions → manual_only.
    4. Durability-reducing changes → never auto-apply.
    5. CRITICAL recommendations require rollback guidance.
    6. Glacier/archive recommendations require retrieval warnings.
    7. Public-access modifications always require manual review.
    8. Lifecycle cleanup recommendations cannot auto-delete data.

This is the:
    "reliability and durability over aggressive optimization"
layer from the architecture spec.
"""

from __future__ import annotations

import logging
from typing import List

from agent.s3_agent.types import (
    Recommendation,
    RecCategory,
    Severity,
)

logger = logging.getLogger(__name__)

MIN_CONFIDENCE_TO_EMIT = 0.45


# ---------------------------------------------------------------------------
# Rules that MUST remain manual-only
# ---------------------------------------------------------------------------

MANUAL_ONLY_RULES = {
    #
    # Cost / archival actions
    #
    "s3.cost.glacier_candidate",
    "s3.cost.lifecycle_missing",

    #
    # Security-sensitive
    #
    "s3.security.public_access",

    #
    # Replication / durability
    #
    "s3.reliability.replication_failures",

    #
    # Operational investigations
    #
    "s3.storage.abnormal_growth",
}


# ---------------------------------------------------------------------------
# Rules that impact durability
# ---------------------------------------------------------------------------

DURABILITY_SENSITIVE_RULES = {
    "s3.cost.glacier_candidate",
    "s3.cost.lifecycle_missing",
}


# ---------------------------------------------------------------------------
# Validation Pipeline
# ---------------------------------------------------------------------------

def validate_and_filter(
    recs: List[Recommendation],
) -> List[Recommendation]:

    """
    Validate recommendations against operational guardrails.
    """

    out: List[Recommendation] = []

    for rec in recs:

        #
        # Rule 1:
        # Evidence required.
        #
        if not rec.evidence:
            logger.info(
                "safety: dropping %s — missing evidence",
                rec.rule_id,
            )
            continue

        #
        # Rule 2:
        # Confidence threshold.
        #
        if rec.confidence < MIN_CONFIDENCE_TO_EMIT:
            logger.info(
                "safety: dropping %s — confidence %.2f below floor",
                rec.rule_id,
                rec.confidence,
            )
            continue

        #
        # Rule 3:
        # Empty boto3 params → manual only.
        #
        for cmd in rec.boto3_sequence:

            if not cmd.get("params"):
                rec.manual_only = True

                logger.info(
                    "safety: forcing manual_only on %s "
                    "— empty boto3 params",
                    rec.rule_id,
                )

                break

        #
        # Rule 4:
        # Sensitive storage operations
        # should NEVER auto-apply.
        #
        if rec.rule_id in MANUAL_ONLY_RULES:
            rec.manual_only = True

        #
        # Rule 5:
        # Durability-sensitive actions
        # require rollback guidance.
        #
        if (
            rec.rule_id in DURABILITY_SENSITIVE_RULES
            and not rec.rollback
        ):
            rec.rollback = (
                "Restore objects to previous storage class "
                "and disable lifecycle transition policy."
            )

        #
        # Rule 6:
        # Critical recommendations MUST include rollback.
        #
        if (
            rec.category == RecCategory.CRITICAL
            and not rec.rollback
        ):
            rec.rollback = (
                "Reverse configuration changes manually "
                "using previous bucket configuration."
            )

        #
        # Rule 7:
        # Glacier/archive actions MUST warn about retrieval latency.
        #
        if (
            "glacier" in rec.rule_id.lower()
            and not rec.retrieval_impact
        ):
            rec.retrieval_impact = (
                "Archived objects may require minutes or "
                "hours for retrieval depending on retrieval tier."
            )

        #
        # Rule 8:
        # Never auto-delete storage blindly.
        #
        if (
            "delete" in rec.title.lower()
            or "cleanup" in rec.title.lower()
        ):
            rec.manual_only = True

            logger.info(
                "safety: forcing manual_only on %s "
                "— deletion-related operation",
                rec.rule_id,
            )

        #
        # Rule 9:
        # Public access modifications
        # always require human validation.
        #
        if "public_access" in rec.rule_id:
            rec.manual_only = True

        #
        # Rule 10:
        # Low-confidence CRITICAL/HIGH severity
        # should be downgraded.
        #
        if (
            rec.confidence < 0.60
            and rec.severity in (
                Severity.CRITICAL,
                Severity.HIGH,
            )
        ):
            rec.severity = (
                Severity.HIGH
                if rec.severity == Severity.CRITICAL
                else Severity.MEDIUM
            )

            logger.info(
                "safety: downgraded severity on %s "
                "due to low confidence",
                rec.rule_id,
            )

        #
        # Rule 11:
        # Missing retrieval impact on archival actions.
        #
        if (
            rec.rule_id.startswith("s3.cost")
            and "archive" in rec.title.lower()
            and not rec.retrieval_impact
        ):
            rec.retrieval_impact = (
                "Storage archival may increase retrieval latency."
            )

        #
        # Rule 12:
        # Missing durability impact should default safely.
        #
        if not rec.durability_impact:
            rec.durability_impact = (
                "No significant durability impact identified."
            )

        out.append(rec)

    return out