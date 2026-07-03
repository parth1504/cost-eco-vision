"""
Session management for multi-agent interactions.

Handles:
  - Session lifecycle (create, pause, resume, complete)
  - Multi-session handoff (transfer context to a new session)
  - Session history and replay
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from agent.core.types import SessionState, SessionStatus
from agent.core.memory import agent_memory

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages the lifecycle of multi-agent sessions."""

    def __init__(self):
        self._active_sessions: Dict[str, SessionState] = {}

    def create_session(
        self,
        resources: Optional[List[Dict[str, Any]]] = None,
        parent_session_id: Optional[str] = None,
    ) -> SessionState:
        session = SessionState(
            resources=resources or [],
            parent_session_id=parent_session_id,
        )

        if parent_session_id:
            parent = agent_memory.get_session_state(parent_session_id)
            if parent:
                session.context["handoff_from"] = {
                    "session_id": parent_session_id,
                    "recommendation_count": parent.get("recommendation_count", 0),
                    "status": parent.get("status", "unknown"),
                }

        self._active_sessions[session.session_id] = session
        agent_memory.store_session_state(session.session_id, session.to_dict())
        return session

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        if session_id in self._active_sessions:
            return self._active_sessions[session_id].to_dict()
        return agent_memory.get_session_state(session_id)

    def pause_session(self, session_id: str) -> bool:
        session = self._active_sessions.get(session_id)
        if not session:
            return False
        session.status = SessionStatus.PAUSED
        agent_memory.store_session_state(session_id, session.to_dict())
        return True

    def resume_session(self, session_id: str) -> Optional[SessionState]:
        stored = agent_memory.get_session_state(session_id)
        if not stored:
            return None

        session = SessionState(
            session_id=session_id,
            status=SessionStatus.ACTIVE,
            parent_session_id=stored.get("parent_session_id"),
        )
        session.context["resumed_at"] = datetime.utcnow().isoformat()
        session.context["prior_state"] = stored

        self._active_sessions[session_id] = session
        return session

    def complete_session(self, session_id: str):
        session = self._active_sessions.pop(session_id, None)
        if session:
            session.status = SessionStatus.COMPLETED
            session.completed_at = datetime.utcnow()
            agent_memory.store_session_state(session_id, session.to_dict())
            agent_memory.store_session_snapshot(session_id, session.to_dict())

    def handoff_session(self, from_session_id: str) -> Optional[str]:
        """Create a handoff token that a new session can resume from."""
        stored = agent_memory.get_session_state(from_session_id)
        if not stored:
            return None

        self.pause_session(from_session_id)
        return agent_memory.create_handoff(from_session_id, stored)

    def resume_from_handoff(self, handoff_id: str) -> Optional[SessionState]:
        handoff_data = agent_memory.resume_from_handoff(handoff_id)
        if not handoff_data:
            return None

        from_session = handoff_data.get("from_session", "")
        context = handoff_data.get("context", {})

        session = self.create_session(parent_session_id=from_session)
        session.context["handoff_context"] = context
        return session

    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        active = [
            {**s.to_dict(), "source": "active"}
            for s in self._active_sessions.values()
        ]

        snapshots = agent_memory.get_recent_snapshots(limit=limit)
        historical = [
            {**s, "source": "history"}
            for s in snapshots
        ]

        combined = active + historical
        combined.sort(
            key=lambda s: s.get("started_at", ""),
            reverse=True,
        )
        return combined[:limit]


# Singleton
session_manager = SessionManager()
