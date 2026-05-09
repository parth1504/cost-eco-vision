"""
Top-level S3 intelligence agent orchestrator.

Pipeline:

    resource dict (legacy shape from aws/s3.py:build_s3_resource)
        │
        ▼
    [collector]   collect_from_resource()  →  TelemetryBundle
    [normalizer]  normalize()
        │
        ▼
    [signals]     extract_signals()        →  List[Signal]
        │
        ▼
    [agents]      Storage / Cost / Reliability / Security / Access
                  → List[Recommendation]
        │
        ▼
    [safety]      validate_and_filter()
        │
        ▼
    [memory]      annotate_with_history() + should_emit() filter
        │
        ▼
    [ranker]      deduplicate + rank by priority
        │
        ▼
    [report]      to_legacy_dict() — frontend-compatible shape
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agent.s3_agent.agents import ALL_AGENTS
from agent.s3_agent.memory import annotate_with_history, should_emit
from agent.s3_agent.ranker import rank
from agent.s3_agent.report import to_legacy_dict
from agent.s3_agent.safety import validate_and_filter
from agent.s3_agent.signals import extract_signals
from agent.s3_agent.telemetry import collect_from_resource, normalize

logger = logging.getLogger(__name__)


def run_s3_agent(resource: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    End-to-end S3 intelligence agent run for a single bucket resource.

    Returns recommendations in the SAME dict shape the legacy
    `generate_s3_recommendations` produces, making this a
    drop-in replacement.
    """

    if not resource or resource.get("type") != "S3":
        return []

    if resource.get("is_optimized"):
        return []

    # 1-2. Collect + normalize telemetry.
    bundle = normalize(collect_from_resource(resource))

    # 3. Extract intelligence signals.
    signals = extract_signals(bundle)

    # 4. Run specialized agents.
    recommendations = []

    for agent_fn in ALL_AGENTS:
        try:
            recommendations.extend(agent_fn(bundle, signals))
        except Exception as e:
            logger.warning(
                "S3 agent %s failed: %s",
                agent_fn.__name__,
                e,
            )

    # 5. Safety + guardrails.
    recommendations = validate_and_filter(recommendations)

    # 6. Historical memory + deduplication.
    history = list(resource.get("recommendations") or [])

    final = []

    for rec in recommendations:
        if not should_emit(rec, history):
            logger.info(
                "memory: suppressing %s (recent duplicate)",
                rec.rule_id,
            )
            continue

        final.append(
            annotate_with_history(rec, history)
        )

    # 7. Rank + deduplicate.
    final = rank(final)

    # 8. Convert into frontend-compatible format.
    return [to_legacy_dict(r) for r in final]