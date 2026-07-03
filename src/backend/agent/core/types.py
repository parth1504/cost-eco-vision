"""
Shared types for the multi-agent framework.

Defines enums and dataclasses used by guardrails and graph nodes.
Agent communication and session state use plain dicts via LangGraph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


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
