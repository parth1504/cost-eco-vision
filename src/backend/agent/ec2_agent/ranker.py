"""
Recommendation ranking + dedup.

After all sub-agents have produced recs and safety has filtered them,
we still need to:
  1. Deduplicate within a single run (same rule_id from two agents)
  2. Sort by a priority score that balances severity × confidence ÷ risk
"""

from __future__ import annotations

from typing import List

from agent.ec2_agent.types import Recommendation, Severity


_SEV_SCORE = {
    Severity.CRITICAL: 5,
    Severity.HIGH: 4,
    Severity.WARNING: 3,
    Severity.MEDIUM: 3,
    Severity.LOW: 2,
    Severity.INFO: 1,
}

_RISK_DIVISOR = {"low": 1.0, "medium": 1.4, "high": 2.0}


def _priority(rec: Recommendation) -> float:
    """Higher = surface earlier."""
    sev = _SEV_SCORE.get(rec.severity, 2)
    risk = _RISK_DIVISOR.get(rec.operational_risk, 1.4)
    return (sev * rec.confidence) / risk


def deduplicate(recs: List[Recommendation]) -> List[Recommendation]:
    """Within one run, take the highest-priority instance of each rule_id."""
    by_rule: dict = {}
    for r in recs:
        existing = by_rule.get(r.rule_id)
        if existing is None or _priority(r) > _priority(existing):
            by_rule[r.rule_id] = r
    return list(by_rule.values())


def rank(recs: List[Recommendation]) -> List[Recommendation]:
    """Dedup then sort by priority score (highest first)."""
    return sorted(deduplicate(recs), key=_priority, reverse=True)
