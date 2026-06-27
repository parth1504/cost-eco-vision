"""
Dynamic multi-agent orchestrator for EC2 resource analysis.

Instead of running every agent in a fixed sequence, an LLM Router decides
at each step which specialist agent to invoke next — based on:
  - signals extracted from telemetry
  - findings accumulated so far
  - which agents have already been called

This makes the system truly agentic:
  - The router can circle back to an agent that already ran if new evidence
    warrants a second look (e.g. root_cause_agent after more signals surface)
  - Agents are skipped entirely when their domain has no relevant signals
  - Every routing decision is logged in the trace for explainability

Explainability trace shape (attached to each recommendation as `agent_trace`):
  [
    {"step": 1, "agent": "metric_analyzer_agent",
     "reason": "Always start with metrics to establish baseline signals",
     "findings": 2, "signals_seen": ["cpu_sustained_low", "ebs_burst_balance_low"]},
    {"step": 2, "agent": "cost_optimization_agent",
     "reason": "cpu_sustained_low + instance_idle_high_cost → cost win available",
     "findings": 1, "signals_seen": [...]},
    ...
  ]
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from agent.ec2_agent.agents import (
    cost_optimization_agent,
    metric_analyzer_agent,
    reliability_agent,
    root_cause_agent,
    security_agent,
)
from agent.ec2_agent.ranker import rank
from agent.ec2_agent.report import to_legacy_dict
from agent.ec2_agent.signals import extract_signals
from agent.ec2_agent.telemetry import collect_from_resource, normalize
from agent.ec2_agent.types import Recommendation, Signal, TelemetryBundle
from agent.llm.llm_client import get_llm_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent registry — every callable specialist available to the router
# ---------------------------------------------------------------------------

AGENT_REGISTRY: Dict[str, Any] = {
    "metric_analyzer_agent":   metric_analyzer_agent,
    "cost_optimization_agent": cost_optimization_agent,
    "reliability_agent":       reliability_agent,
    "security_agent":          security_agent,
    "root_cause_agent":        root_cause_agent,
}

# Signal → domain mapping used by rule-based fallback router
_COST_SIGNALS        = {"instance_idle_high_cost", "cpu_sustained_low",
                        "graviton_migration_candidate", "spot_candidate", "cpu_bursty"}
_RELIABILITY_SIGNALS = {"status_check_failures", "reboot_loop_detected",
                        "no_autoscaling", "single_az_deployment"}
_SECURITY_SIGNALS    = {"imdsv1_in_use", "ebs_unencrypted",
                        "ssh_rdp_open_to_world", "ami_outdated"}
_METRIC_SIGNALS      = {"cpu_sustained_high", "memory_pressure_detected",
                        "swap_exhaustion", "oom_killed", "ebs_burst_balance_low",
                        "network_saturation_detected"}

MAX_STEPS           = 10   # hard ceiling on total agent invocations per run
MAX_CALLS_PER_AGENT = 2    # router can revisit an agent at most this many times


# ---------------------------------------------------------------------------
# Shared context that flows through the whole orchestration run
# ---------------------------------------------------------------------------

@dataclass
class TraceStep:
    step:          int
    agent:         str
    reason:        str          # router's rationale for picking this agent
    findings:      int          # number of recommendations this call produced
    signals_seen:  List[str]    # signal names available at the time of the call


@dataclass
class AgentContext:
    bundle:      TelemetryBundle
    signals:     List[Signal]
    typed_recs:  List[Recommendation] = field(default_factory=list)   # Recommendation objects
    dict_recs:   List[Dict[str, Any]] = field(default_factory=list)   # root_cause_agent output
    trace:       List[TraceStep]      = field(default_factory=list)
    call_counts: Dict[str, int]       = field(default_factory=dict)

    def signal_names(self) -> List[str]:
        return [s.name for s in self.signals]

    def all_rule_ids(self) -> List[str]:
        return [r.rule_id for r in self.typed_recs]

    def available_agents(self) -> List[str]:
        return [
            name for name in AGENT_REGISTRY
            if self.call_counts.get(name, 0) < MAX_CALLS_PER_AGENT
        ]


# ---------------------------------------------------------------------------
# LLM Router
# ---------------------------------------------------------------------------

_ROUTER_SYSTEM = """You are an intelligent orchestration router for an AWS cloud SRE agent system.
Your job: given current signals and findings, decide which specialist agent to invoke next.

