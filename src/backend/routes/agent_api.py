"""
REST + WebSocket API for the multi-agent system.

Endpoints:
  - POST /agent/analyze        — Run multi-agent analysis on resources
  - GET  /agent/session/{id}   — Get session state and trace
  - GET  /agent/sessions       — List recent sessions
  - POST /agent/session/{id}/handoff — Create handoff token
  - POST /agent/resume/{handoff_id} — Resume from handoff
  - GET  /agent/agents         — List registered agents
  - GET  /agent/trace/{id}     — Get full trace for a session
  - GET  /agent/evaluation     — Get evaluation metrics
  - GET  /agent/memory/stats   — Memory system stats
  - WS   /agent/ws/{session}   — Real-time trace stream
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


# ─── Request/Response Models ────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    resources: List[Dict[str, Any]]
    session_id: str | None = None


class HandoffResponse(BaseModel):
    handoff_id: str
    from_session: str


# ─── REST Endpoints ─────────────────────────────────────────────────────────

@router.post("/analyze")
async def analyze_resources(request: AnalyzeRequest):
    """Run multi-agent analysis on a set of resources."""
    from agent.core.orchestrator import MultiAgentOrchestrator

    orchestrator = MultiAgentOrchestrator()
    result = orchestrator.run(request.resources, session_id=request.session_id)
    return result


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """Get the state and trace of a specific session."""
    from agent.core.session import session_manager

    session = session_manager.get_session(session_id)
    if not session:
        return {"error": "Session not found", "session_id": session_id}
    return session


@router.get("/sessions")
async def list_sessions(limit: int = 20):
    """List recent agent sessions."""
    from agent.core.session import session_manager
    return {"sessions": session_manager.list_sessions(limit=limit)}


@router.post("/session/{session_id}/handoff")
async def create_handoff(session_id: str):
    """Create a handoff token for multi-session context transfer."""
    from agent.core.session import session_manager

    handoff_id = session_manager.handoff_session(session_id)
    if not handoff_id:
        return {"error": "Session not found or already completed"}
    return {"handoff_id": handoff_id, "from_session": session_id}


@router.post("/resume/{handoff_id}")
async def resume_from_handoff(handoff_id: str):
    """Resume a session from a handoff token."""
    from agent.core.session import session_manager

    session = session_manager.resume_from_handoff(handoff_id)
    if not session:
        return {"error": "Handoff token not found or expired"}
    return session.to_dict()


@router.get("/agents")
async def list_agents():
    """List all registered agents and their capabilities."""
    from agent.core.registry import agent_registry
    return {"agents": agent_registry.list_agents()}


@router.get("/trace/{trace_id}")
async def get_trace(trace_id: str):
    """Get the full OpenTelemetry trace for a session."""
    from agent.core.observability import trace_collector
    return {
        "trace_id": trace_id,
        "spans": trace_collector.get_trace(trace_id),
        "summary": trace_collector.get_session_summary(trace_id),
    }


@router.get("/evaluation")
async def get_evaluation():
    """Get evaluation metrics and benchmark results."""
    from agent.core.evaluation import evaluation_engine
    return {
        "summary": evaluation_engine.get_summary(),
        "metrics": evaluation_engine.get_metrics(),
        "benchmarks": evaluation_engine.get_benchmark_results(),
    }


@router.get("/memory/stats")
async def get_memory_stats():
    """Get memory system statistics."""
    from agent.core.memory import agent_memory
    return {
        "adoption_rate": agent_memory.get_adoption_rate(),
        "expired_cleaned": agent_memory.cleanup(),
    }


@router.get("/messages/{trace_id}")
async def get_messages(trace_id: str):
    """Get the full agent conversation for a trace."""
    from agent.core.registry import message_bus
    return {
        "trace_id": trace_id,
        "messages": message_bus.get_conversation(trace_id),
        "interaction_graph": message_bus.get_agent_interactions(trace_id),
    }


# ─── WebSocket for Real-time Trace Streaming ────────────────────────────────

class ConnectionManager:
    """Manages WebSocket connections for real-time trace streaming."""

    def __init__(self):
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        if session_id not in self._connections:
            self._connections[session_id] = []
        self._connections[session_id].append(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket):
        conns = self._connections.get(session_id, [])
        if websocket in conns:
            conns.remove(websocket)

    async def broadcast(self, session_id: str, data: Dict[str, Any]):
        conns = self._connections.get(session_id, [])
        dead = []
        for ws in conns:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conns.remove(ws)


ws_manager = ConnectionManager()


@router.websocket("/ws/{session_id}")
async def websocket_trace(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time agent trace streaming.

    The agentic UI connects here to see live:
      - Agent decisions as they happen
      - Messages between agents
      - Verification gate results
      - Recommendation generation progress
    """
    await ws_manager.connect(session_id, websocket)

    # Register a trace listener that forwards events to this WebSocket
    from agent.core.observability import trace_collector

    loop = asyncio.get_event_loop()

    def on_trace_event(event_type: str, data: Dict[str, Any]):
        if data.get("trace_id", "").startswith(session_id[:8]):
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast(session_id, {
                    "event": event_type,
                    "data": data,
                }),
                loop,
            )

    trace_collector.add_listener(on_trace_event)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(session_id, websocket)
        trace_collector.remove_listener(on_trace_event)
