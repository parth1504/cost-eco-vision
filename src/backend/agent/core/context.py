"""
Context engineering layer — controls what information each agent sees.

Raw telemetry never reaches an LLM directly. This module curates
each agent's context window so it only sees what's relevant:

  1. Signal filtering:
     Each agent declares a signal_domain (set of signal names) in its
     AgentDefinition. build_agent_context() filters the full signal list
     to only include signals in that domain. An ec2_cost agent won't see
     security signals; an s3_reliability agent won't see cost signals.

  2. Prior recommendation filtering:
     Each agent declares rec_type_relevance (e.g. {"cost", "performance"}).
     Only prior recs matching those types are included, so the agent
     isn't distracted by unrelated history.

  3. Cross-agent findings:
     A compact summary of what OTHER agents have already found for this
     resource. Enables agents to build on each other's work instead of
     working in isolation.

  4. Recurring pattern detection:
     If the same rule_id appears 3+ times in prior recommendations,
     it's flagged as a recurring pattern — a hint to the agent to
     focus on root cause rather than re-issuing the same rec.

All filtering metadata comes from the dynamic service registry.
Adding a new service automatically extends context filtering.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from agent.core.registry import registry

logger = logging.getLogger(__name__)

# Materialized at import time for backward compatibility with code that
# reads SIGNAL_DOMAIN_MAP directly. New code should use the registry.
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

    # If the agent has no declared signal domain, pass all signals through
    # (fail-open so new agents work before their domains are fully configured).
    relevant_signals = [
        s for s in signals
        if s.get("name") in domain_signals or not domain_signals
    ]

    # Cap prior recs and decisions to keep the LLM context window manageable
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
    Build a compact summary of what OTHER agents have found.

    This enables cross-agent awareness: if ec2_cost found an idle instance,
    ec2_security can see that and prioritize checking its security posture.
    Capped at 5 recs per agent to keep context tight.
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
    # Strip bulky fields (raw metrics, full config) that waste LLM tokens.
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
    # Surface rules that keep appearing — helps agents avoid re-issuing
    # the same recommendation and instead focus on root cause.
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
    """Context for the critique node — includes all recs to review,
    the available signals (so critique can check evidence claims),
    and structured instructions for the LLM quality reviewer."""
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
    """Context for the correlate node — gives the LLM a cross-resource
    view of all findings so it can spot dependencies, conflicts, and
    compound savings that no single-resource agent would catch."""
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
