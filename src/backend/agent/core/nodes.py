"""
LangGraph node functions for the unified multi-agent orchestrator.

Pipeline nodes (in execution order):
  1. collect_telemetry  — build TelemetryBundle per resource
  2. extract_signals    — extract intelligence signals from bundles
  3. supervisor         — LLM + rule-based router decides next sub-agent
  4. Sub-agent nodes    — per-service specialist agents (context-aware)
  5. safety_and_rank    — guardrails + dedup + priority ordering
  6. critique           — LLM quality review of recommendations
  7. refine             — apply critique feedback
  8. correlate          — LLM cross-resource pattern detection
  9. verify             — verification gates
 10. evaluate           — quality metrics + session persistence

Sub-agent nodes (each wraps existing agent functions):
  EC2:      ec2_metric, ec2_cost, ec2_reliability, ec2_security, ec2_root_cause
  S3:       s3_storage, s3_cost, s3_reliability, s3_security, s3_access, s3_root_cause
  DynamoDB: dynamodb_capacity, dynamodb_performance, dynamodb_reliability, dynamodb_root_cause
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
from agent.core.context import (
    build_agent_context,
    build_cross_agent_summary,
    build_critique_context,
    build_correlation_context,
    SIGNAL_DOMAIN_MAP,
)

logger = logging.getLogger(__name__)

MAX_REFINEMENT_ITERATIONS = 2
MAX_CALLS_PER_AGENT = 2

# Signal-domain mapping for rule-based routing (from complex_orchestrator)
_EC2_COST_SIGNALS = {
    "instance_idle_high_cost", "cpu_sustained_low",
    "graviton_migration_candidate", "spot_candidate", "cpu_bursty",
}
_EC2_RELIABILITY_SIGNALS = {
    "status_check_failures", "reboot_loop_detected",
    "no_autoscaling", "single_az_deployment",
}
_EC2_SECURITY_SIGNALS = {
    "imdsv1_in_use", "ebs_unencrypted",
    "ssh_rdp_open_to_world", "ami_outdated",
}
_EC2_METRIC_SIGNALS = {
    "cpu_sustained_high", "memory_pressure_detected",
    "swap_exhaustion", "oom_killed", "ebs_burst_balance_low",
    "network_saturation_detected",
}

# All sub-agent names the supervisor can route to
_ALL_SUB_AGENTS = [
    "ec2_metric", "ec2_cost", "ec2_reliability", "ec2_security", "ec2_root_cause",
    "s3_storage", "s3_cost", "s3_reliability", "s3_security", "s3_access", "s3_root_cause",
    "dynamodb_capacity", "dynamodb_performance", "dynamodb_reliability", "dynamodb_root_cause",
]

# LLM router system prompt
_ROUTER_SYSTEM = """You are an intelligent orchestration router for an AWS cloud optimization agent system.
Your job: given current signals, findings from agents that have already run, and call counts, decide which specialist agent to invoke next.

Available agents:
- ec2_metric              : CPU/memory/network/EBS threshold violations and trends
- ec2_cost                : Idle instances, rightsizing, Graviton, Spot, ASG savings
- ec2_reliability         : Health check failures, single-AZ, missing ASG
- ec2_security            : IMDSv2 gaps, unencrypted EBS, open SSH/RDP, outdated AMIs
- ec2_root_cause          : LLM-powered causal correlation of signals+events (call only when >=2 signals AND >=1 finding exist for EC2)
- s3_storage              : Storage utilization anomalies, small object overhead
- s3_cost                 : Lifecycle policies, tiering, cold storage opportunities
- s3_reliability          : Versioning, replication, access logging gaps
- s3_security             : Public access risks, encryption gaps
- s3_access               : Retrieval spikes, transfer cost anomalies
- s3_root_cause           : LLM-powered causal analysis for S3 (call only when >=2 S3 signals exist)
- dynamodb_capacity       : Over/under provisioned RCU/WCU, on-demand vs provisioned
- dynamodb_performance    : Throttling, hot partitions, retry storms
- dynamodb_reliability    : PITR, replication lag, backups
- dynamodb_root_cause     : LLM-powered causal analysis for DynamoDB (call only when >=2 DynamoDB signals exist)

