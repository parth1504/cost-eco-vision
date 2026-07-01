"""
REST + WebSocket API for the LangGraph multi-agent system.

Endpoints:
  - POST /agent/analyze           — Run multi-agent analysis via LangGraph
  - POST /agent/analyze/stream    — Stream node-by-node results via SSE
  - GET  /agent/session/{id}      — Get session state (from LangGraph checkpointer)
  - GET  /agent/sessions          — List recent sessions
  - POST /agent/session/{id}/handoff — Create handoff token
  - POST /agent/resume/{handoff_id}  — Resume from handoff
  - GET  /agent/trace/{id}        — Get trace data
  - GET  /agent/evaluation        — Get evaluation metrics
  - GET  /agent/memory/stats      — Memory system stats
  - GET  /agent/graph             — Get graph topology for visualization
  - WS   /agent/ws/{session}      — Real-time event stream
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
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
    """Run multi-agent analysis via LangGraph."""
    from agent.core.orchestrator import MultiAgentOrchestrator

    orchestrator = MultiAgentOrchestrator()
    result = orchestrator.run(request.resources, session_id=request.session_id)
    return result


@router.post("/analyze/stream")
async def analyze_stream(request: AnalyzeRequest):
    """Stream analysis results node-by-node via Server-Sent Events."""
    from agent.core.orchestrator import MultiAgentOrchestrator

    orchestrator = MultiAgentOrchestrator()

    async def event_generator():
        for snapshot in orchestrator.stream(request.resources, session_id=request.session_id):
            yield f"data: {json.dumps(snapshot, default=str)}\n\n"
        yield "data: {\"event\": \"complete\"}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """Get session state from LangGraph checkpointer or memory."""
    from agent.core.orchestrator import MultiAgentOrchestrator

    orchestrator = MultiAgentOrchestrator()
    state = orchestrator.get_session_state(session_id)
    if not state:
        return {"error": "Session not found", "session_id": session_id}
    return state


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


@router.get("/trace/{trace_id}")
async def get_trace(trace_id: str):
    """Get trace data for a session."""
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


@router.get("/graph")
async def get_graph_topology():
    """Get the LangGraph topology for UI visualization."""
    from agent.core.graph import compiled_graph

    try:
        graph_data = compiled_graph.get_graph()
        nodes = [
            {"id": node_id, "type": "agent" if node_id not in ("__start__", "__end__") else "control"}
            for node_id in graph_data.nodes
        ]
        edges = [
            {
                "source": edge.source,
                "target": edge.target,
                "conditional": edge.conditional,
            }
            for edge in graph_data.edges
        ]
        return {"nodes": nodes, "edges": edges}
    except Exception as e:
        logger.warning("Could not extract graph topology: %s", e)
        return {
            "nodes": [
                {"id": "supervisor", "type": "agent"},
                {"id": "ec2_specialist", "type": "agent"},
                {"id": "s3_specialist", "type": "agent"},
                {"id": "dynamodb_specialist", "type": "agent"},
                {"id": "critique", "type": "agent"},
                {"id": "refine", "type": "agent"},
                {"id": "correlate", "type": "agent"},
                {"id": "verify", "type": "agent"},
                {"id": "evaluate", "type": "agent"},
            ],
            "edges": [
                {"source": "supervisor", "target": "ec2_specialist", "conditional": True},
                {"source": "supervisor", "target": "s3_specialist", "conditional": True},
                {"source": "supervisor", "target": "dynamodb_specialist", "conditional": True},
                {"source": "supervisor", "target": "critique", "conditional": True},
                {"source": "supervisor", "target": "refine", "conditional": True},
                {"source": "supervisor", "target": "correlate", "conditional": True},
                {"source": "supervisor", "target": "verify", "conditional": True},
                {"source": "supervisor", "target": "evaluate", "conditional": True},
                {"source": "ec2_specialist", "target": "aggregate", "conditional": False},
                {"source": "s3_specialist", "target": "aggregate", "conditional": False},
                {"source": "dynamodb_specialist", "target": "aggregate", "conditional": False},
                {"source": "aggregate", "target": "supervisor", "conditional": False},
                {"source": "critique", "target": "supervisor", "conditional": False},
                {"source": "refine", "target": "supervisor", "conditional": False},
                {"source": "correlate", "target": "supervisor", "conditional": False},
                {"source": "verify", "target": "supervisor", "conditional": False},
                {"source": "evaluate", "target": "__end__", "conditional": False},
            ],
        }


# ─── WebSocket for Real-time Event Streaming ────────────────────────────────

class ConnectionManager:
    """Manages WebSocket connections for real-time trace streaming."""

    def __init__(self):
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self._connections.setdefault(session_id, []).append(websocket)

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
    WebSocket for real-time agent trace streaming.

    Streams LangGraph node transitions, span events, and metrics
    to the frontend dashboard as they happen.
    """
    await ws_manager.connect(session_id, websocket)

    from agent.core.observability import trace_collector

    loop = asyncio.get_event_loop()

    def on_trace_event(event_type: str, data: Dict[str, Any]):
        if data.get("trace_id", "").startswith(session_id[:8]):
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast(session_id, {"event": event_type, "data": data}),
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
