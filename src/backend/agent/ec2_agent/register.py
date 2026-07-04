"""EC2 service registration for the dynamic service registry."""

from agent.core.registry import (
    AgentDefinition,
    ServiceDefinition,
    registry,
)

registry.register(ServiceDefinition(
    service_type="EC2",
    telemetry_module="agent.ec2_agent.telemetry",
    signals_module="agent.ec2_agent.signals",
    report_module="agent.ec2_agent.report",
    agents={
        "ec2_metric": AgentDefinition(
            node_name="ec2_metric",
            function_name="metric_analyzer_agent",
            module_path="agent.ec2_agent.agents",
            description=(
                "CPU/memory/network/EBS threshold "
                "violations and trends"
            ),
            signal_domain={
                "cpu_sustained_high", "cpu_sustained_low",
                "cpu_bursty", "cpu_anomaly",
                "memory_pressure_detected", "swap_exhaustion",
                "oom_killed", "ebs_burst_balance_low",
                "network_saturation_detected",
                "packet_drops_observed", "disk_full_risk",
            },
            rec_type_relevance={"performance", "reliability"},
            routing_priority=10,
        ),
        "ec2_cost": AgentDefinition(
            node_name="ec2_cost",
            function_name="cost_optimization_agent",
            module_path="agent.ec2_agent.agents",
            description=(
                "Idle instances, rightsizing, Graviton, "
                "Spot, ASG savings"
            ),
            signal_domain={
                "instance_idle_high_cost", "cpu_sustained_low",
                "cpu_bursty", "graviton_migration_candidate",
                "spot_candidate",
            },
            rec_type_relevance={"cost", "performance"},
            routing_signals={
                "instance_idle_high_cost", "cpu_sustained_low",
                "graviton_migration_candidate", "spot_candidate",
                "cpu_bursty",
            },
            routing_priority=8,
        ),
        "ec2_reliability": AgentDefinition(
            node_name="ec2_reliability",
            function_name="reliability_agent",
            module_path="agent.ec2_agent.agents",
            description=(
                "Health check failures, single-AZ, missing ASG"
            ),
            signal_domain={
                "status_check_failures", "reboot_loop_detected",
                "no_autoscaling", "single_az_deployment",
            },
            rec_type_relevance={
                "reliability", "performance", "operational",
            },
            routing_signals={
                "status_check_failures", "reboot_loop_detected",
                "no_autoscaling", "single_az_deployment",
            },
            routing_priority=7,
        ),
        "ec2_security": AgentDefinition(
            node_name="ec2_security",
            function_name="security_agent",
            module_path="agent.ec2_agent.agents",
            description=(
                "IMDSv2 gaps, unencrypted EBS, "
                "open SSH/RDP, outdated AMIs"
            ),
            signal_domain={
                "imdsv1_in_use", "ebs_unencrypted",
                "ssh_rdp_open_to_world", "ami_outdated",
            },
            rec_type_relevance={"security"},
            routing_signals={
                "imdsv1_in_use", "ebs_unencrypted",
                "ssh_rdp_open_to_world", "ami_outdated",
            },
            routing_priority=6,
        ),
        "ec2_root_cause": AgentDefinition(
            node_name="ec2_root_cause",
            function_name="root_cause_agent",
            module_path="agent.ec2_agent.agents",
            description=(
                "LLM-powered causal correlation "
                "of signals+events"
            ),
            signal_domain={
                "cpu_sustained_high", "cpu_sustained_low",
                "cpu_bursty", "cpu_anomaly",
                "memory_pressure_detected", "swap_exhaustion",
                "oom_killed", "ebs_burst_balance_low",
                "network_saturation_detected",
                "status_check_failures", "reboot_loop_detected",
                "deployment_correlated_latency_spike",
                "disk_full_risk",
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
