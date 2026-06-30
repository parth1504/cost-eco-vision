"""
Unified type system for the multi-agent framework.

Every agent in the system (EC2, S3, DynamoDB, Critique, Correlation)
communicates through these shared types. The existing per-agent types
(ec2_agent/types.py etc.) remain for domain-specific telemetry bundles,
but all inter-agent messages and orchestration state use these.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentRole(str, Enum):
    EC2_SPECIALIST = "ec2_specialist"
    S3_SPECIALIST = "s3_specialist"
    DYNAMODB_SPECIALIST = "dynamodb_specialist"
    CRITIQUE = "critique"
    CORRELATION = "correlation"
    ROOT_CAUSE = "root_cause"
    ORCHESTRATOR = "orchestrator"


class MessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    CRITIQUE_REQUEST = "critique_request"
    CRITIQUE_RESPONSE = "critique_response"
    CORRELATION_REQUEST = "correlation_request"
    CORRELATION_RESPONSE = "correlation_response"
    REFINEMENT = "refinement"
    VERIFICATION = "verification"
    HANDOFF = "handoff"


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
class AgentMessage:
    """A message between any two agents in the system."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: str = ""
    to_agent: str = ""
    message_type: MessageType = MessageType.REQUEST
    payload: Dict[str, Any] = field(default_factory=dict)
    reply_to: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    trace_id: str = ""
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "message_type": self.message_type.value,
            "payload": self.payload,
            "reply_to": self.reply_to,
            "timestamp": self.timestamp.isoformat(),
            "trace_id": self.trace_id,
            "span_id": self.span_id,
        }


@dataclass
class AgentDecision:
    """Records a single decision point for traceability."""
    agent: str
    action: str
    reasoning: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    duration_ms: float = 0.0
    token_usage: Dict[str, int] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "action": self.action,
            "reasoning": self.reasoning,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "confidence": self.confidence,
            "duration_ms": self.duration_ms,
            "token_usage": self.token_usage,
            "timestamp": self.timestamp.isoformat(),
        }


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
