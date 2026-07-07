"""
LangGraph StateGraph — unified multi-agent cloud optimization system.

Single graph replaces every per-service orchestrator and the post-processing
pipeline. The supervisor node dynamically routes to telemetry collection,
signal extraction, service-specific sub-agents (discovered from the registry),
safety/ranking, critique, refine, correlate, verify, and evaluate.

Sub-agent nodes are registered dynamically from the service registry.
Adding a new AWS service auto-discovers its agents — no graph changes needed.

Graph topology:
    START → supervisor → collect_telemetry     → supervisor
                       → extract_signals       → supervisor
                       → [N sub-agent nodes]   → supervisor
                       → safety_and_rank       → supervisor
                       → critique              → supervisor
                       → refine               → supervisor
                       → correlate            → supervisor
                       → verify               → supervisor
                       → evaluate             → END
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

# Fixed pipeline stages — always present regardless of which services are registered.
_PIPELINE_NODES = [
    "collect_telemetry",
    "extract_signals",
    "safety_and_rank",
    "critique",
    "refine",
    "correlate",
    "verify",
    "evaluate",
]

# Merge pipeline nodes with dynamically discovered sub-agent nodes
# to form the full set of targets the supervisor can route to.
_ALL_ROUTING_TARGETS = _PIPELINE_NODES + list(SUB_AGENT_NODES.keys())


def _route_from_supervisor(state: AgentState) -> str:
    return state.get("next_action", "__end__")


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

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

    graph.set_entry_point("supervisor")

    # Supervisor uses conditional edges — state["next_action"] selects
    # which node runs next. "__end__" terminates the graph.
    routing_map = {name: name for name in _ALL_ROUTING_TARGETS}
    routing_map["__end__"] = END
    graph.add_conditional_edges("supervisor", _route_from_supervisor, routing_map)

    # Every non-terminal node returns to supervisor for re-routing.
    graph.add_edge("collect_telemetry", "supervisor")
    graph.add_edge("extract_signals", "supervisor")
    graph.add_edge("safety_and_rank", "supervisor")
    graph.add_edge("critique", "supervisor")
    graph.add_edge("refine", "supervisor")
    graph.add_edge("correlate", "supervisor")
    graph.add_edge("verify", "supervisor")

    for name in SUB_AGENT_NODES:
        graph.add_edge(name, "supervisor")

    # evaluate is the only node that terminates the graph directly.
    graph.add_edge("evaluate", END)

    return graph


def compile_graph(checkpointer: MemorySaver | None = None):
    graph = build_graph()
    return graph.compile(checkpointer=checkpointer)


# Module-level compilation — the graph is built once at startup and reused
# across all API requests. MemorySaver enables session replay via thread_id.
checkpointer = MemorySaver()
compiled_graph = compile_graph(checkpointer=checkpointer)
