"""
LangGraph StateGraph — unified multi-agent cloud optimization system.

Single graph replaces every per-service orchestrator and the post-processing
pipeline.  The supervisor node dynamically routes to telemetry collection,
signal extraction, 15 service-specific sub-agents, safety/ranking, critique,
refine, correlate, verify, and evaluate.

Graph topology:
    START → supervisor → collect_telemetry → supervisor
                       → extract_signals   → supervisor
                       → [15 sub-agent nodes] → supervisor
                       → safety_and_rank   → supervisor
                       → critique          → supervisor
                       → refine            → supervisor
                       → correlate         → supervisor
                       → verify            → supervisor
                       → evaluate          → END
"""

from __future__ import annotations

import logging

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agent.core.state import AgentState
from agent.core.nodes import (
    collect_telemetry,
    extract_signals,
    supervisor,
    safety_and_rank,
    critique,
    refine,
    correlate,
    verify,
    evaluate,
    SUB_AGENT_NODES,
)

logger = logging.getLogger(__name__)

_ALL_ROUTING_TARGETS = (
    [
        "collect_telemetry",
        "extract_signals",
        "safety_and_rank",
        "critique",
        "refine",
        "correlate",
        "verify",
        "evaluate",
    ]
    + list(SUB_AGENT_NODES.keys())
)


def _route_from_supervisor(state: AgentState) -> str:
    return state.get("next_action", "__end__")


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # --- Register nodes ---
    graph.add_node("supervisor", supervisor)
    graph.add_node("collect_telemetry", collect_telemetry)
    graph.add_node("extract_signals", extract_signals)
    graph.add_node("safety_and_rank", safety_and_rank)
    graph.add_node("critique", critique)
    graph.add_node("refine", refine)
    graph.add_node("correlate", correlate)
    graph.add_node("verify", verify)
    graph.add_node("evaluate", evaluate)

    for name, fn in SUB_AGENT_NODES.items():
        graph.add_node(name, fn)

    # --- Entry point ---
    graph.set_entry_point("supervisor")

    # --- Supervisor conditional routing ---
    routing_map = {name: name for name in _ALL_ROUTING_TARGETS}
    routing_map["__end__"] = END
    graph.add_conditional_edges("supervisor", _route_from_supervisor, routing_map)

    # --- Every non-terminal node returns to supervisor ---
    graph.add_edge("collect_telemetry", "supervisor")
    graph.add_edge("extract_signals", "supervisor")
    graph.add_edge("safety_and_rank", "supervisor")
    graph.add_edge("critique", "supervisor")
    graph.add_edge("refine", "supervisor")
    graph.add_edge("correlate", "supervisor")
    graph.add_edge("verify", "supervisor")

    for name in SUB_AGENT_NODES:
        graph.add_edge(name, "supervisor")

    # --- Evaluate terminates ---
    graph.add_edge("evaluate", END)

    return graph


def compile_graph(checkpointer: MemorySaver | None = None):
    graph = build_graph()
    return graph.compile(checkpointer=checkpointer)


checkpointer = MemorySaver()
compiled_graph = compile_graph(checkpointer=checkpointer)
