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
    """A single sub-agent within a service."""
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
    """Everything the pipeline needs to work with a service."""
    service_type: str
    telemetry_module: str
    signals_module: str
    report_module: str
    agents: Dict[str, AgentDefinition] = field(default_factory=dict)


class ServiceRegistry:

    def __init__(self) -> None:
        self._services: Dict[str, ServiceDefinition] = {}
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
        domain_map: Dict[str, Set[str]] = {}
        for service in self._services.values():
            for agent_name, agent_def in service.agents.items():
                if agent_def.signal_domain:
                    domain_map[agent_name] = set(agent_def.signal_domain)
        return domain_map

    def get_rec_type_relevance(self) -> Dict[str, Set[str]]:
        relevance: Dict[str, Set[str]] = {}
        for service in self._services.values():
            for agent_name, agent_def in service.agents.items():
                if agent_def.rec_type_relevance:
                    relevance[agent_name] = set(agent_def.rec_type_relevance)
        return relevance

    def get_router_agent_descriptions(self) -> str:
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


_REGISTRATION_MODULES = [
    "agent.ec2_agent.register",
    "agent.s3_agent.register",
    "agent.dynamodb_agent.register",
]


def _discover_services() -> None:
    for mod_path in _REGISTRATION_MODULES:
        try:
            importlib.import_module(mod_path)
        except Exception as e:
            logger.error(
                "Failed to register service from %s: %s", mod_path, e,
            )


_discover_services()
