"""
Context engineering layer.

Controls what information each agent sees. Raw telemetry never reaches
an LLM directly — this layer curates the context window with:
  - Relevant signals (not all signals, just the ones this agent cares about)
  - Prior recommendations for this resource (from memory)
  - Cross-agent findings (what other agents have already found)
  - Session history (what has already been decided)

This prevents prompt pollution and keeps each agent focused on its domain.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Signal → sub-agent domain mapping
# ---------------------------------------------------------------------------
# Maps each sub-agent node name to the signals it cares about.
# Agents only see signals in their domain — prevents prompt pollution.

SIGNAL_DOMAIN_MAP = {
    # --- EC2 sub-agents ---
    "ec2_metric": {
        "cpu_sustained_high", "cpu_sustained_low", "cpu_bursty", "cpu_anomaly",
        "memory_pressure_detected", "swap_exhaustion", "oom_killed",
        "ebs_burst_balance_low", "network_saturation_detected", "packet_drops_observed",
        "disk_full_risk",
    },
    "ec2_cost": {
        "instance_idle_high_cost", "cpu_sustained_low", "cpu_bursty",
        "graviton_migration_candidate", "spot_candidate",
    },
    "ec2_reliability": {
        "status_check_failures", "reboot_loop_detected",
        "no_autoscaling", "single_az_deployment",
    },
    "ec2_security": {
        "imdsv1_in_use", "ebs_unencrypted",
        "ssh_rdp_open_to_world", "ami_outdated",
    },
    "ec2_root_cause": {
        "cpu_sustained_high", "cpu_sustained_low", "cpu_bursty", "cpu_anomaly",
        "memory_pressure_detected", "swap_exhaustion", "oom_killed",
        "ebs_burst_balance_low", "network_saturation_detected",
        "status_check_failures", "reboot_loop_detected",
        "deployment_correlated_latency_spike", "disk_full_risk",
    },

    # --- S3 sub-agents ---
    "s3_storage": {
        "excessive_small_objects_detected", "bucket_growth_abnormal",
        "storage_growth_anomaly", "stale_data_accumulation", "small_object_overhead",
    },
    "s3_cost": {
        "missing_lifecycle_policy", "cold_storage_candidate",
        "intelligent_tiering_underutilized", "no_lifecycle_policy",
        "intelligent_tiering_candidate", "glacier_candidate",
        "high_retrieval_cost", "cross_region_transfer_cost",
    },
    "s3_reliability": {
        "versioning_disabled", "replication_failures_detected",
        "no_versioning", "no_replication", "no_access_logging",
    },
    "s3_security": {
        "public_access_risk_detected", "unencrypted_storage_detected",
        "public_bucket_detected", "no_encryption",
    },
    "s3_access": {
        "retrieval_spike_detected", "transfer_cost_anomaly_detected",
        "high_retrieval_cost", "cross_region_transfer_cost",
    },
    "s3_root_cause": {
        "storage_growth_anomaly", "stale_data_accumulation",
        "public_bucket_detected", "no_encryption", "no_versioning",
        "retrieval_spike_detected", "transfer_cost_anomaly_detected",
        "missing_lifecycle_policy", "bucket_growth_abnormal",
    },

    # --- DynamoDB sub-agents ---
    "dynamodb_capacity": {
        "overprovisioned_rcu_detected", "overprovisioned_wcu_detected",
        "overprovisioned_rcu", "overprovisioned_wcu",
        "underprovisioned_rcu", "underprovisioned_wcu",
        "gsi_overprovisioned", "on_demand_candidate", "provisioned_candidate",
    },
    "dynamodb_performance": {
        "throttling_detected", "hot_partition_detected", "retry_storm_detected",
        "retry_storm", "scan_heavy_workload", "latency_anomaly",
    },
    "dynamodb_reliability": {
        "pitr_disabled", "replication_lag_detected",
        "replication_lag_high", "no_backup", "autoscaling_flapping",
    },
    "dynamodb_root_cause": {
        "throttling_detected", "hot_partition_detected", "retry_storm_detected",
        "overprovisioned_rcu_detected", "overprovisioned_wcu_detected",
        "pitr_disabled", "replication_lag_detected",
        "scan_heavy_workload", "latency_anomaly", "autoscaling_flapping",
    },

    # --- Legacy broad mappings (kept for backward compat) ---
    "ec2_specialist": {
        "cpu_sustained_high", "cpu_sustained_low", "cpu_bursty", "cpu_anomaly",
        "memory_pressure_detected", "swap_exhaustion", "oom_killed",
        "ebs_burst_balance_low", "network_saturation_detected", "packet_drops_observed",
        "status_check_failures", "reboot_loop_detected", "no_autoscaling",
        "single_az_deployment", "imdsv1_in_use", "ebs_unencrypted",
        "ssh_rdp_open_to_world", "ami_outdated", "instance_idle_high_cost",
        "graviton_migration_candidate", "spot_candidate",
        "deployment_correlated_latency_spike", "disk_full_risk",
    },
    "s3_specialist": {
        "storage_growth_anomaly", "stale_data_accumulation", "no_lifecycle_policy",
        "public_bucket_detected", "no_encryption", "no_versioning",
        "no_access_logging", "no_replication", "high_retrieval_cost",
        "intelligent_tiering_candidate", "glacier_candidate",
        "small_object_overhead", "cross_region_transfer_cost",
    },
    "dynamodb_specialist": {
        "throttling_detected", "hot_partition_detected", "retry_storm",
        "scan_heavy_workload", "overprovisioned_rcu", "overprovisioned_wcu",
        "underprovisioned_rcu", "underprovisioned_wcu", "replication_lag_high",
        "pitr_disabled", "no_backup", "autoscaling_flapping",
        "gsi_overprovisioned", "on_demand_candidate", "provisioned_candidate",
        "latency_anomaly",
    },
}

# Rec-type relevance per sub-agent (which prior rec types are useful context)
_REC_TYPE_RELEVANCE = {
    "ec2_metric":       {"performance", "reliability"},
    "ec2_cost":         {"cost", "performance"},
    "ec2_reliability":  {"reliability", "performance", "operational"},
    "ec2_security":     {"security"},
    "ec2_root_cause":   {"performance", "reliability", "security", "operational", "cost"},
    "s3_storage":       {"cost", "performance"},
    "s3_cost":          {"cost"},
    "s3_reliability":   {"reliability"},
    "s3_security":      {"security"},
    "s3_access":        {"cost", "performance"},
    "s3_root_cause":    {"performance", "reliability", "security", "operational", "cost"},
    "dynamodb_capacity":     {"cost", "performance"},
    "dynamodb_performance":  {"performance", "reliability"},
    "dynamodb_reliability":  {"reliability"},
    "dynamodb_root_cause":   {"performance", "reliability", "cost", "operational"},
}


def build_agent_context(
    agent_id: str,
    signals: List[Dict[str, Any]],
    resource: Dict[str, Any],
    prior_recommendations: List[Dict[str, Any]],
    session_decisions: List[Dict[str, Any]],
    cross_agent_findings: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Build a curated context payload for a specific agent.
    Filters signals to only include those relevant to this agent's domain.
    """
    domain_signals = SIGNAL_DOMAIN_MAP.get(agent_id, set())

    relevant_signals = [
        s for s in signals
        if s.get("name") in domain_signals or not domain_signals
    ]

    relevant_prior = [
        r for r in prior_recommendations
        if _is_relevant_recommendation(agent_id, r)
    ][-10:]

    recent_decisions = session_decisions[-5:]

    context = {
        "agent_id": agent_id,
        "resource": _slim_resource(resource),
        "signals": relevant_signals,
        "signal_count": len(relevant_signals),
        "prior_recommendations": relevant_prior,
        "recent_decisions": recent_decisions,
    }

    if cross_agent_findings:
        context["cross_agent_findings"] = cross_agent_findings

    recurring = _detect_recurring(relevant_prior)
    if recurring:
        context["recurring_patterns"] = recurring

    return context


