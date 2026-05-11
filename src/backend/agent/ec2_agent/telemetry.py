"""
Collector + Normalizer.

The collector builds a `TelemetryBundle` for an instance from:
  - the resource dict the legacy pipeline already produces (so we slot in
    without changing how data is fetched)
  - additional CloudWatch series (memory, disk, EBS burst, packet drops)
    where available
  - mocked/optional data (logs, deployments, APM) when the integration
    isn't wired

The normalizer is mostly a data-shape adapter — turning the existing
`metrics.cpu.avg_7d` / `metrics.network.in_avg_7d` shape into typed
MetricSeries. We accept that some series will be absent (None) and let
the feature-extraction layer handle that gracefully.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from agent.ec2_agent.types import MetricSeries, TelemetryBundle


def _series_from_avg_max(name: str, avg: Optional[float], maximum: Optional[float], unit: str = "") -> Optional[MetricSeries]:
    """
    Build a MetricSeries from existing avg/max summary values. Sets
    `explicit_avg` / `explicit_max` so the properties return the real
    summary stats instead of recomputing from synthesized points.

    A synthetic 2-point series is still populated so anomaly detection
    has something to work with — but the avg/max properties bypass it.
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
    Build a TelemetryBundle from the legacy resource dict that
    `aws/ec2.py:build_ec2_resource()` produces.

    Falls back gracefully for missing fields — the feature layer skips
    signals that need data we don't have.
    """
    metrics = resource.get("metrics") or {}
    cpu = metrics.get("cpu") or {}
    network = metrics.get("network") or {}
    disk = metrics.get("disk") or {}
    health = metrics.get("health") or {}
    config = resource.get("config") or {}

    # Parse launch time if present.
    launch_iso = resource.get("creation_date")
    launch_time: Optional[datetime] = None
    if launch_iso:
        try:
            launch_time = datetime.fromisoformat(launch_iso.replace("Z", ""))
        except Exception:
            launch_time = None

    bundle = TelemetryBundle(
        instance_id=resource.get("resource_id") or resource.get("name") or "",
        region=resource.get("region") or "",
        state=resource.get("status") or "",
        launch_time=launch_time,
        tags=resource.get("tags") or {},
        monthly_cost=float(resource.get("monthly_cost") or 0),
       

        cpu=_series_from_avg_max("cpu", cpu.get("avg_7d"), cpu.get("max_7d"), "%"),

        memory=_series_from_avg_max("memory", metrics.get("memory_avg_7d"), metrics.get("memory_max_7d"), "%"),
        swap=_series_from_avg_max("swap", metrics.get("swap_avg_7d"), metrics.get("swap_max_7d"), "%"),
        disk_used_pct=_series_from_avg_max("disk_used", metrics.get("disk_used_avg"), metrics.get("disk_used_max"), "%"),
        ebs_burst_balance=_series_from_avg_max("ebs_burst", metrics.get("ebs_burst_avg"), metrics.get("ebs_burst_min"), "%"),
        packet_drops=_series_from_avg_max("packet_drops", metrics.get("packet_drops_avg"), metrics.get("packet_drops_max")),
        tcp_connections=_series_from_avg_max("tcp_conn", metrics.get("tcp_conn_avg"), metrics.get("tcp_conn_max")),
        process_count=_series_from_avg_max("processes", metrics.get("process_avg"), metrics.get("process_max")),
        p95_latency=_series_from_avg_max("p95_latency", metrics.get("p95_avg"), metrics.get("p95_max"), "ms"),
        p99_latency=_series_from_avg_max("p99_latency", metrics.get("p99_avg"), metrics.get("p99_max"), "ms"),
        status_check_failed=_series_from_avg_max("status_check", health.get("status_check_failed_avg"), health.get("status_check_failed_max")),
        reboot_count_7d=int(resource.get("reboot_count_7d") or 0),

        disk_read_iops=_series_from_avg_max("disk_read_iops", disk.get("read_avg_7d"), disk.get("read_peak_7d"), "ops/s"),
        disk_write_iops=_series_from_avg_max("disk_write_iops", disk.get("write_avg_7d"), disk.get("write_peak_7d"), "ops/s"),
        
        network_in=_series_from_avg_max("net_in", network.get("in_avg_7d"), network.get("in_peak_7d"), "bytes/s"),
        network_out=_series_from_avg_max("net_out", network.get("out_avg_7d"), network.get("out_peak_7d"), "bytes/s"),

        is_spot=bool(config.get("is_spot")),
        is_reserved=bool(config.get("is_reserved")),
        
        imdsv2_required=config.get("imdsv2_required"),
        ebs_encrypted=config.get("ebs_encrypted"),
        public_ip=config.get("public_ip"),
        open_ports_world=config.get("open_ports_world") or [],
        ami_age_days=config.get("ami_age_days"),

        autoscaling_attached=config.get("autoscaling_attached"),
        autoscaling_az_count=config.get("autoscaling_az_count"),

        events=resource.get("events") or [],
        log_signals=resource.get("log_signals") or {},
    )
    return bundle


def normalize(bundle: TelemetryBundle) -> TelemetryBundle:
    """
    Identity for now. Hook for future cleanup (clipping outliers, gap-filling)
    so the rest of the pipeline can rely on the bundle being well-formed.
    """
    return bundle
