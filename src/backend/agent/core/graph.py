"""
LangGraph StateGraph for the multi-agent cloud optimization system.

The graph implements a supervisor pattern where a central supervisor node
decides which agent to route to next. This enables free-form communication:
  - Any agent can be called at any point
  - Agents can be called multiple times (critique -> refine -> critique loop)
  - The supervisor decides dynamically based on current state
  - LangSmith traces every node execution automatically

Graph topology:
    START -> supervisor -> [dispatch -> specialists -> aggregate] -> supervisor
         -> critique -> supervisor -> [refine -> supervisor]* -> correlate
         -> supervisor -> verify -> supervisor -> evaluate -> END
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agent.core.state import AgentState
from agent.core.nodes import (
    supervisor,
    ec2_specialist,
    s3_specialist,
    dynamodb_specialist,
    aggregate,
    critique,
    refine,
    correlate,
    verify,
    evaluate,
)

logger = logging.getLogger(__name__)


def _route_from_supervisor(
    state: AgentState,
) -> Literal[
    "dispatch", "critique", "refine", "correlate", "verify", "evaluate", "__end__"
]:
    """Conditional edge: read supervisor's decision and route accordingly."""
    return state.get("next_action", "__end__")


def _route_from_dispatch(state: AgentState) -> list[str]:
    """Fan out to the specialist nodes that have matching resources."""
    resources = state.get("resources", [])
    types_present = {r.get("type") for r in resources}

    targets = []
    if "EC2" in types_present:
        targets.append("ec2_specialist")
    if "S3" in types_present:
        targets.append("s3_specialist")
    if "DynamoDB" in types_present:
        targets.append("dynamodb_specialist")

    return targets if targets else ["aggregate"]


def build_graph() -> StateGraph:
    """Construct the multi-agent LangGraph."""
    graph = StateGraph(AgentState)

    # --- Register nodes ---
    graph.add_node("supervisor", supervisor)
    graph.add_node("dispatch", _dispatch_noop)
    graph.add_node("ec2_specialist", ec2_specialist)
    graph.add_node("s3_specialist", s3_specialist)
    graph.add_node("dynamodb_specialist", dynamodb_specialist)
    graph.add_node("aggregate", aggregate)
    graph.add_node("critique", critique)
    graph.add_node("refine", refine)
    graph.add_node("correlate", correlate)
    graph.add_node("verify", verify)
    graph.add_node("evaluate", evaluate)

    # --- Entry point ---
    graph.set_entry_point("supervisor")

    # --- Supervisor routes to the next action ---
    graph.add_conditional_edges(
        "supervisor",
        _route_from_supervisor,
        {
            "dispatch": "dispatch",
            "critique": "critique",
            "refine": "refine",
            "correlate": "correlate",
            "verify": "verify",
            "evaluate": "evaluate",
            "__end__": END,
        },
    )

    # --- Dispatch fans out to specialists ---
    graph.add_conditional_edges("dispatch", _route_from_dispatch)

    # --- Specialists converge to aggregate ---
    graph.add_edge("ec2_specialist", "aggregate")
    graph.add_edge("s3_specialist", "aggregate")
    graph.add_edge("dynamodb_specialist", "aggregate")

    # --- Aggregate, critique, refine, correlate, verify all return to supervisor ---
    graph.add_edge("aggregate", "supervisor")
    graph.add_edge("critique", "supervisor")
    graph.add_edge("refine", "supervisor")
    graph.add_edge("correlate", "supervisor")
    graph.add_edge("verify", "supervisor")

    # --- Evaluate terminates ---
    graph.add_edge("evaluate", END)

    return graph


def _dispatch_noop(state: AgentState) -> dict:
    """No-op pass-through — the actual work is done by the specialists."""
    return {}


def compile_graph(checkpointer: MemorySaver | None = None):
    """Build and compile the graph, optionally with a checkpointer for persistence."""
    graph = build_graph()
    return graph.compile(checkpointer=checkpointer)


# Pre-built graph with in-memory checkpointer for session persistence
checkpointer = MemorySaver()
compiled_graph = compile_graph(checkpointer=checkpointer)