def build_cross_agent_summary(
    findings: Dict[str, List[Dict[str, Any]]],
    current_agent: str,
) -> List[Dict[str, Any]]:
    """
    Build a compact summary of what other agents have found.
    Used to give each sub-agent visibility into sibling findings.
    """
    summary = []
    for agent_name, recs in findings.items():
        if agent_name == current_agent or not recs:
            continue
        for rec in recs[:5]:
            summary.append({
                "from_agent": agent_name,
                "rule_id": rec.get("rule_id", ""),
                "title": rec.get("title", ""),
                "type": rec.get("type", ""),
                "severity": rec.get("severity", ""),
                "confidence": rec.get("confidence", 0),
            })
    return summary


def _slim_resource(resource: Dict[str, Any]) -> Dict[str, Any]:
    keep_keys = {
        "resource_id", "name", "type", "region", "status", "monthly_cost",
        "tags", "instance_type", "creation_date", "is_optimized",
    }
    return {k: v for k, v in resource.items() if k in keep_keys}


def _is_relevant_recommendation(agent_id: str, rec: Dict[str, Any]) -> bool:
    rec_type = (rec.get("type") or "").lower()
    allowed = _REC_TYPE_RELEVANCE.get(agent_id)
    if allowed is None:
        return True
    return rec_type in allowed


def _detect_recurring(recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from collections import Counter
    rule_counts = Counter(r.get("rule_id") for r in recommendations if r.get("rule_id"))
    return [
        {"rule_id": rid, "occurrences": count}
        for rid, count in rule_counts.items()
        if count >= 3
    ]


def build_critique_context(
    recommendations: List[Dict[str, Any]],
    signals: List[Dict[str, Any]],
    resource: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "agent_id": "critique",
        "resource": _slim_resource(resource),
        "recommendations_to_review": recommendations,
        "available_signals": signals,
        "review_instructions": {
            "check_evidence": "Every recommendation must cite specific signal evidence",
            "check_confidence": "Flag recommendations with <0.5 confidence",
            "check_conflicts": "Flag contradictory recommendations",
            "check_safety": "Flag anything that could cause outages",
            "check_completeness": "Note important signals that no recommendation addresses",
        },
    }


def build_correlation_context(
    all_findings: Dict[str, List[Dict[str, Any]]],
    resources: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "agent_id": "correlation",
        "resources": [_slim_resource(r) for r in resources],
        "findings_by_agent": {
            agent: findings[:10]
            for agent, findings in all_findings.items()
        },
        "correlation_instructions": {
            "find_dependencies": "Identify resources that affect each other",
            "find_compound_savings": "Find optimizations that amplify when done together",
            "find_conflicts": "Find recommendations that conflict across resources",
        },
    }
