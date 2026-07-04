"""S3 service registration for the dynamic service registry."""

from agent.core.registry import (
    AgentDefinition,
    ServiceDefinition,
    registry,
)

registry.register(ServiceDefinition(
    service_type="S3",
    telemetry_module="agent.s3_agent.telemetry",
    signals_module="agent.s3_agent.signals",
    report_module="agent.s3_agent.report",
    agents={
        "s3_storage": AgentDefinition(
            node_name="s3_storage",
            function_name="storage_utilization_agent",
            module_path="agent.s3_agent.agents",
            description=(
                "Storage utilization anomalies, "
                "small object overhead"
            ),
            signal_domain={
                "excessive_small_objects_detected",
                "bucket_growth_abnormal",
                "storage_growth_anomaly",
                "stale_data_accumulation",
                "small_object_overhead",
            },
            rec_type_relevance={"cost", "performance"},
            routing_priority=5,
        ),
        "s3_cost": AgentDefinition(
            node_name="s3_cost",
            function_name="cost_optimization_agent",
            module_path="agent.s3_agent.agents",
            description=(
                "Lifecycle policies, tiering, "
                "cold storage opportunities"
            ),
            signal_domain={
                "missing_lifecycle_policy",
                "cold_storage_candidate",
                "intelligent_tiering_underutilized",
                "no_lifecycle_policy",
                "intelligent_tiering_candidate",
                "glacier_candidate",
                "high_retrieval_cost",
                "cross_region_transfer_cost",
            },
            rec_type_relevance={"cost"},
            routing_priority=5,
        ),
        "s3_reliability": AgentDefinition(
            node_name="s3_reliability",
            function_name="reliability_agent",
            module_path="agent.s3_agent.agents",
            description=(
                "Versioning, replication, "
                "access logging gaps"
            ),
            signal_domain={
                "versioning_disabled",
                "replication_failures_detected",
                "no_versioning", "no_replication",
                "no_access_logging",
            },
            rec_type_relevance={"reliability"},
            routing_priority=5,
        ),
        "s3_security": AgentDefinition(
            node_name="s3_security",
            function_name="security_agent",
            module_path="agent.s3_agent.agents",
            description=(
                "Public access risks, encryption gaps"
            ),
            signal_domain={
                "public_access_risk_detected",
                "unencrypted_storage_detected",
                "public_bucket_detected",
                "no_encryption",
            },
            rec_type_relevance={"security"},
            routing_priority=5,
        ),
        "s3_access": AgentDefinition(
            node_name="s3_access",
            function_name="access_pattern_agent",
            module_path="agent.s3_agent.agents",
            description=(
                "Retrieval spikes, transfer cost anomalies"
            ),
            signal_domain={
                "retrieval_spike_detected",
                "transfer_cost_anomaly_detected",
                "high_retrieval_cost",
                "cross_region_transfer_cost",
            },
            rec_type_relevance={"cost", "performance"},
            routing_priority=5,
        ),
        "s3_root_cause": AgentDefinition(
            node_name="s3_root_cause",
            function_name="root_cause_agent",
            module_path="agent.s3_agent.agents",
            description=(
                "LLM-powered causal analysis for S3"
            ),
            signal_domain={
                "storage_growth_anomaly",
                "stale_data_accumulation",
                "public_bucket_detected",
                "no_encryption", "no_versioning",
                "retrieval_spike_detected",
                "transfer_cost_anomaly_detected",
                "missing_lifecycle_policy",
                "bucket_growth_abnormal",
            },
            rec_type_relevance={
                "performance", "reliability", "security",
                "operational", "cost",
            },
            is_root_cause=True,
            routing_priority=3,
        ),
    },
))
