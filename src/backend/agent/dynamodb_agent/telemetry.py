"""
Collector + Normalizer for DynamoDB intelligence analysis.

The collector builds a `TelemetryBundle` from:
    - the legacy DynamoDB resource dict
    - capacity telemetry
    - latency telemetry
    - partition behavior
    - throttling behavior
    - autoscaling metadata
    - reliability configuration
    - optional workload/application telemetry

The normalizer converts heterogeneous DynamoDB metrics into:
    - typed MetricSeries
    - structured workload metadata
    - scalable signal-friendly telemetry

IMPORTANT:
The LLM MUST NOT consume raw DynamoDB telemetry directly.

This layer exists to:
    normalize
        →
    structure
        →
    prepare intelligence-ready telemetry

for the signal extraction layer.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from agent.dynamodb_agent.types import (
    MetricSeries,
    TelemetryBundle,
)


# ---------------------------------------------------------------------------
# MetricSeries Helper
# ---------------------------------------------------------------------------

def _series_from_avg_max(
    name: str,
    avg: Optional[float],
    maximum: Optional[float],
    unit: str = "",
) -> Optional[MetricSeries]:

    """
    Build lightweight MetricSeries objects from
    avg/max summary telemetry.

    A synthetic minimal series is generated so:
        - anomaly detection
        - trend analysis
        - signal extraction

    can still operate even when only summary metrics exist.
    """

    if avg is None and maximum is None:
        return None

    now = datetime.utcnow()

    points = []

    if avg is not None:
        points.append(
            (
                now - timedelta(days=3),
                float(avg),
            )
        )

    if maximum is not None:
        points.append(
            (
                now,
                float(maximum),
            )
        )

    return MetricSeries(
        name=name,
        points=points,
        unit=unit,

        explicit_avg=(
            float(avg)
            if avg is not None
            else None
        ),

        explicit_max=(
            float(maximum)
            if maximum is not None
            else None
        ),
    )


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

def collect_from_resource(
    resource: Dict[str, Any],
) -> TelemetryBundle:

    """
    Build TelemetryBundle from:
        aws/dynamodb.py:build_dynamodb_resource()

    Missing telemetry is tolerated intentionally.

    Downstream signal extraction handles sparse metrics gracefully.
    """

    metrics = resource.get("metrics") or {}
    config = resource.get("config") or {}
    metadata = resource.get("metadata") or {}

    creation_iso = metadata.get("creation_date")

    creation_time: Optional[datetime] = None

    if creation_iso:
        try:
            creation_time = datetime.fromisoformat(
                creation_iso.replace("Z", "")
            )
        except Exception:
            creation_time = None

    bundle = TelemetryBundle(

        #
        # Table identity
        #
        table_name=(
            resource.get("name")
            or resource.get("resource_id")
            or ""
        ),

        table_id=(
            resource.get("resource_id")
            or ""
        ),

        region=resource.get("region") or "",

        state=resource.get("status") or "",

        creation_time=creation_time,

        monthly_cost=float(
            resource.get("monthly_cost") or 0
        ),

        tags=resource.get("tags") or {},

        #
        # Capacity telemetry
        #
        consumed_rcu=_series_from_avg_max(
            "consumed_rcu",
            metrics.get("consumed_rcu_avg"),
            metrics.get("consumed_rcu_peak"),
            "RCU",
        ),

        provisioned_rcu=_series_from_avg_max(
            "provisioned_rcu",
            metrics.get("provisioned_rcu_avg"),
            metrics.get("provisioned_rcu_peak"),
            "RCU",
        ),

        consumed_wcu=_series_from_avg_max(
            "consumed_wcu",
            metrics.get("consumed_wcu_avg"),
            metrics.get("consumed_wcu_peak"),
            "WCU",
        ),

        provisioned_wcu=_series_from_avg_max(
            "provisioned_wcu",
            metrics.get("provisioned_wcu_avg"),
            metrics.get("provisioned_wcu_peak"),
            "WCU",
        ),

        rcu_utilization=_series_from_avg_max(
            "rcu_utilization",
            metrics.get("rcu_utilization_avg"),
            metrics.get("rcu_utilization_peak"),
            "%",
        ),

        wcu_utilization=_series_from_avg_max(
            "wcu_utilization",
            metrics.get("wcu_utilization_avg"),
            metrics.get("wcu_utilization_peak"),
            "%",
        ),

        burst_capacity_usage=_series_from_avg_max(
            "burst_capacity_usage",
            metrics.get("burst_usage_avg"),
            metrics.get("burst_usage_peak"),
            "%",
        ),

        #
        # Performance telemetry
        #
        throttled_requests=_series_from_avg_max(
            "throttled_requests",
            metrics.get("throttled_requests_avg"),
            metrics.get("throttled_requests_peak"),
            "requests",
        ),

        retry_rate=_series_from_avg_max(
            "retry_rate",
            metrics.get("retry_rate_avg"),
            metrics.get("retry_rate_peak"),
            "%",
        ),

        timeout_rate=_series_from_avg_max(
            "timeout_rate",
            metrics.get("timeout_rate_avg"),
            metrics.get("timeout_rate_peak"),
            "%",
        ),

        failed_requests=_series_from_avg_max(
            "failed_requests",
            metrics.get("failed_requests_avg"),
            metrics.get("failed_requests_peak"),
            "requests",
        ),

        p95_latency=_series_from_avg_max(
            "p95_latency",
            metrics.get("p95_latency_avg"),
            metrics.get("p95_latency_peak"),
            "ms",
        ),

        p99_latency=_series_from_avg_max(
            "p99_latency",
            metrics.get("p99_latency_avg"),
            metrics.get("p99_latency_peak"),
            "ms",
        ),

        scan_frequency=_series_from_avg_max(
            "scan_frequency",
            metrics.get("scan_frequency_avg"),
            metrics.get("scan_frequency_peak"),
            "scans",
        ),

        #
        # Partition behavior
        #
        hot_partition_ratio=_series_from_avg_max(
            "hot_partition_ratio",
            metrics.get("hot_partition_ratio_avg"),
            metrics.get("hot_partition_ratio_peak"),
            "%",
        ),

        partition_skew_ratio=_series_from_avg_max(
            "partition_skew_ratio",
            metrics.get("partition_skew_avg"),
            metrics.get("partition_skew_peak"),
            "%",
        ),

        adaptive_capacity_usage=_series_from_avg_max(
            "adaptive_capacity_usage",
            metrics.get("adaptive_capacity_avg"),
            metrics.get("adaptive_capacity_peak"),
            "%",
        ),

        #
        # Cost telemetry
        #
        read_cost=_series_from_avg_max(
            "read_cost",
            metrics.get("read_cost_avg"),
            metrics.get("read_cost_peak"),
            "usd",
        ),

        write_cost=_series_from_avg_max(
            "write_cost",
            metrics.get("write_cost_avg"),
            metrics.get("write_cost_peak"),
            "usd",
        ),

        storage_cost=_series_from_avg_max(
            "storage_cost",
            metrics.get("storage_cost_avg"),
            metrics.get("storage_cost_peak"),
            "usd",
        ),

        backup_cost=_series_from_avg_max(
            "backup_cost",
            metrics.get("backup_cost_avg"),
            metrics.get("backup_cost_peak"),
            "usd",
        ),

        gsi_cost=_series_from_avg_max(
            "gsi_cost",
            metrics.get("gsi_cost_avg"),
            metrics.get("gsi_cost_peak"),
            "usd",
        ),

        #
        # Reliability + DR telemetry
        #
        replication_lag=_series_from_avg_max(
            "replication_lag",
            metrics.get("replication_lag_avg"),
            metrics.get("replication_lag_peak"),
            "seconds",
        ),

        autoscaling_flaps=_series_from_avg_max(
            "autoscaling_flaps",
            metrics.get("autoscaling_flaps_avg"),
            metrics.get("autoscaling_flaps_peak"),
            "events",
        ),

        #
        # Configuration
        #
        billing_mode=config.get("billing_mode"),

        pitr_enabled=config.get("pitr_enabled"),

        streams_enabled=config.get("streams_enabled"),

        autoscaling_enabled=config.get(
            "autoscaling_enabled"
        ),

        global_table_enabled=config.get(
            "global_table_enabled"
        ),

        encryption_enabled=config.get(
            "encryption_enabled"
        ),

        kms_key=config.get("kms_key"),

        backup_enabled=config.get(
            "backup_enabled"
        ),

        table_class=config.get("table_class"),

        gsis=config.get("gsis") or [],

        partition_key=config.get(
            "partition_key"
        ),

        sort_key=config.get("sort_key"),

        #
        # Operational telemetry
        #
        events=resource.get("events") or [],

        log_signals=resource.get(
            "log_signals"
        ) or {},

        workload_patterns=resource.get(
            "workload_patterns"
        ) or {},

        historical_trends=resource.get(
            "historical_trends"
        ) or {},
    )

    return bundle


# ---------------------------------------------------------------------------
# Normalization Hook
# ---------------------------------------------------------------------------

def normalize(
    bundle: TelemetryBundle,
) -> TelemetryBundle:

    """
    Hook for future telemetry cleanup.

    Future capabilities:
        - anomaly smoothing
        - seasonality normalization
        - partition skew correction
        - sparse metric interpolation
        - workload normalization
        - retry amplification cleanup

    Identity behavior for now.
    """

    return bundle