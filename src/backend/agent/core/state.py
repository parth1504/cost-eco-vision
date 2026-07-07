"""
LangGraph state definition for the unified multi-agent orchestrator.

The state flows through the entire pipeline:
  telemetry → signals → sub-agents → safety → rank →
  critique → refine → correlate → verify → evaluate

Annotated fields with operator.add are append-only lists.
"""

from __future__ import annotations

import operator
import uuid
from typing import Any, Annotated, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    # total=False: every field is optional so nodes only return the keys
    # they update — LangGraph merges partial dicts into accumulated state.

    # --- Inputs ---
    session_id: str
    trace_id: str
    resources: List[Dict[str, Any]]

    # --- Telemetry layer ---
    telemetry_bundles: Dict[str, Any]       # resource_id → normalized bundle
    signals_map: Dict[str, List[Any]]       # resource_id → Signal objects

    # --- Sub-agent tracking ---
    findings: Dict[str, List[Dict[str, Any]]]   # agent_name → recommendations
    agent_call_counts: Dict[str, int]            # agent_name → invocation count

    # --- Pipeline stages ---
    all_recommendations: List[Dict[str, Any]]    # after safety_and_rank
    critique_results: Dict[str, Any]
    correlations: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]        # final verified output

    # --- Routing ---
    next_action: str    # supervisor sets this; graph conditional edge reads it
    phase: str
    iteration: int      # tracks critique→refine loop count

    # --- Tracing (append-only via operator.add) ---
    # LangGraph merges these with list concatenation, so each node can
    # return new entries without overwriting previous ones.
    messages: Annotated[List[Dict[str, Any]], operator.add]
    decisions: Annotated[List[Dict[str, Any]], operator.add]
    agent_trace: Annotated[List[Dict[str, Any]], operator.add]
    verification_gates: Annotated[List[Dict[str, Any]], operator.add]

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
        telemetry_bundles={},
        signals_map={},
        findings={},
        agent_call_counts={},
        all_recommendations=[],
        critique_results={},
        correlations=[],
        recommendations=[],
        next_action="collect_telemetry",
        phase="init",
        iteration=0,
        messages=[],
        decisions=[],
        agent_trace=[],
        verification_gates=[],
        status="active",
        error=None,
    )
