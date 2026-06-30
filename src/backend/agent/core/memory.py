"""
Unified memory system for the multi-agent framework.

Three tiers:
  1. Working memory  — current session state (agent findings, messages, decisions)
  2. Short-term      — recent sessions, cross-session context (TTL: 7 days)
  3. Long-term       — recommendation history, adoption tracking, patterns (persistent)

All tiers are backed by an in-process store with an interface designed to
swap in DynamoDB/Redis when ready for production deployment. The memory
system is what enables:
  - Recommendation deduplication across sessions
  - Multi-session handoff (user returns, picks up where they left off)
  - Feedback loops (track which recs were adopted, measure actual impact)
  - Pattern detection (recurring issues across resources)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    key: str
    value: Any
    created_at: float = field(default_factory=time.time)
    ttl_seconds: Optional[float] = None
    tags: Dict[str, str] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.ttl_seconds is None:
            return False
        return time.time() - self.created_at > self.ttl_seconds


class MemoryStore:
    """
    In-process memory store with TTL support and tag-based queries.
    Production: swap internals for Redis (working/short-term) + DynamoDB (long-term).
    """

    def __init__(self):
        self._store: Dict[str, MemoryEntry] = {}
        self._tag_index: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))

    def put(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float] = None,
        tags: Optional[Dict[str, str]] = None,
    ):
        entry = MemoryEntry(key=key, value=value, ttl_seconds=ttl_seconds, tags=tags or {})
        self._store[key] = entry
        for tag_key, tag_val in entry.tags.items():
            if key not in self._tag_index[tag_key][tag_val]:
                self._tag_index[tag_key][tag_val].append(key)

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.is_expired:
            self.delete(key)
            return None
        return entry.value

    def delete(self, key: str):
        entry = self._store.pop(key, None)
        if entry:
            for tag_key, tag_val in entry.tags.items():
                keys = self._tag_index.get(tag_key, {}).get(tag_val, [])
                if key in keys:
                    keys.remove(key)

    def query_by_tag(self, tag_key: str, tag_value: str) -> List[Any]:
        keys = self._tag_index.get(tag_key, {}).get(tag_value, [])
        results = []
        for k in keys:
            val = self.get(k)
            if val is not None:
                results.append(val)
        return results

    def keys_by_prefix(self, prefix: str) -> List[str]:
        return [k for k in self._store if k.startswith(prefix) and not self._store[k].is_expired]

    def cleanup_expired(self) -> int:
        expired = [k for k, v in self._store.items() if v.is_expired]
        for k in expired:
            self.delete(k)
        return len(expired)


class AgentMemory:
    """
    High-level memory interface used by the orchestrator and agents.
    Wraps MemoryStore with domain-specific operations.
    """

    WORKING_TTL = 3600          # 1 hour
    SHORT_TERM_TTL = 604800     # 7 days
    LONG_TERM_TTL = None        # permanent

    def __init__(self):
        self._store = MemoryStore()

    # ── Working Memory (current session) ──────────────────────────────────

    def store_session_state(self, session_id: str, state: Dict[str, Any]):
        self._store.put(
            f"session:{session_id}",
            state,
            ttl_seconds=self.WORKING_TTL,
            tags={"type": "session", "session_id": session_id},
        )

    def get_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._store.get(f"session:{session_id}")

    # ── Short-term Memory (cross-session) ──────────────────────────────────

    def store_session_snapshot(self, session_id: str, snapshot: Dict[str, Any]):
        self._store.put(
            f"snapshot:{session_id}",
            snapshot,
            ttl_seconds=self.SHORT_TERM_TTL,
            tags={"type": "snapshot", "session_id": session_id},
        )

    def get_recent_snapshots(self, limit: int = 10) -> List[Dict[str, Any]]:
        keys = self._store.keys_by_prefix("snapshot:")
        results = []
        for k in sorted(keys, reverse=True)[:limit]:
            val = self._store.get(k)
            if val:
                results.append(val)
        return results

    # ── Long-term Memory (recommendation history) ──────────────────────────

    def store_recommendation_history(
        self, resource_id: str, recommendations: List[Dict[str, Any]]
    ):
        key = f"rec_history:{resource_id}"
        existing = self._store.get(key) or []
        existing.extend(recommendations)
        # keep last 100 per resource
        self._store.put(
            key, existing[-100:],
            ttl_seconds=self.LONG_TERM_TTL,
            tags={"type": "rec_history", "resource_id": resource_id},
        )

    def get_recommendation_history(self, resource_id: str) -> List[Dict[str, Any]]:
        return self._store.get(f"rec_history:{resource_id}") or []

    def store_adoption(self, resource_id: str, rule_id: str, adopted: bool, actual_savings: Optional[float] = None):
        key = f"adoption:{resource_id}:{rule_id}"
        self._store.put(
            key,
            {
                "resource_id": resource_id,
                "rule_id": rule_id,
                "adopted": adopted,
                "actual_savings": actual_savings,
                "timestamp": datetime.utcnow().isoformat(),
            },
            ttl_seconds=self.LONG_TERM_TTL,
            tags={"type": "adoption", "resource_id": resource_id},
        )

    def get_adoption_rate(self, resource_id: Optional[str] = None) -> Dict[str, Any]:
        if resource_id:
            entries = self._store.query_by_tag("resource_id", resource_id)
            adoptions = [e for e in entries if isinstance(e, dict) and "adopted" in e]
        else:
            keys = self._store.keys_by_prefix("adoption:")
            adoptions = [self._store.get(k) for k in keys]
            adoptions = [a for a in adoptions if a]

        if not adoptions:
            return {"total": 0, "adopted": 0, "rate": 0.0}

        adopted_count = sum(1 for a in adoptions if a.get("adopted"))
        return {
            "total": len(adoptions),
            "adopted": adopted_count,
            "rate": round(adopted_count / len(adoptions), 3) if adoptions else 0.0,
        }

    # ── Deduplication ──────────────────────────────────────────────────────

    def is_duplicate(
        self,
        resource_id: str,
        rule_id: str,
        cooldown_hours: int = 24,
    ) -> bool:
        history = self.get_recommendation_history(resource_id)
        for rec in reversed(history):
            if rec.get("rule_id") != rule_id:
                continue
            detected = rec.get("detected_at")
            if not detected:
                continue
            try:
                dt = datetime.fromisoformat(str(detected).replace("Z", ""))
                if datetime.utcnow() - dt < timedelta(hours=cooldown_hours):
                    return True
            except (ValueError, TypeError):
                continue
        return False

    # ── Pattern Detection ──────────────────────────────────────────────────

    def get_recurring_patterns(self, resource_id: str, min_occurrences: int = 3) -> List[Dict[str, Any]]:
        history = self.get_recommendation_history(resource_id)
        rule_counts: Dict[str, int] = defaultdict(int)
        for rec in history:
            rule_id = rec.get("rule_id", "")
            if rule_id:
                rule_counts[rule_id] += 1

        return [
            {"rule_id": rid, "occurrences": count}
            for rid, count in rule_counts.items()
            if count >= min_occurrences
        ]

    # ── Multi-session Handoff ──────────────────────────────────────────────

    def create_handoff(self, from_session: str, context: Dict[str, Any]) -> str:
        import uuid
        handoff_id = str(uuid.uuid4())
        self._store.put(
            f"handoff:{handoff_id}",
            {
                "from_session": from_session,
                "context": context,
                "created_at": datetime.utcnow().isoformat(),
            },
            ttl_seconds=self.SHORT_TERM_TTL,
            tags={"type": "handoff", "from_session": from_session},
        )
        return handoff_id

    def resume_from_handoff(self, handoff_id: str) -> Optional[Dict[str, Any]]:
        return self._store.get(f"handoff:{handoff_id}")

    def cleanup(self) -> int:
        return self._store.cleanup_expired()


# Singleton
agent_memory = AgentMemory()
