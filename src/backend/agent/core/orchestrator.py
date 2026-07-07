"""
Multi-agent orchestrator — the public API for running LangGraph analysis.

This is a thin wrapper around compiled_graph (from graph.py). It does NOT
contain any routing logic — all routing is handled by the supervisor node
inside the graph. This module's responsibilities are:

  1. Create initial state from a list of resource dicts
  2. Invoke the compiled graph (synchronous, async, or streaming)
  3. Package the final state into a structured API response
  4. Handle errors and session state retrieval

Entry points:
  - services/resources.py calls orchestrator.run() for batch analysis
  - routes/agent_api.py calls orchestrator.run() for the REST endpoint
  - analyzer_agent/main.py calls orchestrator.run() for single-resource re-analysis
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from agent.core.state import AgentState, create_initial_state
from agent.core.graph import compiled_graph, checkpointer
from agent.core.evaluation import evaluation_engine
from agent.core.memory import agent_memory

logger = logging.getLogger(__name__)


class MultiAgentOrchestrator:
    """
    Runs a complete multi-agent optimization session via LangGraph.

    The graph topology enables free-form communication:
      - Supervisor dynamically routes to any agent
      - Critique <-> refine loop for iterative improvement
      - Correlation agent for cross-resource patterns
      - All transitions traced via LangSmith + OpenTelemetry
    """

    def run(
        self,
        resources: List[Dict[str, Any]],
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute the full multi-agent analysis pipeline synchronously.

        This is the primary entry point. compiled_graph.invoke() blocks
        until the graph reaches END (after the evaluate node), then
        returns the final accumulated state.
        """
        initial_state = create_initial_state(resources, session_id=session_id)
        sid = initial_state["session_id"]

        # thread_id maps to MemorySaver — same session_id can resume state
        config = {
            "configurable": {"thread_id": sid},
            "metadata": {
                "session_id": sid,
                "resource_count": len(resources),
                "resource_types": list({r.get("type") for r in resources}),
            },
        }

        logger.info(
            "[Orchestrator] Starting LangGraph run — session=%s, resources=%d",
            sid, len(resources),
        )

        start = time.time()
        try:
            final_state = compiled_graph.invoke(initial_state, config=config)
        except Exception as e:
            logger.error("[Orchestrator] Graph execution failed: %s", e, exc_info=True)
            return self._error_response(initial_state, str(e))

        elapsed_ms = (time.time() - start) * 1000
        logger.info(
            "[Orchestrator] Completed — session=%s, recommendations=%d, duration=%.0fms",
            sid, len(final_state.get("recommendations", [])), elapsed_ms,
        )

        return self._build_response(final_state, elapsed_ms)

    async def arun(
        self,
        resources: List[Dict[str, Any]],
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Async version using astream_events for real-time SSE streaming."""
        initial_state = create_initial_state(resources, session_id=session_id)
        sid = initial_state["session_id"]

        config = {
            "configurable": {"thread_id": sid},
            "metadata": {
                "session_id": sid,
                "resource_count": len(resources),
            },
        }

        start = time.time()
        final_state = None

        try:
            async for event in compiled_graph.astream_events(
                initial_state, config=config, version="v2",
            ):
                kind = event.get("event", "")
                if kind == "on_chain_end" and event.get("name") == "LangGraph":
                    final_state = event.get("data", {}).get("output", {})
        except Exception as e:
            logger.error("[Orchestrator] Async graph execution failed: %s", e, exc_info=True)
            return self._error_response(initial_state, str(e))

        if final_state is None:
            final_state = initial_state

        elapsed_ms = (time.time() - start) * 1000
        return self._build_response(final_state, elapsed_ms)

    def stream(
        self,
        resources: List[Dict[str, Any]],
        session_id: Optional[str] = None,
    ):
        """Generator that yields state snapshots after each node execution."""
        initial_state = create_initial_state(resources, session_id=session_id)
        sid = initial_state["session_id"]

        config = {
            "configurable": {"thread_id": sid},
            "metadata": {"session_id": sid},
        }

        for state_snapshot in compiled_graph.stream(initial_state, config=config):
            yield state_snapshot

    def get_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve the checkpointed state for a session."""
        config = {"configurable": {"thread_id": session_id}}
        try:
            snapshot = compiled_graph.get_state(config)
            if snapshot and snapshot.values:
                return snapshot.values
        except Exception:
            pass
        # Fallback to persistent memory if checkpointer has been evicted
        return agent_memory.get_session_state(session_id)

    def _build_response(self, state: dict, elapsed_ms: float) -> Dict[str, Any]:
        """Extract fields from the final LangGraph state into the structured
        response shape that the frontend and API consumers expect."""
        recommendations = state.get("recommendations", [])
        decisions = state.get("decisions", [])
        messages = state.get("messages", [])
        gates = state.get("verification_gates", [])
        correlations = state.get("correlations", [])

        passed = sum(1 for g in gates if g.get("result") == "passed")
        failed = sum(1 for g in gates if g.get("result") == "failed")
        review = sum(1 for g in gates if g.get("result") == "needs_review")

        return {
            "session": {
                "session_id": state.get("session_id", ""),
                "trace_id": state.get("trace_id", ""),
                "status": state.get("status", "completed"),
                "resource_count": len(state.get("resources", [])),
                "recommendation_count": len(recommendations),
                "message_count": len(messages),
                "decision_count": len(decisions),
                "duration_ms": round(elapsed_ms, 2),
            },
            "recommendations": recommendations,
            "decisions": decisions,
            "messages": messages,
            "correlations": correlations,
            "verification_summary": {
                "total_gates": len(gates),
                "passed": passed,
                "failed": failed,
                "needs_review": review,
            },
            "verification_gates": gates,
            "evaluation": evaluation_engine.get_summary(),
        }

    def _error_response(self, state: dict, error: str) -> Dict[str, Any]:
        return {
            "session": {
                "session_id": state.get("session_id", ""),
                "trace_id": state.get("trace_id", ""),
                "status": "failed",
                "error": error,
            },
            "recommendations": [],
            "decisions": state.get("decisions", []),
            "messages": state.get("messages", []),
            "correlations": [],
            "verification_summary": {"total_gates": 0, "passed": 0, "failed": 0, "needs_review": 0},
            "verification_gates": [],
            "evaluation": {},
        }
