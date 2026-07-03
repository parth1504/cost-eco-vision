"""
Memory layer — historical recommendation context.

The existing `Recommendations` DDB table holds, per-resource, an array of
recommendations from prior runs. We don't add a new table; we read that
array as our long-term memory.

Two functions matter:
  - is_duplicate(rec, history): suppress identical recs that already exist
  - should_resurrect(rec, history, cooldown_hours): allow re-emission only
    if severity went up, confidence went up substantially, or cooldown passed

This is what stops the analyzer from flooding the user with the same
"PITR disabled" recommendation on every refresh.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from agent.ec2_agent.types import Recommendation


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", ""))
    except Exception:
        return None


def find_prior(rec: Recommendation, history: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Find the most recent prior recommendation with the same rule_id."""
    candidates = [
        h for h in history
        if h.get("rule_id") == rec.rule_id or h.get("title") == rec.title
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda h: h.get("detected_at") or h.get("last_activity") or "", reverse=True)
    return candidates[0]


def should_emit(
    rec: Recommendation,
    history: List[Dict[str, Any]],
    cooldown_hours: int = 24,
) -> bool:
    """
    True if this recommendation should be surfaced to the user (vs.
    suppressed as a duplicate of a recent emission).

    Allow re-emission when:
      - no prior history for this rule
      - severity HAS escalated since last emission
      - confidence has jumped by >= 0.2
      - cooldown_hours have elapsed since last emission
      - the prior was rejected/dismissed (we still want to nag, but less often)
    """
    prior = find_prior(rec, history)
    if not prior:
        return True

    prior_status = (prior.get("status") or "").lower()
    if prior_status in ("rejected", "dismissed"):
        # Respect rejection for 7 days; re-surface afterward.
        last = _parse_iso(prior.get("detected_at") or prior.get("last_activity"))
        if last and datetime.utcnow() - last < timedelta(days=7):
            return False

    # Severity escalation
    sev_rank = {"low": 1, "info": 1, "medium": 2, "warning": 2, "high": 3, "critical": 4}
    if sev_rank.get(rec.severity.value, 0) > sev_rank.get(prior.get("severity", ""), 0):
        return True

    # Confidence jump
    prior_conf = float(prior.get("confidence") or 0)
    if rec.confidence - prior_conf >= 0.2:
        return True

    # Cooldown
    last = _parse_iso(prior.get("detected_at") or prior.get("last_activity"))
    if last and datetime.utcnow() - last >= timedelta(hours=cooldown_hours):
        return True

    return False


def annotate_with_history(
    rec: Recommendation,
    history: List[Dict[str, Any]],
) -> Recommendation:
    """
    Enrich a rec with historical context. Adds a `prior_emissions` count to
    evidence so the user sees "this is the 4th time we've flagged this".
    """
    matches = [h for h in history if h.get("rule_id") == rec.rule_id or h.get("title") == rec.title]
    if matches:
        rec.evidence = {**rec.evidence, "prior_emissions": len(matches)}
        # Recurring → bump severity hint
        if len(matches) >= 3 and rec.reasoning:
            rec.reasoning = (
                f"⚠️ Recurring issue ({len(matches)} prior emissions). "
                f"Consider why prior fixes haven't held.\n\n" + rec.reasoning
            )
    return rec
