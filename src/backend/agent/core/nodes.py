"""
LangGraph node functions for the unified multi-agent orchestrator.

Every function in this module is a LangGraph "node" — it receives the full
AgentState dict, does some work, and returns a partial dict that LangGraph
merges back into state. Nodes never call each other directly; the graph
edges (defined in graph.py) control execution order.

Pipeline nodes (in execution order controlled by the supervisor):
  1. collect_telemetry  — call per-service telemetry collectors via registry
  2. extract_signals    — call per-service signal extractors via registry
  3. supervisor         — read state, decide which node runs next (sets next_action)
  4. Sub-agent nodes    — dynamically created wrappers that call per-service
                          agent functions via registry (e.g. ec2_metric, s3_cost)
  5. safety_and_rank    — drop low-confidence recs, dedup, filter evidence-free
  6. critique           — LLM + rule-based quality review of recommendations
  7. refine             — apply critique feedback (lower confidence, add warnings)
  8. correlate          — LLM + rule-based cross-resource pattern detection
  9. verify             — run guardrail gates, drop failing recommendations
 10. evaluate           — compute quality metrics, persist session to memory

Sub-agent nodes are registered dynamically from the service registry.
Adding a new AWS service auto-discovers its agents — no changes here.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Tuple, Optional

from agent.core.state import AgentState
from agent.core.guardrails import run_all_gates, verify_conversation_depth
from agent.core.evaluation import evaluation_engine
from agent.core.memory import agent_memory
from agent.core.registry import registry
from agent.core.context import (
    build_agent_context,
    build_cross_agent_summary,
    build_critique_context,
    build_correlation_context,
)

logger = logging.getLogger(__name__)

# Guard against infinite supervisor loops: cap how many times critique→refine
# can cycle and how often any single sub-agent can be invoked per session.
MAX_REFINEMENT_ITERATIONS = 2
MAX_CALLS_PER_AGENT = 2


# ---------------------------------------------------------------------------
# Collect Telemetry
# ---------------------------------------------------------------------------
# First pipeline stage. For each resource, looks up the correct service's
# telemetry collector from the registry (e.g. EC2 → ec2_agent.telemetry),
# calls collect_from_resource() + normalize(), and stores the result
# in telemetry_bundles keyed by resource_id.

def collect_telemetry(state: AgentState) -> dict:
    resources = state.get("resources", [])
    bundles: Dict[str, Any] = {}

    for resource in resources:
        # Skip resources that already have recommendations (e.g. cached)
        if resource.get("recommendations"):
            continue
        rid = resource.get("resource_id", "")
        rtype = resource.get("type")
        try:
            fns = registry.load_telemetry_functions(rtype)
            collect_fn, normalize_fn = fns
            if collect_fn and normalize_fn:
                bundles[rid] = normalize_fn(collect_fn(resource))
        except Exception as e:
            logger.error("Telemetry collection failed for %s: %s", rid, e)

    logger.info("Collected telemetry for %d resources", len(bundles))
    return {
        "telemetry_bundles": bundles,
        "messages": [_message("telemetry", "supervisor",
                              f"Collected telemetry for {len(bundles)} resources")],
    }


# ---------------------------------------------------------------------------
# Extract Signals
# ---------------------------------------------------------------------------
# Second stage. Transforms raw telemetry bundles into typed Signal objects
# (name, severity, confidence, description). Signals are the intelligence
# layer — raw telemetry never reaches downstream agents directly. Each
# service has its own signal extractor that knows its domain.

def extract_signals(state: AgentState) -> dict:
    bundles = state.get("telemetry_bundles", {})
    resources = state.get("resources", [])
    signals_map: Dict[str, List[Any]] = {}
    resource_types = {r.get("resource_id"): r.get("type") for r in resources}

    for rid, bundle in bundles.items():
        rtype = resource_types.get(rid)
        try:
            extract_fn = registry.load_signal_extractor(rtype)
            if extract_fn:
                signals_map[rid] = extract_fn(bundle)
        except Exception as e:
            logger.error("Signal extraction failed for %s: %s", rid, e)

    total_signals = sum(len(s) for s in signals_map.values())
    logger.info("Extracted %d signals across %d resources", total_signals, len(signals_map))
    return {
        "signals_map": signals_map,
        "messages": [_message("signals", "supervisor",
                              f"Extracted {total_signals} signals from {len(signals_map)} resources")],
    }


# ---------------------------------------------------------------------------
# Supervisor — the central routing node
# ---------------------------------------------------------------------------
# The supervisor is the heart of the LangGraph loop. It runs after every
# other node completes (all edges point back to supervisor). It inspects
# the current state and decides what to do next by setting next_action.
#
# The decision cascade is a priority chain:
#   1. No telemetry yet?        → collect_telemetry
#   2. No signals yet?          → extract_signals
#   3. Uncovered signal domains → route to next sub-agent (LLM + rule-based)
#   4. Findings exist, no safety pass yet? → safety_and_rank
#   5. Not critiqued yet?       → critique
#   6. Critique found issues?   → refine (up to MAX_REFINEMENT_ITERATIONS)
#   7. Multiple resources, no correlations? → correlate
#   8. Not verified yet?        → verify
#   9. All done?                → evaluate (terminal)
#
# The conditional edge in graph.py reads state["next_action"] and routes
# to that node. This is how the supervisor pattern works in LangGraph.

def supervisor(state: AgentState) -> dict:
    findings = state.get("findings", {})
    has_findings = any(bool(v) for v in findings.values())
    has_critique = bool(state.get("critique_results", {}).get("reviewed"))
    critique_issues = state.get("critique_results", {}).get("critique", [])
    has_correlations = bool(state.get("correlations"))
    has_verified = bool(state.get("recommendations"))
    iteration = state.get("iteration", 0)
    resources = state.get("resources", [])

    if not state.get("telemetry_bundles"):
        return {
            "next_action": "collect_telemetry",
            "phase": "telemetry",
            "decisions": [_decision("supervisor", "start_telemetry",
                                    f"Starting telemetry collection for {len(resources)} resources")],
        }

    if not state.get("signals_map"):
        return {
            "next_action": "extract_signals",
            "phase": "signals",
            "decisions": [_decision("supervisor", "start_signals",
                                    "Telemetry ready — extracting intelligence signals")],
        }

    next_agent = _route_next_sub_agent(state)
    if next_agent:
        return {
            "next_action": next_agent[0],
            "phase": "sub_agents",
            "decisions": [_decision("supervisor", "route_sub_agent",
                                    next_agent[1])],
        }

    if has_findings and not state.get("all_recommendations"):
        return {
            "next_action": "safety_and_rank",
            "phase": "safety",
            "decisions": [_decision("supervisor", "run_safety",
                                    "Sub-agents complete — running safety filter and ranking")],
        }

    if state.get("all_recommendations") and not has_critique:
        return {
            "next_action": "critique",
            "phase": "critique",
            "decisions": [_decision("supervisor", "request_critique",
                                    "Recommendations ready — requesting quality review")],
        }

    if critique_issues and iteration < MAX_REFINEMENT_ITERATIONS:
        return {
            "next_action": "refine",
            "phase": "refine",
            "iteration": iteration + 1,
            "decisions": [_decision("supervisor", "request_refinement",
                                    f"Critique found {len(critique_issues)} issues — refining (iteration {iteration + 1})")],
        }

    if not has_correlations and len(resources) > 1:
        return {
            "next_action": "correlate",
            "phase": "correlate",
            "decisions": [_decision("supervisor", "request_correlation",
                                    f"Checking cross-resource patterns across {len(resources)} resources")],
        }

    if not has_verified:
        return {
            "next_action": "verify",
            "phase": "verify",
            "decisions": [_decision("supervisor", "run_verification",
                                    "Running verification gates on recommendations")],
        }

    return {
        "next_action": "evaluate",
        "phase": "evaluate",
        "decisions": [_decision("supervisor", "run_evaluation",
                                "Final evaluation and quality metrics")],
    }


# ---------------------------------------------------------------------------
# Sub-agent routing — decides WHICH specialist agent runs next
# ---------------------------------------------------------------------------
# Two routing strategies, tried in order:
#   1. LLM routing: sends signal summary, findings, and call counts to the
#      LLM and asks it to pick the next agent. Catches nuanced patterns
#      like "security agent should run because cost agent found idle
#      instances that may also have open ports."
#   2. Rule-based fallback: deterministic matching of extracted signals
#      against each agent's routing_signals set. Used when LLM is
#      unavailable, returns bad JSON, or suggests an invalid agent.
#
# Both strategies consult the registry for agent definitions, so adding
# a new service automatically makes its agents routable.

def _route_next_sub_agent(state: AgentState) -> Optional[Tuple[str, str]]:
    # LLM routing first for nuanced decisions; falls back to deterministic
    # rule-based routing if LLM is unavailable or returns an invalid agent.
    llm_result = _llm_route(state)
    if llm_result is not None:
        return llm_result
    return _rule_based_route(state)


def _build_router_system_prompt() -> str:
    agent_descriptions = registry.get_router_agent_descriptions()
    return (
        "You are an intelligent orchestration router for an AWS "
        "cloud optimization agent system.\n"
        "Your job: given current signals, findings from agents that "
        "have already run, and call counts, decide which specialist "
        "agent to invoke next.\n\n"
        f"Available agents:\n{agent_descriptions}\n\n"
        "Routing rules:\n"
        "1. Start with baseline agents before specialized ones\n"
        "2. Root-cause agents should only run after domain agents "
        "have produced findings\n"
        "3. Respond DONE when all relevant signal domains are covered\n"
        "4. Never suggest an agent that has reached its call limit "
        "(max 2 calls each)\n"
        "5. Prioritize agents whose signal domains have the most "
        "unaddressed signals\n"
        "6. Consider cross-agent findings — if one agent found issues, "
        "related agents may find more\n\n"
        'Respond ONLY with valid JSON: '
        '{"next": "<agent_name_or_DONE>", '
        '"reason": "<one concise sentence>"}'
    )


def _llm_route(state: AgentState) -> Optional[Tuple[str, str]]:
    signals_map = state.get("signals_map", {})
    resources = state.get("resources", [])
    agent_counts = state.get("agent_call_counts", {})
    findings = state.get("findings", {})

    resource_types = {r.get("resource_id"): r.get("type") for r in resources}

    signal_summary = []
    for rid, signals in signals_map.items():
        rtype = resource_types.get(rid, "unknown")
        for s in signals:
            signal_summary.append({
                "name": s.name,
                "severity": s.severity.value if hasattr(s.severity, "value") else str(s.severity),
                "confidence": round(s.confidence, 2),
                "resource_type": rtype,
            })

    if not signal_summary:
        return None

    finding_summary = []
    for agent_name, recs in findings.items():
        for rec in recs[:5]:
            finding_summary.append({
                "from_agent": agent_name,
                "rule_id": rec.get("rule_id", ""),
                "type": rec.get("type", ""),
                "severity": rec.get("severity", ""),
            })

    all_agent_names = registry.get_all_agent_names()
    available = [
        name for name in all_agent_names
        if agent_counts.get(name, 0) < MAX_CALLS_PER_AGENT
    ]

    if not available:
        return None

    user_msg = (
        f"Current state:\n"
        f"- Signals: {json.dumps(signal_summary, default=str)}\n"
        f"- Findings so far: {json.dumps(finding_summary, default=str)}\n"
        f"- Agents called: {json.dumps(agent_counts)}\n"
        f"- Still available: {json.dumps(available)}\n\n"
        f"What should the orchestrator do next?"
    )

    full_prompt = _build_router_system_prompt() + "\n\n" + user_msg

    try:
        from agent.llm.llm_client import get_llm_client
        text = get_llm_client().generate(full_prompt) or ""

        # LLM may wrap JSON in markdown fences — strip them before parsing
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1)
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start:end + 1]

        parsed = json.loads(text)
        next_agent = parsed.get("next", "")
        reason = parsed.get("reason", "LLM routing decision")

        if next_agent == "DONE" or not next_agent:
            logger.info("LLM router decided DONE: %s", reason)
            return None

        # Validate against registry — LLM may hallucinate agent names
        if next_agent not in all_agent_names:
            logger.warning("LLM suggested unknown agent '%s', falling back", next_agent)
            return None

        if agent_counts.get(next_agent, 0) >= MAX_CALLS_PER_AGENT:
            logger.warning("LLM suggested '%s' but it's at call limit, falling back", next_agent)
            return None

        logger.info("LLM router → %s: %s", next_agent, reason)
        return (next_agent, f"[LLM] {reason}")

    except Exception as e:
        logger.warning("LLM routing failed (%s), using rule-based fallback", e)
        return None


def _rule_based_route(state: AgentState) -> Optional[Tuple[str, str]]:
    """Registry-driven deterministic routing based on signal domains."""
    signals_map = state.get("signals_map", {})
    resources = state.get("resources", [])
    agent_counts = state.get("agent_call_counts", {})
    findings = state.get("findings", {})

    resource_types = {r.get("resource_id"): r.get("type") for r in resources}

    # Group extracted signal names by service type (EC2, S3, etc.)
    signals_by_service: Dict[str, set] = {}
    for rid, signals in signals_map.items():
        rtype = resource_types.get(rid)
        if rtype:
            sig_names = {s.name for s in signals}
            signals_by_service.setdefault(rtype, set()).update(sig_names)

    candidates: List[Tuple[str, str, int]] = []

    for service_type, service_signals in signals_by_service.items():
        if not service_signals:
            continue
        service = registry.get_service(service_type)
        if not service:
            continue

        service_agent_names = set(service.agents.keys())

        for agent_name, agent_def in service.agents.items():
            if agent_counts.get(agent_name, 0) >= MAX_CALLS_PER_AGENT:
                continue

            # Root-cause agents only run after domain agents have produced
            # findings AND there are >=2 signals — they need enough data
            # to perform meaningful causal correlation.
            if agent_def.is_root_cause:
                has_findings = any(
                    bool(findings.get(a)) for a in service_agent_names
                )
                if not has_findings or len(service_signals) < 2:
                    continue

            # Skip agents whose routing_signals don't intersect with
            # the signals actually extracted for this service.
            if agent_def.routing_signals:
                if not (service_signals & agent_def.routing_signals):
                    continue

            candidates.append((
                agent_name,
                agent_def.description,
                agent_def.routing_priority,
            ))

    if not candidates:
        return None

    # Higher priority runs first (e.g. ec2_metric=10 before ec2_security=6)
    candidates.sort(key=lambda c: c[2], reverse=True)
    return (candidates[0][0], f"[Rule] {candidates[0][1]}")


# ---------------------------------------------------------------------------
# Sub-agent node — generic wrapper for all service-specific agents
# ---------------------------------------------------------------------------
# Every sub-agent node (ec2_metric, s3_cost, dynamodb_capacity, etc.)
# calls this same function with a different agent_name. The wrapper:
#   1. Looks up the agent function from registry (lazy import)
#   2. Filters resources to only this agent's service type
#   3. Builds curated context (relevant signals, prior recs, cross-agent
#      findings) via build_agent_context() — the agent never sees raw
#      telemetry or irrelevant signals
#   4. Calls the agent function and collects recommendations
#   5. Converts Recommendation objects to dicts via the service's
#      to_legacy_dict() converter
#   6. Merges results into state (findings, call counts, trace)

def _run_sub_agent_node(state: AgentState, agent_name: str) -> dict:
    agent_def = registry.get_agent_definition(agent_name)
    service = registry.get_service_for_agent(agent_name)
    if not agent_def or not service:
        logger.error("Unknown agent %s — not in registry", agent_name)
        return {}

    service_type = service.service_type
    agent_fn = registry.load_agent_function(agent_name)

    bundles = state.get("telemetry_bundles", {})
    signals_map = state.get("signals_map", {})
    findings = state.get("findings", {})
    decisions = state.get("decisions", [])
    resources = [
        r for r in state.get("resources", [])
        if r.get("type") == service_type and not r.get("recommendations")
    ]

    cross_findings = build_cross_agent_summary(findings, agent_name)

    all_prior_recs: List[Dict[str, Any]] = []
    for recs_list in findings.values():
        all_prior_recs.extend(recs_list)

    recs: List[Dict[str, Any]] = []
    for resource in resources:
        rid = resource.get("resource_id", "")
        bundle = bundles.get(rid)
        signals = signals_map.get(rid, [])
        if not bundle:
            continue

        signal_dicts = [
            {
                "name": s.name,
                "severity": s.severity.value if hasattr(s.severity, "value") else str(s.severity),
                "confidence": s.confidence,
                "description": s.description,
            }
            for s in signals
        ]
        agent_context = build_agent_context(
            agent_id=agent_name,
            signals=signal_dicts,
            resource=resource,
            prior_recommendations=all_prior_recs,
            session_decisions=decisions,
            cross_agent_findings=cross_findings,
        )

        start = time.time()
        try:
            result = agent_fn(bundle, signals, context=agent_context)
            for rec in result:
                rec_dict = _to_dict(rec, service_type, rid)
                recs.append(rec_dict)
        except TypeError:
            # Backward compat: older agent functions don't accept `context`
            try:
                result = agent_fn(bundle, signals)
                for rec in result:
                    rec_dict = _to_dict(rec, service_type, rid)
                    recs.append(rec_dict)
            except Exception as e:
                logger.error("%s failed for %s: %s", agent_name, rid, e)
        except Exception as e:
            logger.error("%s failed for %s: %s", agent_name, rid, e)
        elapsed = (time.time() - start) * 1000
        logger.info("%s processed %s in %.0fms — %d recs",
                    agent_name, rid, elapsed, len(recs))

    new_findings = dict(findings)
    existing = new_findings.get(agent_name, [])
    new_findings[agent_name] = existing + recs

    counts = dict(state.get("agent_call_counts", {}))
    counts[agent_name] = counts.get(agent_name, 0) + 1

    return {
        "findings": new_findings,
        "agent_call_counts": counts,
        "agent_trace": [_trace_step(agent_name, len(recs), state)],
        "messages": [_message(agent_name, "supervisor",
                              f"Analyzed {len(resources)} {service_type} resources — "
                              f"{len(recs)} recommendations (context: {len(cross_findings)} cross-agent findings)")],
    }


def _to_dict(rec: Any, service_type: str, resource_id: str) -> Dict[str, Any]:
    if isinstance(rec, dict):
        rec.setdefault("resource_id", resource_id)
        return rec

    to_legacy = registry.load_report_converter(service_type)
    if to_legacy:
        d = to_legacy(rec)
        d["resource_id"] = resource_id
        return d

    return {"resource_id": resource_id}

##factory functions 
def _make_sub_agent_node(agent_name: str):
    """Factory: create a LangGraph node function for a registered agent."""
    def node_fn(state: AgentState) -> dict:
        return _run_sub_agent_node(state, agent_name)
    # LangGraph uses __name__ for tracing and LangSmith spans
    node_fn.__name__ = agent_name
    node_fn.__qualname__ = agent_name
    return node_fn


# ---------------------------------------------------------------------------
# Safety + Rank
# ---------------------------------------------------------------------------

def safety_and_rank(state: AgentState) -> dict:
    findings = state.get("findings", {})
    resources = state.get("resources", [])
    all_recs: List[Dict[str, Any]] = []

    for agent_name, recs in findings.items():
        all_recs.extend(recs)

    for resource in resources:
        existing = resource.get("recommendations")
        if existing:
            for rec in existing:
                rec.setdefault("resource_id", resource.get("resource_id", ""))
            all_recs.extend(existing)

    initial_count = len(all_recs)
    safe_recs = _apply_safety_filters(all_recs, resources)

    logger.info("Safety filter: %d → %d recommendations", initial_count, len(safe_recs))

    return {
        "all_recommendations": safe_recs,
        "messages": [_message("safety_rank", "supervisor",
                              f"Safety filtered {initial_count} → {len(safe_recs)} recommendations")],
    }


def _apply_safety_filters(
    recs: List[Dict[str, Any]],
    resources: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    # Drop low-confidence and evidence-free recs, then dedup by keeping
    # the highest-confidence rec per (resource_id, rule_id) pair.
    MIN_CONFIDENCE = 0.4
    seen_rules: Dict[str, Dict[str, Any]] = {}

    for rec in recs:
        if not rec.get("evidence") and not rec.get("supporting_signals"):
            continue
        if rec.get("confidence", 0) < MIN_CONFIDENCE:
            continue

        key = f"{rec.get('resource_id', '')}:{rec.get('rule_id', rec.get('title', ''))}"
        existing = seen_rules.get(key)
        if existing and existing.get("confidence", 0) >= rec.get("confidence", 0):
            continue
        seen_rules[key] = rec

    return list(seen_rules.values())


# ---------------------------------------------------------------------------
# Critique — quality review of recommendations
# ---------------------------------------------------------------------------
# Runs both rule-based and LLM checks on all recommendations:
#   - Rule-based: missing evidence, low confidence, duplicate types,
#     high-severity recs without rollback plans or actionable steps
#   - LLM: contradictions, unrealistic savings, cascade risks,
#     missing context, prioritization gaps
# Issues found here feed into the refine node (next step).

def critique(state: AgentState) -> dict:
    recommendations = state.get("all_recommendations", [])
    if not recommendations:
        return {
            "critique_results": {"reviewed": True, "critique": [], "summary": "No recommendations to review"},
            "messages": [_message("critique", "supervisor", "No recommendations to review")],
        }

    critiques = _rule_based_critique(recommendations)

    llm_critiques = _llm_critique(recommendations)
    if llm_critiques:
        existing_rules = {c["rule_id"] for c in critiques}
        for lc in llm_critiques:
            if lc.get("rule_id") not in existing_rules:
                critiques.append(lc)

    return {
        "critique_results": {
            "reviewed": True,
            "critique": critiques,
            "summary": f"Reviewed {len(recommendations)} recommendations, {len(critiques)} with issues",
        },
        "messages": [_message("critique", "supervisor",
                              f"Reviewed {len(recommendations)} recs — {len(critiques)} issues found")],
    }


def _rule_based_critique(recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    critiques = []
    seen_types: Dict[str, List[str]] = {}

    for rec in recommendations:
        rule_id = rec.get("rule_id", "unknown")
        issues = []

        if not rec.get("evidence") and not rec.get("supporting_signals"):
            issues.append({"type": "missing_evidence", "detail": "No supporting evidence or signals", "severity": "high"})

        confidence = rec.get("confidence", 0)
        if confidence < 0.5:
            issues.append({"type": "low_confidence", "detail": f"Confidence {confidence:.2f} below threshold", "severity": "medium"})

        rec_type = rec.get("type", "")
        if rec_type in seen_types:
            for other_id in seen_types[rec_type]:
                issues.append({"type": "potential_conflict", "detail": f"Multiple {rec_type} recs: {other_id} and {rule_id}", "severity": "low"})
        seen_types.setdefault(rec_type, []).append(rule_id)

        sev = (rec.get("severity") or "").lower()
        if sev in ("critical", "high"):
            if not rec.get("rollback"):
                issues.append({"type": "missing_rollback", "detail": "High-severity rec without rollback plan", "severity": "medium"})
            if not rec.get("solution_steps"):
                issues.append({"type": "missing_steps", "detail": "High-severity rec without actionable steps", "severity": "medium"})

        if issues:
            critiques.append({"rule_id": rule_id, "title": rec.get("title", ""), "issues": issues})

    return critiques


def _llm_critique(recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(recommendations) == 0:
        return []

    rec_summary = []
    for rec in recommendations[:15]:
        rec_summary.append({
            "rule_id": rec.get("rule_id", ""),
            "title": rec.get("title", ""),
            "type": rec.get("type", ""),
            "severity": rec.get("severity", ""),
            "confidence": rec.get("confidence", 0),
            "description": (rec.get("description") or "")[:200],
            "has_evidence": bool(rec.get("evidence") or rec.get("supporting_signals")),
            "has_rollback": bool(rec.get("rollback")),
            "has_steps": bool(rec.get("solution_steps")),
            "estimated_savings": rec.get("estimated_savings", "N/A"),
        })

    prompt = (
        "You are a senior cloud architect reviewing optimization recommendations.\n\n"
        "Review these recommendations for quality issues:\n"
        f"{json.dumps(rec_summary, indent=2, default=str)}\n\n"
        "Look for:\n"
        "1. Contradictions between recommendations (e.g. 'stop instance' + 'upgrade instance')\n"
        "2. Missing context that would change the recommendation\n"
        "3. Unrealistic savings estimates\n"
        "4. Recommendations that could cause cascading failures if applied together\n"
        "5. Missing prioritization (which should be done first?)\n\n"
        "Return STRICT JSON array. Each element:\n"
        '{"rule_id": "...", "issue_type": "contradiction|unrealistic|cascade_risk|missing_context", '
        '"detail": "one sentence", "severity": "high|medium|low"}\n\n'
        "Return [] if no issues found. No markdown, no explanations."
    )

    try:
        from agent.llm.llm_client import get_llm_client
        text = get_llm_client().generate(prompt) or ""

        fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1)
        else:
            start = text.find("[")
            end = text.rfind("]")
            if start >= 0 and end > start:
                text = text[start:end + 1]

        parsed = json.loads(text)
        if not isinstance(parsed, list):
            return []

        critiques = []
        for item in parsed:
            critiques.append({
                "rule_id": item.get("rule_id", "unknown"),
                "title": "",
                "issues": [{
                    "type": item.get("issue_type", "llm_quality_check"),
                    "detail": item.get("detail", ""),
                    "severity": item.get("severity", "medium"),
                    "source": "llm",
                }],
            })
        return critiques

    except Exception as e:
        logger.warning("LLM critique failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Refine — apply critique feedback to recommendations
# ---------------------------------------------------------------------------
# For each critiqued recommendation, applies targeted fixes:
#   - low_confidence     → penalize confidence score
#   - missing_rollback   → add generic rollback plan
#   - missing_evidence   → penalize confidence score harder
#   - contradiction      → penalize confidence + add warning
#   - cascade_risk       → add warning + mark manual_only
#   - unrealistic        → reset estimated_savings to "Needs verification"
# After refinement, clears critique results so supervisor doesn't loop.

def refine(state: AgentState) -> dict:
    recommendations = list(state.get("all_recommendations", []))
    critique_data = state.get("critique_results", {})
    critiqued_rules = {c["rule_id"] for c in critique_data.get("critique", [])}

    refined_count = 0
    for rec in recommendations:
        rule_id = rec.get("rule_id", "")
        if rule_id not in critiqued_rules:
            continue

        issues = []
        for c in critique_data.get("critique", []):
            if c["rule_id"] == rule_id:
                issues = c.get("issues", [])
                break

        for issue in issues:
            issue_type = issue.get("type", "")
            if issue_type == "low_confidence":
                rec["confidence"] = max(0, rec.get("confidence", 0) - 0.1)
                refined_count += 1
            elif issue_type == "missing_rollback":
                rec["rollback"] = rec.get("rollback") or "Reverse the applied action manually."
                refined_count += 1
            elif issue_type == "missing_evidence":
                rec["confidence"] = max(0, rec.get("confidence", 0) - 0.15)
                refined_count += 1
            elif issue_type == "contradiction":
                rec["confidence"] = max(0, rec.get("confidence", 0) - 0.2)
                rec.setdefault("warnings", []).append(issue.get("detail", "Contradicts another recommendation"))
                refined_count += 1
            elif issue_type == "cascade_risk":
                rec.setdefault("warnings", []).append(issue.get("detail", "May cause cascading failures"))
                rec["manual_only"] = True
                refined_count += 1
            elif issue_type == "unrealistic":
                rec["estimated_savings"] = "Needs verification"
                refined_count += 1

    return {
        "all_recommendations": recommendations,
        "critique_results": {"reviewed": True, "critique": [], "summary": "Refinement applied"},
        "decisions": [_decision("refine", "apply_critique_feedback",
                                f"Refined {refined_count} recommendations based on critique")],
        "messages": [_message("refine", "supervisor", f"Applied {refined_count} refinements")],
    }


# ---------------------------------------------------------------------------
# Correlate — cross-resource pattern detection
# ---------------------------------------------------------------------------
# Looks for patterns that span multiple resources:
#   Rule-based: idle resource clusters, recurring security gaps,
#     co-located resources in the same service tag
#   LLM: dependencies, cascade risks, amplified savings,
#     shared root causes across different resources/services
# Only runs when there are 2+ resources to correlate.

def correlate(state: AgentState) -> dict:
    resources = state.get("resources", [])
    all_recs = state.get("all_recommendations", [])
    findings = state.get("findings", {})
    correlations = []

    correlations.extend(_rule_based_correlations(resources, all_recs))

    llm_correlations = _llm_correlate(resources, all_recs, findings)
    if llm_correlations:
        correlations.extend(llm_correlations)

    return {
        "correlations": correlations,
        "messages": [_message("correlation", "supervisor",
                              f"Found {len(correlations)} cross-resource patterns")],
        "decisions": [_decision("correlation", "cross_resource_analysis",
                                f"Detected {len(correlations)} patterns across {len(resources)} resources")],
    }


def _rule_based_correlations(
    resources: List[Dict[str, Any]],
    all_recs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    correlations = []

    idle_recs = [r for r in all_recs if "idle" in (r.get("title") or "").lower()]
    if len(idle_recs) >= 2:
        total_savings = sum(
            float(r.get("saving", 0) or r.get("estimated_savings", 0) or 0)
            for r in idle_recs
            if isinstance(r.get("saving", r.get("estimated_savings")), (int, float))
        )
        correlations.append({
            "type": "compound_savings",
            "title": "Multiple idle resources — combined savings opportunity",
            "description": f"{len(idle_recs)} idle resources detected across services",
            "combined_savings": total_savings,
            "confidence": 0.85,
            "source": "rule",
        })

    security_recs = [r for r in all_recs if r.get("type") == "security"]
    title_counts: Dict[str, int] = {}
    for r in security_recs:
        title = r.get("title", "")
        title_counts[title] = title_counts.get(title, 0) + 1
    for title, count in title_counts.items():
        if count >= 2:
            correlations.append({
                "type": "security_pattern",
                "title": f"Recurring security gap: {title}",
                "description": f"{count} resources share the same security issue",
                "confidence": 0.9,
                "source": "rule",
            })

    by_service: Dict[str, List[str]] = {}
    for r in resources:
        svc = (r.get("tags") or {}).get("Service", "")
        if svc:
            by_service.setdefault(svc, []).append(r.get("resource_id", ""))
    for svc, rids in by_service.items():
        if len(rids) >= 2:
            svc_recs = [r for r in all_recs if r.get("resource_id") in rids]
            if svc_recs:
                correlations.append({
                    "type": "service_dependency",
                    "title": f"Co-located resources in service '{svc}'",
                    "description": f"{len(rids)} resources tagged to same service",
                    "resources_involved": rids,
                    "recommendation_count": len(svc_recs),
                    "confidence": 0.7,
                    "source": "rule",
                })

    return correlations


def _llm_correlate(
    resources: List[Dict[str, Any]],
    all_recs: List[Dict[str, Any]],
    findings: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    if len(resources) < 2 or len(all_recs) < 2:
        return []

    context = build_correlation_context(findings, resources)

    rec_summary = []
    for rec in all_recs[:20]:
        rec_summary.append({
            "resource_id": rec.get("resource_id", ""),
            "title": rec.get("title", ""),
            "type": rec.get("type", ""),
            "severity": rec.get("severity", ""),
            "estimated_savings": str(rec.get("estimated_savings", "N/A")),
        })

    resource_summary = []
    for r in resources[:10]:
        resource_summary.append({
            "resource_id": r.get("resource_id", ""),
            "type": r.get("type", ""),
            "status": r.get("status", ""),
            "monthly_cost": r.get("monthly_cost", "N/A"),
            "tags": r.get("tags", {}),
        })

    prompt = (
        "You are a senior cloud architect analyzing cross-resource optimization patterns.\n\n"
        f"Resources:\n{json.dumps(resource_summary, indent=2, default=str)}\n\n"
        f"Recommendations found:\n{json.dumps(rec_summary, indent=2, default=str)}\n\n"
        "Find non-obvious patterns:\n"
        "1. Dependencies: resources that should be optimized together\n"
        "2. Cascading risks: one change that could break another resource\n"
        "3. Amplified savings: optimizations that compound when done together\n"
        "4. Shared root causes: different symptoms across resources from the same issue\n\n"
        "Return STRICT JSON array. Each element:\n"
        '{"type": "dependency|cascade_risk|amplified_savings|shared_root_cause", '
        '"title": "short title", "description": "one sentence", '
        '"resources_involved": ["id1", "id2"], "confidence": 0.7}\n\n'
        "Return [] if no patterns found. No markdown, no explanations."
    )

    try:
        from agent.llm.llm_client import get_llm_client
        text = get_llm_client().generate(prompt) or ""

        fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1)
        else:
            start = text.find("[")
            end = text.rfind("]")
            if start >= 0 and end > start:
                text = text[start:end + 1]

        parsed = json.loads(text)
        if not isinstance(parsed, list):
            return []

        correlations = []
        for item in parsed:
            correlations.append({
                "type": item.get("type", "unknown"),
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "resources_involved": item.get("resources_involved", []),
                "confidence": float(item.get("confidence", 0.6)),
                "source": "llm",
            })
        return correlations

    except Exception as e:
        logger.warning("LLM correlation failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Verify — run guardrail gates before final output
# ---------------------------------------------------------------------------
# Each recommendation passes through verification gates (defined in
# guardrails.py). Recommendations that fail any gate are dropped.
# Surviving recs get a verification stamp with gate pass/review counts.

def verify(state: AgentState) -> dict:
    all_recs = state.get("all_recommendations", [])
    messages = state.get("messages", [])

    gates = []
    depth_gate = verify_conversation_depth(len(messages))
    gates.append(depth_gate.to_dict())

    verified = []
    dropped = 0
    for rec in all_recs:
        rec_gates = run_all_gates(rec)
        for g in rec_gates:
            gates.append(g.to_dict())

        from agent.core.types import VerificationResult
        failed = any(g.result == VerificationResult.FAILED for g in rec_gates)
        if not failed:
            rec["verification"] = {
                "gates_passed": sum(1 for g in rec_gates if g.result == VerificationResult.PASSED),
                "gates_review": sum(1 for g in rec_gates if g.result == VerificationResult.NEEDS_REVIEW),
                "verified_at": time.time(),
            }
            verified.append(rec)
        else:
            dropped += 1
            logger.info("Recommendation %s dropped by verification gate", rec.get("rule_id", "unknown"))

    return {
        "recommendations": verified,
        "verification_gates": gates,
        "decisions": [_decision("verify", "verification_gates",
                                f"Verified {len(verified)}/{len(all_recs)} passed, {dropped} dropped")],
        "messages": [_message("verify", "supervisor",
                              f"{len(verified)} recommendations passed verification")],
    }


# ---------------------------------------------------------------------------
# Evaluate — terminal node (quality metrics + session persistence)
# ---------------------------------------------------------------------------
# Final node in the pipeline. Computes quality scores per resource,
# persists the session state and snapshot to agent_memory, and sets
# next_action="__end__" so the graph terminates. This is the only node
# with a direct edge to END (not back to supervisor).

def evaluate(state: AgentState) -> dict:
    recommendations = state.get("recommendations", [])
    resources = state.get("resources", [])

    for resource in resources:
        resource_recs = [
            r for r in recommendations
            if r.get("resource_id") == resource.get("resource_id") or not r.get("resource_id")
        ]
        if resource_recs:
            evaluation_engine.evaluate_recommendations(resource_recs, [], resource)

    session_id = state.get("session_id", "")
    agent_memory.store_session_state(session_id, {
        "session_id": session_id,
        "status": "completed",
        "recommendation_count": len(recommendations),
        "resource_count": len(resources),
    })
    agent_memory.store_session_snapshot(session_id, {
        "session_id": session_id,
        "recommendation_count": len(recommendations),
        "status": "completed",
        "resource_count": len(resources),
    })

    return {
        "status": "completed",
        "next_action": "__end__",
        "decisions": [_decision("evaluate", "quality_metrics",
                                f"Evaluated {len(recommendations)} recommendations across {len(resources)} resources")],
        "messages": [_message("evaluate", "supervisor",
                              f"Evaluation complete — {len(recommendations)} final recommendations")],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decision(agent: str, action: str, reasoning: str) -> Dict[str, Any]:
    return {
        "agent": agent,
        "action": action,
        "reasoning": reasoning,
        "timestamp": time.time(),
    }


def _message(from_agent: str, to_agent: str, content: str) -> Dict[str, Any]:
    return {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "content": content,
        "timestamp": time.time(),
    }


def _trace_step(agent_name: str, finding_count: int, state: AgentState) -> Dict[str, Any]:
    signals_map = state.get("signals_map", {})
    all_signal_names = []
    for sigs in signals_map.values():
        all_signal_names.extend(s.name for s in sigs)
    return {
        "agent": agent_name,
        "findings": finding_count,
        "signals_seen": list(set(all_signal_names)),
        "timestamp": time.time(),
    }


# ---------------------------------------------------------------------------
# Dynamic sub-agent node map — built from registry at import time.
# graph.py reads this dict to register LangGraph nodes and conditional edges.
# ---------------------------------------------------------------------------

SUB_AGENT_NODES = {
    name: _make_sub_agent_node(name)
    for name in registry.get_all_agent_names()
}
