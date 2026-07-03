"""
Collector + Normalizer for S3 intelligence analysis.

The collector builds a `TelemetryBundle` for a bucket from:
  - the resource dict the legacy pipeline already produces
  - storage metrics
  - access behavior
  - lifecycle configuration
  - replication telemetry
  - security posture
  - cost metadata

The normalizer adapts heterogeneous bucket telemetry into
typed MetricSeries + structured storage intelligence fields.

IMPORTANT:
The goal is NOT raw telemetry dumping.

This layer prepares clean, structured telemetry so the
signal extraction layer can reason about storage behavior,
cost anomalies, durability risks, and access patterns.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from agent.s3_agent.types import MetricSeries, TelemetryBundle


def _series_from_avg_max(
    name: str,
    avg: Optional[float],
    maximum: Optional[float],
    unit: str = "",
) -> Optional[MetricSeries]:
    """
    Build a lightweight MetricSeries from avg/max summaries.

    We synthesize a minimal time series so downstream anomaly
    systems and signal extraction logic can still operate even
    when only summarized metrics are available.
    """

    if avg is None and maximum is None:
        return None

    now = datetime.utcnow()

    points = []

    if avg is not None:
        points.append((now - timedelta(days=3), float(avg)))

    if maximum is not None:
        points.append((now, float(maximum)))

    return MetricSeries(
        name=name,
        points=points,
        unit=unit,
        explicit_avg=float(avg) if avg is not None else None,
        explicit_max=float(maximum) if maximum is not None else None,
    )


def collect_from_resource(resource: Dict[str, Any]) -> TelemetryBundle:
    """
    Build a TelemetryBundle from the legacy S3 resource dict.

    The resource shape comes from:
        aws/s3.py:build_s3_resource()

    Missing fields are tolerated intentionally —
    downstream signal extraction handles sparse telemetry.
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
        bucket_name=resource.get("name") or "",
        bucket_id=resource.get("resource_id") or "",
        region=resource.get("region") or "",
        state=resource.get("status") or "",
        creation_time=creation_time,

        monthly_cost=float(resource.get("monthly_cost") or 0),

        #
        # Storage telemetry
        #
        total_storage_bytes=_series_from_avg_max(
            "storage_bytes",
            metrics.get("storage_avg_7d"),
            metrics.get("storage_peak_7d"),
            "bytes",
        ),

        object_count=_series_from_avg_max(
            "object_count",
            metrics.get("object_count_avg_7d"),
            metrics.get("object_count_peak_7d"),
            "objects",
        ),

        storage_growth_rate=_series_from_avg_max(
            "storage_growth",
            metrics.get("growth_avg_7d"),
            metrics.get("growth_peak_7d"),
            "bytes/day",
        ),

        small_object_ratio=_series_from_avg_max(
            "small_object_ratio",
            metrics.get("small_object_ratio_avg"),
            metrics.get("small_object_ratio_peak"),
            "%",
        ),

        stale_object_ratio=_series_from_avg_max(
            "stale_object_ratio",
            metrics.get("stale_object_ratio_avg"),
            metrics.get("stale_object_ratio_peak"),
            "%",
        ),

        #
        # Access behavior
        #
        get_requests=_series_from_avg_max(
            "get_requests",
            metrics.get("get_requests_avg_7d"),
            metrics.get("get_requests_peak_7d"),
            "requests",
        ),

        put_requests=_series_from_avg_max(
            "put_requests",
            metrics.get("put_requests_avg_7d"),
            metrics.get("put_requests_peak_7d"),
            "requests",
        ),

        retrieval_rate=_series_from_avg_max(
            "retrieval_rate",
            metrics.get("retrieval_avg_7d"),
            metrics.get("retrieval_peak_7d"),
            "retrievals",
        ),

        data_transfer_out=_series_from_avg_max(
            "transfer_out",
            metrics.get("transfer_out_avg_7d"),
            metrics.get("transfer_out_peak_7d"),
            "bytes",
        ),

        access_spikes=_series_from_avg_max(
            "access_spikes",
            metrics.get("access_spike_avg"),
            metrics.get("access_spike_peak"),
            "events",
        ),

        #
        # Lifecycle + storage class telemetry
        #
        glacier_transition_rate=_series_from_avg_max(
            "glacier_transitions",
            metrics.get("glacier_transition_avg"),
            metrics.get("glacier_transition_peak"),
            "objects",
        ),

        intelligent_tiering_ratio=_series_from_avg_max(
            "intelligent_tiering_ratio",
            metrics.get("intelligent_tiering_avg"),
            metrics.get("intelligent_tiering_peak"),
            "%",
        ),

        lifecycle_transition_failures=_series_from_avg_max(
            "lifecycle_failures",
            metrics.get("lifecycle_failure_avg"),
            metrics.get("lifecycle_failure_peak"),
            "failures",
        ),

        #
        # Replication + durability telemetry
        #
        replication_latency=_series_from_avg_max(
            "replication_latency",
            metrics.get("replication_latency_avg"),
            metrics.get("replication_latency_peak"),
            "seconds",
        ),

        replication_failures=_series_from_avg_max(
            "replication_failures",
            metrics.get("replication_failure_avg"),
            metrics.get("replication_failure_peak"),
            "failures",
        ),

        #
        # Cost telemetry
        #
        storage_cost=_series_from_avg_max(
            "storage_cost",
            metrics.get("storage_cost_avg"),
            metrics.get("storage_cost_peak"),
            "usd",
        ),

        retrieval_cost=_series_from_avg_max(
            "retrieval_cost",
            metrics.get("retrieval_cost_avg"),
            metrics.get("retrieval_cost_peak"),
            "usd",
        ),

        transfer_cost=_series_from_avg_max(
            "transfer_cost",
            metrics.get("transfer_cost_avg"),
            metrics.get("transfer_cost_peak"),
            "usd",
        ),

        #
        # Security posture
        #
        public_access_enabled=config.get("public_access_enabled"),
        encryption_enabled=config.get("encryption_enabled"),
        kms_enabled=config.get("kms_enabled"),
        versioning_enabled=config.get("versioning_enabled"),
        mfa_delete_enabled=config.get("mfa_delete_enabled"),

        access_logging_enabled=config.get("access_logging_enabled"),

        replication_enabled=config.get("replication_enabled"),

        lifecycle_enabled=config.get("lifecycle_enabled"),

        object_lock_enabled=config.get("object_lock_enabled"),

        bucket_policy=config.get("bucket_policy") or {},

        acl=config.get("acl") or {},

        tags=resource.get("tags") or {},

        #
        # Optional operational telemetry
        #
        events=resource.get("events") or [],

        audit_findings=resource.get("audit_findings") or {},

        access_patterns=resource.get("access_patterns") or {},

        historical_trends=resource.get("historical_trends") or {},
    )

    return bundle


def normalize(bundle: TelemetryBundle) -> TelemetryBundle:
    """
    Hook for future telemetry cleanup.

    Future responsibilities:
      - outlier clipping
      - sparse-series interpolation
      - unit normalization
      - seasonality normalization
      - request burst smoothing
      - duplicate metric reconciliation

    Keeping identity behavior for now.
    """

    return bundle