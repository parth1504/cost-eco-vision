"""
DynamoDB service registration for the dynamic service registry.

All DynamoDB domain agents share priority=5. The root-cause agent
(priority=3, is_root_cause=True) is gated: it only runs when domain
agents have already produced findings and >=2 signals are present.
"""

from agent.core.registry import (
    AgentDefinition,
    ServiceDefinition,
    registry,
)

registry.register(ServiceDefinition(
    service_type="DynamoDB",
    telemetry_module="agent.dynamodb_agent.telemetry",
    signals_module="agent.dynamodb_agent.signals",
    report_module="agent.dynamodb_agent.report",
    agents={
        "dynamodb_capacity": AgentDefinition(
            node_name="dynamodb_capacity",
            function_name="capacity_optimization_agent",
            module_path="agent.dynamodb_agent.agents",
            description=(
                "Over/under provisioned RCU/WCU, "
                "on-demand vs provisioned"
            ),
            signal_domain={
                "overprovisioned_rcu_detected",
                "overprovisioned_wcu_detected",
                "overprovisioned_rcu", "overprovisioned_wcu",
                "underprovisioned_rcu", "underprovisioned_wcu",
                "gsi_overprovisioned", "on_demand_candidate",
                "provisioned_candidate",
            },
            rec_type_relevance={"cost", "performance"},
            routing_priority=5,
        ),
        "dynamodb_performance": AgentDefinition(
            node_name="dynamodb_performance",
            function_name="performance_scalability_agent",
            module_path="agent.dynamodb_agent.agents",
            description=(
                "Throttling, hot partitions, retry storms"
            ),
            signal_domain={
                "throttling_detected",
                "hot_partition_detected",
                "retry_storm_detected", "retry_storm",
                "scan_heavy_workload", "latency_anomaly",
            },
            rec_type_relevance={"performance", "reliability"},
            routing_priority=5,
        ),
        "dynamodb_reliability": AgentDefinition(
            node_name="dynamodb_reliability",
            function_name="reliability_agent",
            module_path="agent.dynamodb_agent.agents",
            description=(
                "PITR, replication lag, backups"
            ),
            signal_domain={
                "pitr_disabled", "replication_lag_detected",
                "replication_lag_high", "no_backup",
                "autoscaling_flapping",
            },
            rec_type_relevance={"reliability"},
            routing_priority=5,
        ),
        "dynamodb_root_cause": AgentDefinition(
            node_name="dynamodb_root_cause",
            function_name="root_cause_agent",
            module_path="agent.dynamodb_agent.agents",
            description=(
                "LLM-powered causal analysis for DynamoDB"
            ),
            signal_domain={
                "throttling_detected",
                "hot_partition_detected",
                "retry_storm_detected",
                "overprovisioned_rcu_detected",
                "overprovisioned_wcu_detected",
                "pitr_disabled", "replication_lag_detected",
                "scan_heavy_workload", "latency_anomaly",
                "autoscaling_flapping",
            },
            rec_type_relevance={
                "performance", "reliability",
                "cost", "operational",
            },
            is_root_cause=True,
            routing_priority=3,
        ),
    },
))