Routing rules:
1. For EC2: start with ec2_metric (baseline), then route based on signal domains
2. Root-cause agents should only run after domain agents have produced findings
3. Respond DONE when all relevant signal domains are covered
4. Never suggest an agent that has reached its call limit (max 2 calls each)
5. Prioritize agents whose signal domains have the most unaddressed signals
6. Consider cross-agent findings — if one agent found issues, related agents may find more

Respond ONLY with valid JSON: {"next": "<agent_name_or_DONE>", "reason": "<one concise sentence>"}"""


# ---------------------------------------------------------------------------
# Collect Telemetry
# ---------------------------------------------------------------------------

def collect_telemetry(state: AgentState) -> dict:
    resources = state.get("resources", [])
    bundles: Dict[str, Any] = {}

    for resource in resources:
        if resource.get("recommendations"):
            continue
        rid = resource.get("resource_id", "")
        rtype = resource.get("type")
        try:
            if rtype == "EC2":
                from agent.ec2_agent.telemetry import collect_from_resource, normalize
                bundles[rid] = normalize(collect_from_resource(resource))
            elif rtype == "S3":
                from agent.s3_agent.telemetry import (
                    collect_from_resource as s3_collect,
                    normalize as s3_normalize,
                )
                bundles[rid] = s3_normalize(s3_collect(resource))
            elif rtype == "DynamoDB":
                from agent.dynamodb_agent.telemetry import (
                    collect_from_resource as ddb_collect,
                    normalize as ddb_normalize,
                )
                bundles[rid] = ddb_normalize(ddb_collect(resource))
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

def extract_signals(state: AgentState) -> dict:
    bundles = state.get("telemetry_bundles", {})
    resources = state.get("resources", [])
    signals_map: Dict[str, List[Any]] = {}
    resource_types = {r.get("resource_id"): r.get("type") for r in resources}

    for rid, bundle in bundles.items():
        rtype = resource_types.get(rid)
        try:
            if rtype == "EC2":
                from agent.ec2_agent.signals import extract_signals as ec2_extract
                signals_map[rid] = ec2_extract(bundle)
            elif rtype == "S3":
                from agent.s3_agent.signals import extract_signals as s3_extract
                signals_map[rid] = s3_extract(bundle)
            elif rtype == "DynamoDB":
                from agent.dynamodb_agent.signals import extract_signals as ddb_extract
                signals_map[rid] = ddb_extract(bundle)
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
# Supervisor — LLM + rule-based dynamic router
# ---------------------------------------------------------------------------

def supervisor(state: AgentState) -> dict:
    findings = state.get("findings", {})
    has_findings = any(bool(v) for v in findings.values())
    agent_counts = state.get("agent_call_counts", {})
    has_critique = bool(state.get("critique_results", {}).get("reviewed"))
    critique_issues = state.get("critique_results", {}).get("critique", [])
    has_correlations = bool(state.get("correlations"))
    has_verified = bool(state.get("recommendations"))
    iteration = state.get("iteration", 0)
    resources = state.get("resources", [])

    # Phase: collect telemetry
    if not state.get("telemetry_bundles"):
        return {
            "next_action": "collect_telemetry",
            "phase": "telemetry",
            "decisions": [_decision("supervisor", "start_telemetry",
                                    f"Starting telemetry collection for {len(resources)} resources")],
        }

    # Phase: extract signals
    if not state.get("signals_map"):
        return {
            "next_action": "extract_signals",
            "phase": "signals",
            "decisions": [_decision("supervisor", "start_signals",
                                    "Telemetry ready — extracting intelligence signals")],
        }

    # Phase: run sub-agents (LLM-powered routing with rule-based fallback)
    next_agent = _route_next_sub_agent(state)
    if next_agent:
        return {
            "next_action": next_agent[0],
            "phase": "sub_agents",
            "decisions": [_decision("supervisor", "route_sub_agent",
                                    next_agent[1])],
        }

    # Phase: safety + rank
    if has_findings and not state.get("all_recommendations"):
        return {
            "next_action": "safety_and_rank",
            "phase": "safety",
            "decisions": [_decision("supervisor", "run_safety",
                                    "Sub-agents complete — running safety filter and ranking")],
        }

    # Phase: critique
    if state.get("all_recommendations") and not has_critique:
        return {
            "next_action": "critique",
            "phase": "critique",
            "decisions": [_decision("supervisor", "request_critique",
                                    "Recommendations ready — requesting quality review")],
        }

    # Phase: refine (if critique found issues)
    if critique_issues and iteration < MAX_REFINEMENT_ITERATIONS:
        return {
            "next_action": "refine",
            "phase": "refine",
            "iteration": iteration + 1,
            "decisions": [_decision("supervisor", "request_refinement",
                                    f"Critique found {len(critique_issues)} issues — refining (iteration {iteration + 1})")],
        }

    # Phase: correlate
    if not has_correlations and len(resources) > 1:
        return {
            "next_action": "correlate",
            "phase": "correlate",
            "decisions": [_decision("supervisor", "request_correlation",
                                    f"Checking cross-resource patterns across {len(resources)} resources")],
        }

    # Phase: verify
    if not has_verified:
        return {
            "next_action": "verify",
            "phase": "verify",
            "decisions": [_decision("supervisor", "run_verification",
                                    "Running verification gates on recommendations")],
        }

    # Phase: evaluate → done
    return {
        "next_action": "evaluate",
        "phase": "evaluate",
        "decisions": [_decision("supervisor", "run_evaluation",
                                "Final evaluation and quality metrics")],
    }


# ---------------------------------------------------------------------------
# LLM-powered sub-agent routing
# ---------------------------------------------------------------------------

def _route_next_sub_agent(state: AgentState) -> Optional[Tuple[str, str]]:
    """
    Pick the next sub-agent using LLM routing with rule-based fallback.
    The LLM sees signals, findings, and call counts to make nuanced decisions.
    """
    # Try LLM routing first
    llm_result = _llm_route(state)
    if llm_result is not None:
        return llm_result

    # Fall back to deterministic rule-based routing
    return _rule_based_route(state)


def _llm_route(state: AgentState) -> Optional[Tuple[str, str]]:
    """LLM-powered routing decision. Returns None on failure (triggers fallback)."""
    signals_map = state.get("signals_map", {})
    resources = state.get("resources", [])
    agent_counts = state.get("agent_call_counts", {})
    findings = state.get("findings", {})

    resource_types = {r.get("resource_id"): r.get("type") for r in resources}

    # Build signal summary for the LLM
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

    # Build finding summary
    finding_summary = []
    for agent_name, recs in findings.items():
        for rec in recs[:5]:
            finding_summary.append({
                "from_agent": agent_name,
                "rule_id": rec.get("rule_id", ""),
                "type": rec.get("type", ""),
                "severity": rec.get("severity", ""),
            })

    # Available agents (not at call limit)
    available = [
        name for name in _ALL_SUB_AGENTS
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

    full_prompt = _ROUTER_SYSTEM + "\n\n" + user_msg

    try:
        from agent.llm.llm_client import get_llm_client
        text = get_llm_client().generate(full_prompt) or ""

        # Extract JSON from response
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

        if next_agent not in _ALL_SUB_AGENTS:
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
    """Deterministic fallback routing based on signal domains and call counts."""
    signals_map = state.get("signals_map", {})
    resources = state.get("resources", [])
    agent_counts = state.get("agent_call_counts", {})
    findings = state.get("findings", {})

    resource_types = {r.get("resource_id"): r.get("type") for r in resources}

    ec2_signals: set = set()
    s3_signals: set = set()
    ddb_signals: set = set()
    for rid, signals in signals_map.items():
        rtype = resource_types.get(rid)
        sig_names = {s.name for s in signals}
        if rtype == "EC2":
            ec2_signals |= sig_names
        elif rtype == "S3":
            s3_signals |= sig_names
        elif rtype == "DynamoDB":
            ddb_signals |= sig_names

    candidates: List[Tuple[str, str, int]] = []

    if ec2_signals:
        candidates.extend(_ec2_routing_candidates(ec2_signals, agent_counts, state))

    if s3_signals:
        s3_agents = [
            ("s3_storage", "S3 storage utilization analysis"),
            ("s3_cost", "S3 cost optimization analysis"),
            ("s3_reliability", "S3 reliability analysis"),
            ("s3_security", "S3 security analysis"),
            ("s3_access", "S3 access pattern analysis"),
            ("s3_root_cause", "S3 workload intelligence analysis"),
        ]
        for name, desc in s3_agents:
            if agent_counts.get(name, 0) < MAX_CALLS_PER_AGENT:
                priority = 1
                if name == "s3_root_cause":
                    has_s3_findings = any(bool(v) for k, v in findings.items() if k.startswith("s3_"))
                    if not has_s3_findings or len(s3_signals) < 2:
                        continue
                candidates.append((name, desc, priority))

    if ddb_signals:
        ddb_agents = [
            ("dynamodb_capacity", "DynamoDB capacity optimization analysis"),
            ("dynamodb_performance", "DynamoDB performance analysis"),
            ("dynamodb_reliability", "DynamoDB reliability analysis"),
            ("dynamodb_root_cause", "DynamoDB workload intelligence analysis"),
        ]
        for name, desc in ddb_agents:
            if agent_counts.get(name, 0) < MAX_CALLS_PER_AGENT:
                if name == "dynamodb_root_cause":
                    has_ddb_findings = any(bool(v) for k, v in findings.items() if k.startswith("dynamodb_"))
                    if not has_ddb_findings or len(ddb_signals) < 2:
                        continue
                candidates.append((name, desc, 1))

    if not candidates:
        return None

    candidates.sort(key=lambda c: c[2], reverse=True)
    return (candidates[0][0], f"[Rule] {candidates[0][1]}")


def _ec2_routing_candidates(
    signal_names: set,
    agent_counts: Dict[str, int],
    state: AgentState,
) -> List[Tuple[str, str, int]]:
    candidates = []
    findings = state.get("findings", {})

    if agent_counts.get("ec2_metric", 0) < MAX_CALLS_PER_AGENT:
        candidates.append(("ec2_metric", "Baseline metric analysis for EC2 resources", 10))

    if signal_names & _EC2_COST_SIGNALS and agent_counts.get("ec2_cost", 0) < MAX_CALLS_PER_AGENT:
        candidates.append(("ec2_cost",
                           f"Cost signals detected: {signal_names & _EC2_COST_SIGNALS}", 8))

    if signal_names & _EC2_RELIABILITY_SIGNALS and agent_counts.get("ec2_reliability", 0) < MAX_CALLS_PER_AGENT:
        candidates.append(("ec2_reliability",
                           f"Reliability signals detected: {signal_names & _EC2_RELIABILITY_SIGNALS}", 7))

    if signal_names & _EC2_SECURITY_SIGNALS and agent_counts.get("ec2_security", 0) < MAX_CALLS_PER_AGENT:
        candidates.append(("ec2_security",
                           f"Security signals detected: {signal_names & _EC2_SECURITY_SIGNALS}", 6))

    has_ec2_findings = any(bool(v) for k, v in findings.items() if k.startswith("ec2_"))
    if (len(signal_names) >= 2 and has_ec2_findings
            and agent_counts.get("ec2_root_cause", 0) < MAX_CALLS_PER_AGENT):
        candidates.append(("ec2_root_cause",
                           "Sufficient signals and findings for causal correlation", 3))

    return candidates


# ---------------------------------------------------------------------------
# Sub-agent nodes — context-aware factory wrappers
# ---------------------------------------------------------------------------

def _run_sub_agent_node(
    state: AgentState,
    agent_name: str,
    service_type: str,
    agent_fn_path: str,
    agent_fn_name: str,
) -> dict:
    """
    Generic wrapper for any sub-agent node.
    Builds curated context from cross-agent findings and passes it
    alongside telemetry and signals so agents can make informed decisions.
    """
    import importlib
    bundles = state.get("telemetry_bundles", {})
    signals_map = state.get("signals_map", {})
    findings = state.get("findings", {})
    decisions = state.get("decisions", [])
    resources = [
        r for r in state.get("resources", [])
        if r.get("type") == service_type and not r.get("recommendations")
    ]

    module = importlib.import_module(agent_fn_path)
    agent_fn = getattr(module, agent_fn_name)

    # Build cross-agent context: what other agents have found
    cross_findings = build_cross_agent_summary(findings, agent_name)

    # Collect all existing recs as prior context
    all_prior_recs = []
    for recs_list in findings.values():
        all_prior_recs.extend(recs_list)

    recs: List[Dict[str, Any]] = []
    for resource in resources:
        rid = resource.get("resource_id", "")
        bundle = bundles.get(rid)
        signals = signals_map.get(rid, [])
        if not bundle:
            continue

        # Build curated context for this agent + resource
        signal_dicts = [
            {"name": s.name, "severity": s.severity.value if hasattr(s.severity, "value") else str(s.severity),
             "confidence": s.confidence, "description": s.description}
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
            # Agent doesn't accept context kwarg yet — call without it
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

    if service_type == "EC2":
        from agent.ec2_agent.report import to_legacy_dict
    elif service_type == "S3":
        from agent.s3_agent.report import to_legacy_dict
    elif service_type == "DynamoDB":
        from agent.dynamodb_agent.report import to_legacy_dict
    else:
        return {"resource_id": resource_id}

    d = to_legacy_dict(rec)
    d["resource_id"] = resource_id
    return d


# --- EC2 sub-agent nodes ---

def ec2_metric(state: AgentState) -> dict:
    return _run_sub_agent_node(state, "ec2_metric", "EC2",
                               "agent.ec2_agent.agents", "metric_analyzer_agent")

def ec2_cost(state: AgentState) -> dict:
    return _run_sub_agent_node(state, "ec2_cost", "EC2",
                               "agent.ec2_agent.agents", "cost_optimization_agent")

def ec2_reliability(state: AgentState) -> dict:
    return _run_sub_agent_node(state, "ec2_reliability", "EC2",
                               "agent.ec2_agent.agents", "reliability_agent")

def ec2_security(state: AgentState) -> dict:
    return _run_sub_agent_node(state, "ec2_security", "EC2",
                               "agent.ec2_agent.agents", "security_agent")

def ec2_root_cause(state: AgentState) -> dict:
    return _run_sub_agent_node(state, "ec2_root_cause", "EC2",
                               "agent.ec2_agent.agents", "root_cause_agent")

# --- S3 sub-agent nodes ---

def s3_storage(state: AgentState) -> dict:
    return _run_sub_agent_node(state, "s3_storage", "S3",
                               "agent.s3_agent.agents", "storage_utilization_agent")

def s3_cost(state: AgentState) -> dict:
    return _run_sub_agent_node(state, "s3_cost", "S3",
                               "agent.s3_agent.agents", "cost_optimization_agent")

def s3_reliability(state: AgentState) -> dict:
    return _run_sub_agent_node(state, "s3_reliability", "S3",
                               "agent.s3_agent.agents", "reliability_agent")

def s3_security(state: AgentState) -> dict:
    return _run_sub_agent_node(state, "s3_security", "S3",
                               "agent.s3_agent.agents", "security_agent")

def s3_access(state: AgentState) -> dict:
    return _run_sub_agent_node(state, "s3_access", "S3",
                               "agent.s3_agent.agents", "access_pattern_agent")

def s3_root_cause(state: AgentState) -> dict:
    return _run_sub_agent_node(state, "s3_root_cause", "S3",
                               "agent.s3_agent.agents", "root_cause_agent")

# --- DynamoDB sub-agent nodes ---

def dynamodb_capacity(state: AgentState) -> dict:
    return _run_sub_agent_node(state, "dynamodb_capacity", "DynamoDB",
                               "agent.dynamodb_agent.agents", "capacity_optimization_agent")

def dynamodb_performance(state: AgentState) -> dict:
    return _run_sub_agent_node(state, "dynamodb_performance", "DynamoDB",
                               "agent.dynamodb_agent.agents", "performance_scalability_agent")

def dynamodb_reliability(state: AgentState) -> dict:
    return _run_sub_agent_node(state, "dynamodb_reliability", "DynamoDB",
                               "agent.dynamodb_agent.agents", "reliability_agent")

def dynamodb_root_cause(state: AgentState) -> dict:
    return _run_sub_agent_node(state, "dynamodb_root_cause", "DynamoDB",
                               "agent.dynamodb_agent.agents", "root_cause_agent")


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
# Critique — LLM-powered quality review
# ---------------------------------------------------------------------------

def critique(state: AgentState) -> dict:
    recommendations = state.get("all_recommendations", [])
    if not recommendations:
        return {
            "critique_results": {"reviewed": True, "critique": [], "summary": "No recommendations to review"},
            "messages": [_message("critique", "supervisor", "No recommendations to review")],
        }

    # Rule-based critique (fast, deterministic)
    critiques = _rule_based_critique(recommendations)

    # LLM critique for deeper quality review
    llm_critiques = _llm_critique(recommendations)
    if llm_critiques:
        # Merge LLM findings with rule-based, avoiding duplicates
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
    """Use LLM to identify quality issues that rule-based checks miss."""
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

        # Extract JSON array
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
# Refine
# ---------------------------------------------------------------------------

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
# Correlate — LLM-powered cross-resource pattern detection
# ---------------------------------------------------------------------------

def correlate(state: AgentState) -> dict:
    resources = state.get("resources", [])
    all_recs = state.get("all_recommendations", [])
    findings = state.get("findings", {})
    correlations = []

    # Rule-based correlations (fast, deterministic)
    correlations.extend(_rule_based_correlations(resources, all_recs))

    # LLM-powered deep correlation analysis
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

    # Compound savings: multiple idle resources
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

    # Recurring security gaps
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

    # Co-located service resources
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
    """Use LLM to find non-obvious cross-resource patterns."""
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
# Verify — verification gates
# ---------------------------------------------------------------------------

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
# Evaluate — quality metrics + session persistence
# ---------------------------------------------------------------------------

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


# All sub-agent node names for graph registration
SUB_AGENT_NODES = {
    "ec2_metric": ec2_metric,
    "ec2_cost": ec2_cost,
    "ec2_reliability": ec2_reliability,
    "ec2_security": ec2_security,
    "ec2_root_cause": ec2_root_cause,
    "s3_storage": s3_storage,
    "s3_cost": s3_cost,
    "s3_reliability": s3_reliability,
    "s3_security": s3_security,
    "s3_access": s3_access,
    "s3_root_cause": s3_root_cause,
    "dynamodb_capacity": dynamodb_capacity,
    "dynamodb_performance": dynamodb_performance,
    "dynamodb_reliability": dynamodb_reliability,
    "dynamodb_root_cause": dynamodb_root_cause,
}
