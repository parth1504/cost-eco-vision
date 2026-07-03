"""
Memory layer — historical recommendation intelligence
for S3 analysis.

The system uses the existing recommendation history
attached to the resource as long-term operational memory.

We do NOT introduce a new persistence layer.

This prevents:
    - repeated Glacier transition spam
    - recurring lifecycle recommendations
    - duplicate public-access findings
    - repeated intelligent-tiering suggestions
    - recurring replication warnings

The memory layer also enables:
    - operational recurrence awareness
    - storage-growth tracking
    - reliability escalation detection
    - historical optimization context

Examples:
    - repeated retrieval-cost spikes
    - lifecycle recommendations ignored repeatedly
    - recurring replication failures
    - public buckets remaining unresolved

Core responsibilities:
    - duplicate suppression
    - cooldown handling
    - severity escalation awareness
    - recurring issue annotation
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from agent.s3_agent.types import (
    Recommendation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_iso(
    value: Optional[str],
) -> Optional[datetime]:

    if not value:
        return None

    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "")
        )

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Prior Recommendation Lookup
# ---------------------------------------------------------------------------

def find_prior(
    rec: Recommendation,
    history: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:

    """
    Find most recent matching recommendation.
    """

    matches = [
        item
        for item in history
        if (
            item.get("rule_id") == rec.rule_id
            or item.get("title") == rec.title
        )
    ]

    if not matches:
        return None

    matches.sort(
        key=lambda item:
            item.get("detected_at")
            or item.get("last_activity")
            or "",
        reverse=True,
    )

    return matches[0]


# ---------------------------------------------------------------------------
# Emission Decision Logic
# ---------------------------------------------------------------------------

def should_emit(
    rec: Recommendation,
    history: List[Dict[str, Any]],
    cooldown_hours: int = 48,
) -> bool:

    """
    Determine whether recommendation should be emitted.

    Re-emit only when:
        - no prior recommendation exists
        - severity increased
        - confidence increased substantially
        - cooldown elapsed
        - recurring operational issue persists
        - prior recommendation was rejected long ago

    S3-specific behavior:
        - suppress repeated Glacier recommendations
        - suppress repeated lifecycle spam
        - suppress repeated intelligent-tiering noise
        - avoid constant public-access warnings
    """

    prior = find_prior(rec, history)

    #
    # No prior history
    #
    if not prior:
        return True

    prior_status = (
        prior.get("status") or ""
    ).lower()

    last_seen = _parse_iso(
        prior.get("detected_at")
        or prior.get("last_activity")
    )

    #
    # Respect rejected recommendations
    #
    if prior_status in (
        "dismissed",
        "rejected",
    ):

        #
        # Glacier/archive suggestions
        # should not nag frequently
        #
        if (
            "glacier" in rec.rule_id.lower()
            and last_seen
            and datetime.utcnow() - last_seen
            < timedelta(days=14)
        ):
            return False

        #
        # Lifecycle recommendations
        #
        if (
            "lifecycle" in rec.rule_id.lower()
            and last_seen
            and datetime.utcnow() - last_seen
            < timedelta(days=10)
        ):
            return False

        #
        # Intelligent tiering
        #
        if (
            "intelligent_tiering"
            in rec.rule_id.lower()

            and last_seen
            and datetime.utcnow() - last_seen
            < timedelta(days=10)
        ):
            return False

        #
        # Public-access findings should
        # re-surface sooner.
        #
        if (
            "public_access"
            in rec.rule_id.lower()

            and last_seen
            and datetime.utcnow() - last_seen
            < timedelta(days=5)
        ):
            return False

    #
    # Severity escalation
    #
    sev_rank = {
        "info": 1,
        "low": 1,
        "medium": 2,
        "warning": 2,
        "high": 3,
        "critical": 4,
    }

    prior_severity = (
        prior.get("severity") or ""
    ).lower()

    current_rank = sev_rank.get(
        rec.severity.value.lower(),
        0,
    )

    prior_rank = sev_rank.get(
        prior_severity,
        0,
    )

    if current_rank > prior_rank:
        return True

    #
    # Confidence increase
    #
    prior_confidence = float(
        prior.get("confidence") or 0
    )

    if rec.confidence - prior_confidence >= 0.20:
        return True

    #
    # Persistent operational issue
    #
    recurring_matches = [
        item
        for item in history
        if item.get("rule_id") == rec.rule_id
    ]

    if len(recurring_matches) >= 3:

        #
        # Reliability/security issues
        # should re-surface aggressively
        #
        if (
            "replication" in rec.rule_id
            or "public_access" in rec.rule_id
            or "encryption" in rec.rule_id
        ):
            return True

    #
    # Cooldown elapsed
    #
    if (
        last_seen
        and datetime.utcnow() - last_seen
        >= timedelta(hours=cooldown_hours)
    ):
        return True

    return False


# ---------------------------------------------------------------------------
# Historical Annotation
# ---------------------------------------------------------------------------

def annotate_with_history(
    rec: Recommendation,
    history: List[Dict[str, Any]],
) -> Recommendation:

    """
    Add operational history context to recommendation.

    Adds:
        - recurrence metadata
        - rejection history
        - persistent storage-pattern hints
        - operational persistence context
    """

    matches = [
        item
        for item in history
        if (
            item.get("rule_id") == rec.rule_id
            or item.get("title") == rec.title
        )
    ]

    if not matches:
        return rec

    #
    # Recurrence count
    #
    rec.evidence = {
        **rec.evidence,
        "prior_emissions": len(matches),
    }

    #
    # Rejection history
    #
    rejected_count = len([
        item
        for item in matches
        if (
            item.get("status") or ""
        ).lower() in (
            "dismissed",
            "rejected",
        )
    ])

    if rejected_count > 0:
        rec.evidence[
            "prior_rejections"
        ] = rejected_count

    #
    # Recurring issue annotation
    #
    if len(matches) >= 3:

        recurring_prefix = (
            f"⚠️ Recurring issue detected "
            f"({len(matches)} prior emissions). "
        )

        #
        # Contextual operational hints
        #
        if "replication" in rec.rule_id:

            recurring_prefix += (
                "Bucket durability or cross-region "
                "consistency risk appears persistent.\n\n"
            )

        elif "public_access" in rec.rule_id:

            recurring_prefix += (
                "Bucket exposure risk remains unresolved.\n\n"
            )

        elif "lifecycle" in rec.rule_id:

            recurring_prefix += (
                "Storage optimization opportunity "
                "remains unresolved.\n\n"
            )

        elif "glacier" in rec.rule_id:

            recurring_prefix += (
                "Cold-storage optimization continues "
                "to remain unaddressed.\n\n"
            )

        else:

            recurring_prefix += (
                "Underlying operational issue "
                "continues to recur.\n\n"
            )

        rec.reasoning = (
            recurring_prefix
            + rec.reasoning
        )

    #
    # Historical rejection context
    #
    if rejected_count >= 2:

        rec.reasoning += (
            "\n\nHistorical context: "
            "Similar recommendations were previously "
            "dismissed or rejected multiple times."
        )

    return rec