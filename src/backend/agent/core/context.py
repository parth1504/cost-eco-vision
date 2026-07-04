"""
Context engineering layer.

Controls what information each agent sees. Raw telemetry never reaches
an LLM directly — this layer curates the context window with:
  - Relevant signals (not all signals, just the ones this agent cares about)
  - Prior recommendations for this resource (from memory)
  - Cross-agent findings (what other agents have already found)
  - Session history (what has already been decided)

Signal domains and rec-type relevance are loaded from the dynamic
service registry — adding a new service automatically extends context
filtering without touching this file.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from agent.core.registry import registry

logger = logging.getLogger(__name__)

SIGNAL_DOMAIN_MAP: Dict[str, Set[str]] = registry.get_signal_domain_map()


def build_agent_context(
    agent_id: str,
    signals: List[Dict[str, Any]],
    resource: Dict[str, Any],
    prior_recommendations: List[Dict[str, Any]],
    session_decisions: List[Dict[str, Any]],
    cross_agent_findings: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Build a curated context payload for a specific agent.
    Filters signals to only include those relevant to this agent's domain.
    """
    agent_def = registry.get_agent_definition(agent_id)
    domain_signals = agent_def.signal_domain if agent_def else set()

    relevant_signals = [
        s for s in signals
        if s.get("name") in domain_signals or not domain_signals
    ]

    relevant_prior = [
        r for r in prior_recommendations
        if _is_relevant_recommendation(agent_id, r)
    ][-10:]

    recent_decisions = session_decisions[-5:]

    context: Dict[str, Any] = {
        "agent_id": agent_id,
        "resource": _slim_resource(resource),
        "signals": relevant_signals,
        "signal_count": len(relevant_signals),
        "prior_recommendations": relevant_prior,
        "recent_decisions": recent_decisions,
    }

    if cross_agent_findings:
        context["cross_agent_findings"] = cross_agent_findings

    recurring = _detect_recurring(relevant_prior)
    if recurring:
        context["recurring_patterns"] = recurring

    return context


def build_cross_agent_summary(
    findings: Dict[str, List[Dict[str, Any]]],
    current_agent: str,
) -> List[Dict[str, Any]]:
    """
    Build a compact summary of what other agents have found.
    Used to give each sub-agent visibility into sibling findings.
    """
    summary: List[Dict[str, Any]] = []
    for agent_name, recs in findings.items():
        if agent_name == current_agent or not recs:
            continue
        for rec in recs[:5]:
            summary.append({
                "from_agent": agent_name,
                "rule_id": rec.get("rule_id", ""),
                "title": rec.get("title", ""),
                "type": rec.get("type", ""),
                "severity": rec.get("severity", ""),
                "confidence": rec.get("confidence", 0),
            })
    return summary


def _slim_resource(resource: Dict[str, Any]) -> Dict[str, Any]:
    keep_keys = {
        "resource_id", "name", "type", "region", "status", "monthly_cost",
        "tags", "instance_type", "creation_date", "is_optimized",
    }
    return {k: v for k, v in resource.items() if k in keep_keys}


def _is_relevant_recommendation(agent_id: str, rec: Dict[str, Any]) -> bool:
    rec_type = (rec.get("type") or "").lower()
    agent_def = registry.get_agent_definition(agent_id)
    if not agent_def or not agent_def.rec_type_relevance:
        return True
    return rec_type in agent_def.rec_type_relevance


def _detect_recurring(recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from collections import Counter
    rule_counts = Counter(
        r.get("rule_id") for r in recommendations if r.get("rule_id")
    )
    return [
        {"rule_id": rid, "occurrences": count}
        for rid, count in rule_counts.items()
        if count >= 3
    ]


def build_critique_context(
    recommendations: List[Dict[str, Any]],
    signals: List[Dict[str, Any]],
    resource: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "agent_id": "critique",
        "resource": _slim_resource(resource),
        "recommendations_to_review": recommendations,
        "available_signals": signals,
        "review_instructions": {
            "check_evidence": "Every recommendation must cite specific signal evidence",
            "check_confidence": "Flag recommendations with <0.5 confidence",
            "check_conflicts": "Flag contradictory recommendations",
            "check_safety": "Flag anything that could cause outages",
            "check_completeness": "Note important signals that no recommendation addresses",
        },
    }


def build_correlation_context(
    all_findings: Dict[str, List[Dict[str, Any]]],
    resources: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "agent_id": "correlation",
        "resources": [_slim_resource(r) for r in resources],
        "findings_by_agent": {
            agent: findings[:10]
            for agent, findings in all_findings.items()
        },
        "correlation_instructions": {
            "find_dependencies": "Identify resources that affect each other",
            "find_compound_savings": "Find optimizations that amplify when done together",
            "find_conflicts": "Find recommendations that conflict across resources",
        },
    }