Available agents:
- metric_analyzer_agent   : CPU/memory/network/EBS threshold violations and trends
- cost_optimization_agent : Idle instances, Graviton, Spot, ASG savings — needs cost signals
- reliability_agent       : Health check failures, single-AZ, missing ASG
- security_agent          : IMDSv2 gaps, unencrypted EBS, open SSH/RDP, outdated AMIs
- root_cause_agent        : LLM-powered correlation of signals+events — call only when ≥2 signals AND ≥1 finding exist

Routing rules:
1. Always start with metric_analyzer_agent (step 1)
2. Call root_cause_agent only after other agents have run AND findings exist
3. Reply DONE when all relevant domains are covered or no new signals remain
4. Never suggest an agent that has hit its call limit

Respond ONLY with valid JSON: {"next": "<agent_name_or_DONE>", "reason": "<one concise sentence>"}"""


def _llm_route(ctx: AgentContext, step: int) -> Tuple[Optional[str], str]:
    """Ask Gemini to pick the next agent. Returns (agent_name | None, reason)."""
    try:
        signal_summary = [
            {"name": s.name, "severity": s.severity.value, "confidence": round(s.confidence, 2)}
            for s in ctx.signals
        ]
        finding_summary = [
            {"rule_id": r.rule_id, "type": r.type.value, "severity": r.severity.value}
            for r in ctx.typed_recs
        ]
        user_msg = (
            f"Step: {step}\n"
            f"Signals: {json.dumps(signal_summary)}\n"
            f"Findings so far: {json.dumps(finding_summary)}\n"
            f"Agents already called: {json.dumps(dict(ctx.call_counts))}\n"
            f"Still available: {ctx.available_agents()}\n\n"
            f"What should the orchestrator do next?"
        )
        full_prompt = _ROUTER_SYSTEM + "\n\n" + user_msg

        raw = get_llm_client().generate(full_prompt) or ""
        m = re.search(r'\{.*?\}', raw, re.DOTALL)
        if not m:
            raise ValueError("No JSON found in router response")

        parsed = json.loads(m.group())
        agent  = parsed.get("next", "DONE")
        reason = parsed.get("reason", "LLM routing decision")

        if agent == "DONE" or agent not in AGENT_REGISTRY:
            return None, reason
        if ctx.call_counts.get(agent, 0) >= MAX_CALLS_PER_AGENT:
            return None, f"{agent} already called {MAX_CALLS_PER_AGENT}× — stopping"
        return agent, reason

    except Exception as e:
        logger.warning("LLM router failed (step %d): %s — using rule-based fallback", step, e)
        return _rule_based_route(ctx)


def _rule_based_route(ctx: AgentContext) -> Tuple[Optional[str], str]:
    """
    Deterministic fallback: map signal domains to agents, skip exhausted ones.
    Called when the LLM router is unavailable or returns bad JSON.
    """
    signal_set  = set(ctx.signal_names())
    rule_ids    = set(ctx.all_rule_ids())
    available   = set(ctx.available_agents())

    # Priority order: metrics first, then domain-specific, then correlation
    candidates: List[Tuple[str, str]] = []

    if "metric_analyzer_agent" in available:
        candidates.append(("metric_analyzer_agent", "Baseline: always run metrics first"))

    if signal_set & _COST_SIGNALS and "cost_optimization_agent" in available:
        candidates.append(("cost_optimization_agent",
                           f"Cost signals detected: {signal_set & _COST_SIGNALS}"))

    if signal_set & _RELIABILITY_SIGNALS and "reliability_agent" in available:
        candidates.append(("reliability_agent",
                           f"Reliability signals detected: {signal_set & _RELIABILITY_SIGNALS}"))

    if signal_set & _SECURITY_SIGNALS and "security_agent" in available:
        candidates.append(("security_agent",
                           f"Security signals detected: {signal_set & _SECURITY_SIGNALS}"))

    # root_cause only when enough evidence exists
    if (len(ctx.signals) >= 2 and ctx.typed_recs
            and "root_cause_agent" in available):
        candidates.append(("root_cause_agent",
                           "Sufficient signals and findings for causal correlation"))

    # Pick the first candidate not yet called at max
    for name, reason in candidates:
        if ctx.call_counts.get(name, 0) < MAX_CALLS_PER_AGENT:
            return name, reason

    return None, "All relevant agents covered — done"


# ---------------------------------------------------------------------------
# Orchestrator core
# ---------------------------------------------------------------------------

def run_complex_agent(resource: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Dynamic multi-agent run. Returns recommendations in the same legacy dict
    shape as `run_sre_agent`, with an added `agent_trace` key on every
    recommendation for explainability.

    Drop-in replacement for run_sre_agent in analyzer_agent/main.py.
    """
    if not resource or resource.get("type") != "EC2":
        return []
    if resource.get("is_optimized"):
        return []

    # ── 1. Build telemetry context ──────────────────────────────────────────
    bundle  = normalize(collect_from_resource(resource))
    signals = extract_signals(bundle)

    ctx = AgentContext(
        bundle=bundle,
        signals=signals,
        call_counts={name: 0 for name in AGENT_REGISTRY},
    )

    logger.info(
        "[ComplexOrchestrator] Starting dynamic run for %s — %d signals: %s",
        bundle.instance_id, len(signals), [s.name for s in signals],
    )

    # ── 2. Dynamic agent loop ────────────────────────────────────────────────
    for step in range(1, MAX_STEPS + 1):

        # Step 1 always starts with metrics (skip LLM call — no findings yet)
        if step == 1:
            next_agent = "metric_analyzer_agent"
            reason     = "Always start with metric analysis to establish baseline signals"
        else:
            next_agent, reason = _llm_route(ctx, step)

        if next_agent is None:
            logger.info("[ComplexOrchestrator] Router said DONE at step %d: %s", step, reason)
            break

        agent_fn = AGENT_REGISTRY[next_agent]
        ctx.call_counts[next_agent] = ctx.call_counts.get(next_agent, 0) + 1

        logger.info(
            "[ComplexOrchestrator] Step %d → %s  (reason: %s)",
            step, next_agent, reason,
        )

        # ── 3. Run the agent ─────────────────────────────────────────────────
        try:
            new_output = agent_fn(bundle, signals)
        except Exception as e:
            logger.warning("[ComplexOrchestrator] %s raised: %s — skipping", next_agent, e)
            new_output = []

        # Separate typed Recommendation objects from dict-shaped outputs
        # (root_cause_agent returns List[Dict] directly)
        typed_new = [r for r in new_output if isinstance(r, Recommendation)]
        dict_new  = [r for r in new_output if isinstance(r, dict)]

        ctx.typed_recs.extend(typed_new)
        ctx.dict_recs.extend(dict_new)

        step_trace = TraceStep(
            step=step,
            agent=next_agent,
            reason=reason,
            findings=len(new_output),
            signals_seen=ctx.signal_names(),
        )
        ctx.trace.append(step_trace)

        logger.info(
            "[ComplexOrchestrator] Step %d complete — %d new findings "
            "(%d typed, %d dict), total typed=%d",
            step, len(new_output), len(typed_new), len(dict_new),
            len(ctx.typed_recs),
        )

    # ── 4. Rank + project to legacy dict shape ───────────────────────────────
    ranked  = rank(ctx.typed_recs)
    results = [to_legacy_dict(r) for r in ranked]

    # Append the dict-shaped root_cause_agent recommendations
    results.extend(ctx.dict_recs)

    # ── 5. Attach explainability trace to every recommendation ───────────────
    trace_payload = [
        {
            "step":         t.step,
            "agent":        t.agent,
            "reason":       t.reason,
            "findings":     t.findings,
            "signals_seen": t.signals_seen,
        }
        for t in ctx.trace
    ]
    for rec in results:
        rec["agent_trace"]    = trace_payload
        rec["orchestration"]  = {
            "total_steps":     len(ctx.trace),
            "agents_invoked":  [t.agent for t in ctx.trace],
            "unique_agents":   list(dict.fromkeys(t.agent for t in ctx.trace)),
            "coverage_note":   (
                f"Dynamic run: {len(ctx.trace)} steps across "
                f"{len(set(t.agent for t in ctx.trace))} agent(s)"
            ),
        }

    logger.info(
        "[ComplexOrchestrator] Done — %d recommendations from %d steps",
        len(results), len(ctx.trace),
    )
    return results
