"""
Dynamic service registry for the multi-agent cloud optimization system.

Each AWS service (EC2, S3, DynamoDB, ...) registers its capabilities:
  - telemetry collection + normalization
  - signal extraction
  - sub-agent definitions (function, module, signal domains)
  - report conversion (to_legacy_dict)

The LangGraph pipeline discovers registered services at startup and builds
nodes, routing logic, and context maps dynamically. Adding a new service =
one folder + one register() call. No core files need to change.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class AgentDefinition:
    """
    Declares a single sub-agent within a service.

    Each field feeds a different part of the LangGraph pipeline:
      - node_name:         becomes the LangGraph node name and routing target
      - function_name:     the callable inside module_path (loaded lazily)
      - module_path:       stored as string to defer import (avoids circular deps)
      - description:       injected into the LLM router prompt so it knows
                           what this agent does and when to call it
      - signal_domain:     which telemetry signals this agent cares about —
                           context.py filters signals to only pass relevant ones
      - rec_type_relevance: which recommendation types (cost, security, etc.)
                           this agent's prior recs are filtered by in context
      - routing_signals:   if set, the rule-based router only routes here when
                           at least one of these signals was extracted
      - is_root_cause:     root-cause agents are gated — they only run after
                           domain agents produce findings AND >=2 signals exist
      - routing_priority:  higher = runs first in rule-based routing (10 is
                           highest in EC2; root-cause agents use 3)
    """
    node_name: str
    function_name: str
    module_path: str
    description: str
    signal_domain: Set[str] = field(default_factory=set)
    rec_type_relevance: Set[str] = field(default_factory=set)
    routing_signals: Set[str] = field(default_factory=set)
    is_root_cause: bool = False
    routing_priority: int = 5


@dataclass
class ServiceDefinition:
    """
    Everything the LangGraph pipeline needs to work with an AWS service.

    Module paths are strings (not direct imports) so that heavy dependencies
    like boto3 and openai are only loaded when the pipeline actually runs,
    not during startup when the registry is being populated.
    """
    service_type: str                  # e.g. "EC2", "S3", "DynamoDB"
    telemetry_module: str              # must export collect_from_resource() + normalize()
    signals_module: str                # must export extract_signals()
    report_module: str                 # must export to_legacy_dict()
    agents: Dict[str, AgentDefinition] = field(default_factory=dict)


class ServiceRegistry:
    # Singleton — instantiated once at module level. All service registrations
    # happen during _discover_services() before any graph node runs.

    def __init__(self) -> None:
        self._services: Dict[str, ServiceDefinition] = {}
        # Reverse index: agent_name → service_type for O(1) lookups
        self._agent_to_service: Dict[str, str] = {}

    def register(self, definition: ServiceDefinition) -> None:
        self._services[definition.service_type] = definition
        for agent_name in definition.agents:
            self._agent_to_service[agent_name] = definition.service_type
        logger.info(
            "Registered service %s with %d agents",
            definition.service_type, len(definition.agents),
        )

    def get_service(self, service_type: str) -> Optional[ServiceDefinition]:
        return self._services.get(service_type)

    def get_all_services(self) -> Dict[str, ServiceDefinition]:
        return dict(self._services)

    def get_all_agent_names(self) -> List[str]:
        names: List[str] = []
        for service in self._services.values():
            names.extend(service.agents.keys())
        return names

    def get_agent_definition(self, node_name: str) -> Optional[AgentDefinition]:
        service_type = self._agent_to_service.get(node_name)
        if not service_type:
            return None
        return self._services[service_type].agents.get(node_name)

    def get_service_for_agent(self, node_name: str) -> Optional[ServiceDefinition]:
        service_type = self._agent_to_service.get(node_name)
        if not service_type:
            return None
        return self._services.get(service_type)

    def get_signal_domain_map(self) -> Dict[str, Set[str]]:
        """Build agent_name → signal_names map. Used by context.py to filter
        which signals each agent sees (only its domain, not all signals)."""
        domain_map: Dict[str, Set[str]] = {}
        for service in self._services.values():
            for agent_name, agent_def in service.agents.items():
                if agent_def.signal_domain:
                    domain_map[agent_name] = set(agent_def.signal_domain)
        return domain_map

    def get_rec_type_relevance(self) -> Dict[str, Set[str]]:
        """Build agent_name → rec_type set. Used by context.py to filter
        which prior recommendations each agent sees in its context."""
        relevance: Dict[str, Set[str]] = {}
        for service in self._services.values():
            for agent_name, agent_def in service.agents.items():
                if agent_def.rec_type_relevance:
                    relevance[agent_name] = set(agent_def.rec_type_relevance)
        return relevance

    def get_router_agent_descriptions(self) -> str:
        """Generate the 'Available agents' section for the LLM router prompt.
        The LLM reads these descriptions to decide which agent to invoke."""
        lines = []
        for service in self._services.values():
            for name, agent_def in service.agents.items():
                suffix = ""
                if agent_def.is_root_cause:
                    suffix = (
                        f" (call only when >=2 {service.service_type} "
                        f"signals AND findings exist)"
                    )
                lines.append(
                    f"- {name:<30}: {agent_def.description}{suffix}"
                )
        return "\n".join(lines)

    def get_agents_for_service_type(
        self, service_type: str,
    ) -> Dict[str, AgentDefinition]:
        service = self._services.get(service_type)
        if not service:
            return {}
        return dict(service.agents)

    def get_root_cause_agents(self) -> Set[str]:
        return {
            name
            for service in self._services.values()
            for name, agent_def in service.agents.items()
            if agent_def.is_root_cause
        }

    def load_telemetry_functions(self, service_type: str):
        # Lazy import: modules are loaded on first call, not at registration
        # time. This avoids pulling in heavy SDK deps (boto3, openai) during
        # startup, which would break the import chain.
        service = self._services.get(service_type)
        if not service:
            return None, None
        module = importlib.import_module(service.telemetry_module)
        return (
            getattr(module, "collect_from_resource"),
            getattr(module, "normalize"),
        )

    def load_signal_extractor(self, service_type: str):
        service = self._services.get(service_type)
        if not service:
            return None
        module = importlib.import_module(service.signals_module)
        return getattr(module, "extract_signals")

    def load_report_converter(self, service_type: str):
        service = self._services.get(service_type)
        if not service:
            return None
        module = importlib.import_module(service.report_module)
        return getattr(module, "to_legacy_dict")

    def load_agent_function(self, node_name: str):
        agent_def = self.get_agent_definition(node_name)
        if not agent_def:
            return None
        module = importlib.import_module(agent_def.module_path)
        return getattr(module, agent_def.function_name)


registry = ServiceRegistry()

# Each register.py module calls registry.register() at import time.
# To add a new service, create <service>_agent/register.py and add it here.
_REGISTRATION_MODULES = [
    "agent.ec2_agent.register",
    "agent.s3_agent.register",
    "agent.dynamodb_agent.register",
]


def _discover_services() -> None:
    """Import each registration module so it self-registers with the singleton."""
    for mod_path in _REGISTRATION_MODULES:
        try:
            importlib.import_module(mod_path)
        except Exception as e:
            logger.error(
                "Failed to register service from %s: %s", mod_path, e,
            )


# Runs at import time — must complete before nodes.py reads the registry
# to build SUB_AGENT_NODES.
_discover_services()
