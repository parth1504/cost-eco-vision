"""
Agent registry and message bus.

This is the backbone that enables free-form agent communication.
Any agent can send a message to any other agent — there is no fixed
orchestration graph. Agents discover each other through the registry
and communicate through the message bus.

The bus records every message for traceability, and the observability
layer wraps each delivery in a span so the full conversation between
agents is visible in the trace UI.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Protocol

from agent.core.types import AgentMessage, AgentDecision, MessageType
from agent.core.observability import trace_collector

logger = logging.getLogger(__name__)


class AgentProtocol(Protocol):
    """Interface every agent must implement to participate in the mesh."""

    @property
    def agent_id(self) -> str: ...

    @property
    def capabilities(self) -> List[str]: ...

    def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]: ...


class AgentRegistry:
    """
    Central registry of all agents. Agents register on startup;
    the orchestrator and other agents discover them here.
    """

    def __init__(self):
        self._agents: Dict[str, AgentProtocol] = {}
        self._capabilities_index: Dict[str, List[str]] = defaultdict(list)

    def register(self, agent: AgentProtocol):
        self._agents[agent.agent_id] = agent
        for cap in agent.capabilities:
            if agent.agent_id not in self._capabilities_index[cap]:
                self._capabilities_index[cap].append(agent.agent_id)
        logger.info("Registered agent: %s (capabilities: %s)", agent.agent_id, agent.capabilities)

    def unregister(self, agent_id: str):
        agent = self._agents.pop(agent_id, None)
        if agent:
            for cap in agent.capabilities:
                ids = self._capabilities_index.get(cap, [])
                if agent_id in ids:
                    ids.remove(agent_id)

    def get(self, agent_id: str) -> Optional[AgentProtocol]:
        return self._agents.get(agent_id)

    def find_by_capability(self, capability: str) -> List[str]:
        return self._capabilities_index.get(capability, [])

    def all_agents(self) -> Dict[str, AgentProtocol]:
        return dict(self._agents)

    def list_agents(self) -> List[Dict[str, Any]]:
        return [
            {"agent_id": aid, "capabilities": list(a.capabilities)}
            for aid, a in self._agents.items()
        ]


class MessageBus:
    """
    Pub/sub message bus for inter-agent communication.

    Supports:
    - Direct messages (agent-to-agent)
    - Broadcasts (one-to-all)
    - Request-reply patterns
    - Message history for traceability
    """

    def __init__(self, registry: AgentRegistry):
        self._registry = registry
        self._history: List[AgentMessage] = []
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._broadcast_listeners: List[Callable] = []

    def send(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Send a direct message to a specific agent and get a response."""
        self._history.append(message)
        self._notify_subscribers(message)

        target = self._registry.get(message.to_agent)
        if not target:
            logger.warning("Message to unknown agent: %s", message.to_agent)
            return None

        with trace_collector.span(
            trace_id=message.trace_id,
            operation=f"message.{message.message_type.value}",
            agent=message.from_agent,
            attributes={
                "message.id": message.id,
                "message.from": message.from_agent,
                "message.to": message.to_agent,
                "message.type": message.message_type.value,
            },
        ):
            start = time.time()
            try:
                response = target.handle_message(message)
            except Exception as e:
                logger.error("Agent %s failed to handle message: %s", message.to_agent, e)
                response = AgentMessage(
                    from_agent=message.to_agent,
                    to_agent=message.from_agent,
                    message_type=MessageType.RESPONSE,
                    payload={"error": str(e)},
                    reply_to=message.id,
                    trace_id=message.trace_id,
                )

            if response:
                response.trace_id = message.trace_id
                self._history.append(response)
                self._notify_subscribers(response)

            elapsed_ms = (time.time() - start) * 1000
            trace_collector.record_metric(
                "agent.message_handling_ms",
                elapsed_ms,
                labels={"from": message.from_agent, "to": message.to_agent},
            )

            return response

    def broadcast(self, message: AgentMessage) -> List[AgentMessage]:
        """Broadcast a message to all registered agents (except sender)."""
        message.message_type = MessageType.BROADCAST
        self._history.append(message)
        self._notify_subscribers(message)

        responses = []
        for agent_id, agent in self._registry.all_agents().items():
            if agent_id == message.from_agent:
                continue
            try:
                resp = agent.handle_message(message)
                if resp:
                    resp.trace_id = message.trace_id
                    self._history.append(resp)
                    responses.append(resp)
            except Exception as e:
                logger.warning("Broadcast handler failed in %s: %s", agent_id, e)

        for listener in self._broadcast_listeners:
            try:
                listener(message, responses)
            except Exception as e:
                logger.warning("Broadcast listener error: %s", e)

        return responses

    def subscribe(self, agent_id: str, callback: Callable):
        self._subscribers[agent_id].append(callback)

    def on_broadcast(self, callback: Callable):
        self._broadcast_listeners.append(callback)

    def _notify_subscribers(self, message: AgentMessage):
        for cb in self._subscribers.get(message.to_agent, []):
            try:
                cb(message)
            except Exception as e:
                logger.warning("Subscriber notification error: %s", e)

    def get_conversation(self, trace_id: str) -> List[Dict[str, Any]]:
        """Get the full message history for a trace (session)."""
        return [
            m.to_dict() for m in self._history
            if m.trace_id == trace_id
        ]

    def get_agent_interactions(self, trace_id: str) -> Dict[str, Any]:
        """Build an interaction graph for visualization."""
        messages = [m for m in self._history if m.trace_id == trace_id]
        nodes = set()
        edges = []
        for m in messages:
            nodes.add(m.from_agent)
            if m.to_agent:
                nodes.add(m.to_agent)
            edges.append({
                "from": m.from_agent,
                "to": m.to_agent,
                "type": m.message_type.value,
                "timestamp": m.timestamp.isoformat(),
            })
        return {
            "nodes": [{"id": n} for n in nodes],
            "edges": edges,
        }

    def get_full_history(self, limit: int = 200) -> List[Dict[str, Any]]:
        return [m.to_dict() for m in self._history[-limit:]]


# Singletons
agent_registry = AgentRegistry()
message_bus = MessageBus(agent_registry)
