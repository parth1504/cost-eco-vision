"""
Shared types for the multi-agent framework.

Defines enums and dataclasses used across modules (guardrails, session,
evaluation). Agent communication uses plain dicts via the LangGraph state;
these types handle verification gates and session lifecycle.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class SessionStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    HANDED_OFF = "handed_off"


class VerificationResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
    SKIPPED = "skipped"


@dataclass
class VerificationGate:
    """Result of a verification gate check."""
    gate_name: str
    result: VerificationResult = VerificationResult.SKIPPED
    details: str = ""
    threshold: Optional[float] = None
    actual_value: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_name": self.gate_name,
            "result": self.result.value,
            "details": self.details,
            "threshold": self.threshold,
            "actual_value": self.actual_value,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SessionState:
    """Complete state of a multi-agent session."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: SessionStatus = SessionStatus.ACTIVE
    resources: List[Dict[str, Any]] = field(default_factory=list)
    messages: List[AgentMessage] = field(default_factory=list)
    decisions: List[AgentDecision] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    verification_gates: List[VerificationGate] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    parent_session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "status": self.status.value,
            "resource_count": len(self.resources),
            "message_count": len(self.messages),
            "decision_count": len(self.decisions),
            "recommendation_count": len(self.recommendations),
            "verification_gates": [g.to_dict() for g in self.verification_gates],
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "parent_session_id": self.parent_session_id,
            "metadata": self.metadata,
        }
