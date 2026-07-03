"""
LangGraph state definition for the multi-agent cloud optimization system.

The state flows through the graph and accumulates results from each node.
Annotated fields with operator.add are append-only — each node's return
value is merged into the existing list rather than replacing it.
"""

from __future__ import annotations

import operator
import uuid
from typing import Any, Annotated, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    """Shared state that flows through the LangGraph execution."""

    # --- Inputs ---
    session_id: str
    trace_id: str
    resources: List[Dict[str, Any]]

    # --- Accumulated results (append-only via operator.add) ---
    messages: Annotated[List[Dict[str, Any]], operator.add]
    decisions: Annotated[List[Dict[str, Any]], operator.add]
    verification_gates: Annotated[List[Dict[str, Any]], operator.add]

    # --- Mutable results (overwritten by each node) ---
    findings: Dict[str, List[Dict[str, Any]]]
    all_recommendations: List[Dict[str, Any]]
    critique_results: Dict[str, Any]
    correlations: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]

    # --- Routing control ---
    next_action: str
    iteration: int

    # --- Status ---
    status: str
    error: Optional[str]


def create_initial_state(
    resources: List[Dict[str, Any]],
    session_id: Optional[str] = None,
) -> AgentState:
    return AgentState(
        session_id=session_id or str(uuid.uuid4()),
        trace_id=str(uuid.uuid4()),
        resources=resources,
        messages=[],
        decisions=[],
        verification_gates=[],
        findings={},
        all_recommendations=[],
        critique_results={},
        correlations=[],
        recommendations=[],
        next_action="dispatch",
        iteration=0,
        status="active",
        error=None,
    )
