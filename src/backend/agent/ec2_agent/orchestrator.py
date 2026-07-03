"""
Top-level SRE agent orchestrator.

Pipeline:

    resource dict (legacy shape from aws/ec2.py:build_ec2_resource)
        │
        ▼
    [collector]   collect_from_resource()  →  TelemetryBundle
    [normalizer]  normalize()
        │
        ▼
    [signals]     extract_signals()        →  List[Signal]
        │
        ▼
    [agents]      Metric / Cost / Reliability / Security / Root-Cause
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

import json
import logging
import pathlib
from typing import Any, Dict, List

from agent.ec2_agent.agents import ALL_AGENTS
from agent.ec2_agent.memory import annotate_with_history, should_emit
from agent.ec2_agent.ranker import rank
from agent.ec2_agent.report import to_legacy_dict
from agent.ec2_agent.safety import validate_and_filter
from agent.ec2_agent.signals import extract_signals
from agent.ec2_agent.telemetry import collect_from_resource, normalize

logger = logging.getLogger(__name__)


def run_sre_agent(resource: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    End-to-end SRE agent run for a single EC2 resource.

    Returns a list of recommendations in the SAME dict shape the legacy
    `generate_ec2_recommendations` produces, so this is a drop-in
    replacement for that function.
    """
    if not resource or resource.get("type") != "EC2":
        return []
    if resource.get("is_optimized"):
        return []

    # 1-2. Collect + normalize.
    bundle = normalize(collect_from_resource(resource))

    # 3. Extract signals (the load-bearing intelligence layer).
    signals = extract_signals(bundle)

    # 4. Run every sub-agent in sequence; concatenate recommendations.
    recommendations = []
    for agent_fn in ALL_AGENTS:
        try:
            recommendations.extend(agent_fn(bundle, signals))
        except Exception as e:  # pragma: no cover — never fail the whole run on a bad agent
            logger.warning("SRE agent %s failed: %s", agent_fn.__name__, e)
    
    # # 5. Safety + guardrails.
    # recommendations = validate_and_filter(recommendations)

    # # 6. Memory: annotate with history, suppress duplicates.
    # history = list(resource.get("recommendations") or [])
    # final: List = []
    # for rec in recommendations:
    #     if not should_emit(rec, history):
    #         logger.info("memory: suppressing %s (recent duplicate)", rec.rule_id)
    #         continue
    #     final.append(annotate_with_history(rec, history))

    # 7. Rank + deduplicate.
    final = rank(recommendations)

    # 8. Project to legacy dict shape.
    results = [to_legacy_dict(r) for r in final]

    # 9. Log recommendations to file.
    _log_to_file(resource, results)

    return results


def _log_to_file(resource: Dict[str, Any], recommendations: List[Dict[str, Any]]) -> None:
    log_path = pathlib.Path("ec2_recs.txt")
    instance_id = resource.get("id", "unknown")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"=== {instance_id} ===\n")
        f.write(json.dumps(recommendations, indent=2))
        f.write("\n\n")
