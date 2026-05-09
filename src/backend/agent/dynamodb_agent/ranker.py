"""
Recommendation ranking + deduplication
for DynamoDB intelligence analysis.

After:
    - signal extraction
    - specialized agent reasoning
    - safety validation
    - historical filtering

the system still needs to:
    1. deduplicate recommendations
    2. prioritize operationally critical findings
    3. suppress optimization noise
    4. prioritize reliability over aggressive savings

Ranking philosophy:
    reliability + scalability > cost optimization

Examples:
    - retry storms outrank overprovisioned RCUs
    - replication lag outranks billing-mode advice
    - throttling outranks scan optimizations
    - PITR gaps outrank cost savings

Priority balances:
    severity
    confidence
    operational risk
    latency impact
    durability impact
    workload blast radius
"""

from __future__ import annotations

from typing import List

from agent.dynamodb_agent.types import (
    Recommendation,
    Severity,
)


# ---------------------------------------------------------------------------
# Severity scoring
# ---------------------------------------------------------------------------

_SEV_SCORE = {
    Severity.CRITICAL: 6,
    Severity.HIGH: 5,
    Severity.WARNING: 4,
    Severity.MEDIUM: 3,
    Severity.LOW: 2,
    Severity.INFO: 1,
}


# ---------------------------------------------------------------------------
# Operational-risk divisor
# Higher operational risk lowers automatic ranking
# ---------------------------------------------------------------------------

_RISK_DIVISOR = {
    "low": 1.0,
    "medium": 1.5,
    "high": 2.3,
}


# ---------------------------------------------------------------------------
# Reliability + scalability boosts
# ---------------------------------------------------------------------------

CRITICAL_PRIORITY_BOOSTS = {

    #
    # Reliability
    #
    "dynamodb.reliability.replication_lag": 2.8,
    "dynamodb.reliability.pitr": 2.0,

    #
    # Severe performance failures
    #
    "dynamodb.performance.retry_storm": 2.7,
    "dynamodb.performance.throttling": 2.2,

    #
    # Hot-partition scalability bottlenecks
    #
    "dynamodb.performance.hot_partition": 2.1,
}


# ---------------------------------------------------------------------------
# Optimization deprioritization
# Avoid cost-noise dominating dashboard
# ---------------------------------------------------------------------------

OPTIMIZATION_PENALTIES = {
    "dynamodb.cost.overprovisioned_rcu": 0.90,
    "dynamodb.cost.overprovisioned_wcu": 0.90,
    "dynamodb.cost.billing_mode": 0.85,
}


# ---------------------------------------------------------------------------
# Priority calculation
# ---------------------------------------------------------------------------

def _priority(
    rec: Recommendation,
) -> float:

    """
    Higher score = surfaced earlier.
    """

    severity_score = _SEV_SCORE.get(
        rec.severity,
        2,
    )

    risk_divisor = _RISK_DIVISOR.get(
        rec.operational_risk,
        1.5,
    )

    base_score = (
        severity_score * rec.confidence
    ) / risk_divisor

    #
    # Reliability/scalability boost
    #
    base_score *= CRITICAL_PRIORITY_BOOSTS.get(
        rec.rule_id,
        1.0,
    )

    #
    # Optimization penalty
    #
    base_score *= OPTIMIZATION_PENALTIES.get(
        rec.rule_id,
        1.0,
    )

    #
    # Retry amplification boost
    #
    if (
        rec.latency_impact
        and "retry" in rec.latency_impact.lower()
    ):
        base_score *= 1.15

    #
    # Tail-latency amplification boost
    #
    if (
        rec.latency_impact
        and "tail latency" in rec.latency_impact.lower()
    ):
        base_score *= 1.10

    #
    # Durability-sensitive boost
    #
    if (
        rec.durability_impact
        and (
            "recovery" in rec.durability_impact.lower()
            or "consistency" in rec.durability_impact.lower()
        )
    ):
        base_score *= 1.20

    #
    # Schema redesign penalty
    # Important, but operationally expensive
    #
    if "partition_key" in rec.rule_id:
        base_score *= 0.92

    #
    # Manual-only recommendations
    # get slight penalty
    #
    if rec.manual_only:
        base_score *= 0.96

    return round(base_score, 4)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate(
    recs: List[Recommendation],
) -> List[Recommendation]:

    """
    Deduplicate recommendations produced
    by multiple agents.

    Keep highest-priority version.
    """

    by_rule = {}

    for rec in recs:

        existing = by_rule.get(
            rec.rule_id
        )

        if (
            existing is None
            or _priority(rec)
            > _priority(existing)
        ):
            by_rule[rec.rule_id] = rec

    return list(by_rule.values())


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def rank(
    recs: List[Recommendation],
) -> List[Recommendation]:

    """
    Deduplicate then sort by operational priority.
    """

    deduped = deduplicate(recs)

    return sorted(
        deduped,
        key=_priority,
        reverse=True,
    )