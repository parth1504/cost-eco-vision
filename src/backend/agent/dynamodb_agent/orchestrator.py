"""
Top-level DynamoDB intelligence agent orchestrator.

Pipeline:

    resource dict
    (legacy shape from aws/dynamodb.py:build_dynamodb_resource)
        │
        ▼
    [collector]
        collect_from_resource()
            → TelemetryBundle

    [normalizer]
        normalize()
        │
        ▼

    [signals]
        extract_signals()
            → List[Signal]

        (load-bearing intelligence layer)

        Raw telemetry NEVER reaches downstream agents directly.

        Signals represent:
            - throttling
            - hot partitions
            - retry storms
            - scan-heavy workloads
            - overprovisioned throughput
            - replication lag
            - PITR gaps
            - autoscaling instability
            - latency anomalies

        │
        ▼

    [agents]
        Capacity Optimization
        Performance + Scalability
        Cost Optimization
        Reliability + DR
        Root Cause Correlation

            → List[Recommendation]

        │
        ▼

    [safety]
        validate_and_filter()

        Prevents:
            - dangerous throughput reductions
            - unsafe GSI removal
            - unsafe schema redesign advice
            - reliability regressions

        │
        ▼

    [memory]
        annotate_with_history()
        +
        should_emit()

        Prevents:
            - repetitive throttling spam
            - repeated GSI recommendations
            - recurring optimization noise

        │
        ▼

    [ranker]
        deduplicate + rank by priority

        Prioritizes:
            reliability > scalability > cost

        │
        ▼

    [report]
        to_legacy_dict()

        Frontend-compatible projection
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agent.dynamodb_agent.agents import ALL_AGENTS
from agent.dynamodb_agent.memory import (
    annotate_with_history,
    should_emit,
)
from agent.dynamodb_agent.ranker import rank
from agent.dynamodb_agent.report import (
    to_legacy_dict,
)
from agent.dynamodb_agent.safety import (
    validate_and_filter,
)
from agent.dynamodb_agent.signals import (
    extract_signals,
)
from agent.dynamodb_agent.telemetry import (
    collect_from_resource,
    normalize,
)

logger = logging.getLogger(__name__)


def run_dynamodb_agent(
    resource: Dict[str, Any],
) -> List[Dict[str, Any]]:

    """
    End-to-end DynamoDB intelligence agent run
    for a single DynamoDB table.

    Returns recommendations in the SAME dict shape
    the legacy recommendation pipeline produces.

    This allows:
        - drop-in replacement
        - zero frontend changes
        - progressive enhancement
    """

    #
    # Validate resource type
    #
    if (
        not resource
        or resource.get("type") != "DynamoDB"
    ):
        return []

    #
    # Skip already optimized resources
    #
    if resource.get("is_optimized"):
        return []

    #
    # 1-2.
    # Collect + normalize telemetry
    #
    bundle = normalize(
        collect_from_resource(resource)
    )

    #
    # 3.
    # Extract intelligence signals
    #
    signals = extract_signals(bundle)

    #
    # 4.
    # Run specialized sub-agents
    #
    recommendations = []

    for agent_fn in ALL_AGENTS:

        try:
            recommendations.extend(
                agent_fn(bundle, signals)
            )

        #
        # Never fail full pipeline
        # because of one bad agent
        #
        except Exception as e:
            logger.warning(
                "DynamoDB agent %s failed: %s",
                agent_fn.__name__,
                e,
            )

    #
    # 5.
    # Safety + guardrails
    #
    recommendations = validate_and_filter(
        recommendations
    )

    #
    # 6.
    # Historical memory
    #
    history = list(
        resource.get("recommendations") or []
    )

    final: List = []

    for rec in recommendations:

        #
        # Duplicate suppression
        #
        if not should_emit(rec, history):

            logger.info(
                "memory: suppressing %s "
                "(recent duplicate)",
                rec.rule_id,
            )

            continue

        #
        # Historical enrichment
        #
        final.append(
            annotate_with_history(
                rec,
                history,
            )
        )

    #
    # 7.
    # Rank + deduplicate
    #
    final = rank(final)

    #
    # 8.
    # Convert into frontend-compatible dicts
    #
    return [
        to_legacy_dict(rec)
        for rec in final
    ]