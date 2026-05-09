"""
Signal extraction layer for DynamoDB intelligence analysis.

This is the load-bearing intelligence layer.

The LLM and downstream agents MUST NEVER consume
raw DynamoDB telemetry directly.

Instead:
    raw telemetry
        →
    normalized telemetry
        →
    intelligence signals
        →
    recommendations

Signals represent:
    - throttling behavior
    - partition imbalance
    - hot keys
    - autoscaling instability
    - retry amplification
    - excessive scans
    - overprovisioning
    - PITR gaps
    - replication lag
    - latency anomalies

This architecture prevents:
    - hallucinated optimization advice
    - naive threshold reasoning
    - unsafe throughput reductions
    - generic DynamoDB recommendations
"""

from __future__ import annotations

import statistics
from typing import List, Optional

from agent.dynamodb_agent.types import (
    MetricSeries,
    Severity,
    Signal,
    TelemetryBundle,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_data(
    series: Optional[MetricSeries],
) -> bool:

    return (
        series is not None
        and len(series.points) > 0
        and series.avg is not None
    )


def _zscore_anomaly(
    values: List[float],
    threshold: float = 2.5,
) -> Optional[float]:

    """
    Lightweight anomaly detection.

    Detects latest datapoint deviation
    from recent baseline behavior.
    """

    if not values or len(values) < 4:
        return None

    history = values[:-1]

    latest = values[-1]

    mu = statistics.mean(history)

    sigma = (
        statistics.pstdev(history)
        if len(history) > 1
        else 0.0
    )

    if sigma == 0:
        return (
            0.0
            if latest == mu
            else float("inf")
        )

    z = (latest - mu) / sigma

    return z if abs(z) >= threshold else None


# ---------------------------------------------------------------------------
# Capacity Signals
# ---------------------------------------------------------------------------

def _capacity_signals(
    b: TelemetryBundle,
) -> List[Signal]:

    out: List[Signal] = []

    #
    # Overprovisioned RCUs
    #
    if (
        _has_data(b.rcu_utilization)
        and (b.rcu_utilization.avg or 0) < 20
        and b.monthly_cost > 0
    ):
        out.append(
            Signal(
                name="overprovisioned_read_capacity",
                description=(
                    "Provisioned read capacity utilization "
                    "is consistently low."
                ),
                severity=Severity.MEDIUM,
                confidence=0.90,
                evidence={
                    "rcu_utilization_avg":
                        b.rcu_utilization.avg,
                    "monthly_cost":
                        b.monthly_cost,
                },
            )
        )

    #
    # Overprovisioned WCUs
    #
    if (
        _has_data(b.wcu_utilization)
        and (b.wcu_utilization.avg or 0) < 20
    ):
        out.append(
            Signal(
                name="overprovisioned_write_capacity",
                description=(
                    "Provisioned write capacity utilization "
                    "is consistently low."
                ),
                severity=Severity.MEDIUM,
                confidence=0.88,
                evidence={
                    "wcu_utilization_avg":
                        b.wcu_utilization.avg,
                },
            )
        )

    #
    # Burst dependency
    #
    if (
        _has_data(b.burst_capacity_usage)
        and (b.burst_capacity_usage.max or 0) > 80
    ):
        out.append(
            Signal(
                name="excessive_burst_capacity_usage",
                description=(
                    "Workload heavily depends on burst capacity, "
                    "increasing throttling risk during spikes."
                ),
                severity=Severity.WARNING,
                confidence=0.82,
                evidence={
                    "burst_capacity_peak":
                        b.burst_capacity_usage.max,
                },
            )
        )

    #
    # Autoscaling instability
    #
    if (
        _has_data(b.autoscaling_flaps)
        and (b.autoscaling_flaps.max or 0) >= 3
    ):
        out.append(
            Signal(
                name="autoscaling_instability_detected",
                description=(
                    "Autoscaling configuration appears unstable "
                    "with repeated scaling fluctuations."
                ),
                severity=Severity.MEDIUM,
                confidence=0.84,
                evidence={
                    "autoscaling_flaps":
                        b.autoscaling_flaps.max,
                },
            )
        )

    return out


# ---------------------------------------------------------------------------
# Performance + Scalability Signals
# ---------------------------------------------------------------------------

def _performance_signals(
    b: TelemetryBundle,
) -> List[Signal]:

    out: List[Signal] = []

    #
    # Throttling
    #
    if (
        _has_data(b.throttled_requests)
        and (b.throttled_requests.max or 0) > 0
    ):
        out.append(
            Signal(
                name="throttling_detected",
                description=(
                    "DynamoDB throttling events detected."
                ),
                severity=Severity.HIGH,
                confidence=0.95,
                evidence={
                    "throttled_requests_max":
                        b.throttled_requests.max,
                },
            )
        )

    #
    # Hot partitions
    #
    if (
        _has_data(b.hot_partition_ratio)
        and (b.hot_partition_ratio.max or 0) > 30
    ):
        out.append(
            Signal(
                name="hot_partition_detected",
                description=(
                    "Partition utilization is highly skewed, "
                    "suggesting hot partitions or hot keys."
                ),
                severity=Severity.HIGH,
                confidence=0.90,
                evidence={
                    "hot_partition_ratio":
                        b.hot_partition_ratio.max,
                },
            )
        )

    #
    # Partition imbalance
    #
    if (
        _has_data(b.partition_skew_ratio)
        and (b.partition_skew_ratio.avg or 0) > 40
    ):
        out.append(
            Signal(
                name="partition_imbalance_detected",
                description=(
                    "Partition access patterns appear uneven "
                    "across the table."
                ),
                severity=Severity.WARNING,
                confidence=0.85,
                evidence={
                    "partition_skew_ratio":
                        b.partition_skew_ratio.avg,
                },
            )
        )

    #
    # Excessive scans
    #
    if (
        _has_data(b.scan_frequency)
        and (b.scan_frequency.avg or 0) > 1000
    ):
        out.append(
            Signal(
                name="scan_heavy_workload",
                description=(
                    "Workload relies heavily on Scan operations, "
                    "increasing latency and read costs."
                ),
                severity=Severity.HIGH,
                confidence=0.90,
                evidence={
                    "scan_frequency_avg":
                        b.scan_frequency.avg,
                },
            )
        )

    #
    # Retry storms
    #
    if (
        _has_data(b.retry_rate)
        and (b.retry_rate.max or 0) > 25
    ):
        out.append(
            Signal(
                name="retry_storm_detected",
                description=(
                    "Retry amplification behavior detected."
                ),
                severity=Severity.CRITICAL,
                confidence=0.90,
                evidence={
                    "retry_rate_peak":
                        b.retry_rate.max,
                },
            )
        )

    #
    # Latency anomalies
    #
    if _has_data(b.p99_latency):

        z = _zscore_anomaly(
            b.p99_latency.values
        )

        if z is not None:

            out.append(
                Signal(
                    name="latency_anomaly_detected",
                    description=(
                        "p99 latency deviates significantly "
                        "from recent baseline."
                    ),
                    severity=Severity.WARNING,
                    confidence=0.70,
                    evidence={
                        "latency_zscore": z,
                        "recent_values":
                            b.p99_latency.values[-5:],
                    },
                )
            )

    return out


# ---------------------------------------------------------------------------
# Cost Signals
# ---------------------------------------------------------------------------

def _cost_signals(
    b: TelemetryBundle,
) -> List[Signal]:

    out: List[Signal] = []

    #
    # High GSI cost
    #
    if (
        _has_data(b.gsi_cost)
        and (b.gsi_cost.avg or 0) > (
            b.monthly_cost * 0.4
        )
    ):
        out.append(
            Signal(
                name="high_gsi_cost_detected",
                description=(
                    "Global secondary indexes contribute "
                    "significantly to overall table cost."
                ),
                severity=Severity.MEDIUM,
                confidence=0.82,
                evidence={
                    "gsi_cost_avg":
                        b.gsi_cost.avg,
                },
            )
        )

    #
    # Backup growth
    #
    if (
        _has_data(b.backup_cost)
        and (b.backup_cost.avg or 0) > (
            b.monthly_cost * 0.3
        )
    ):
        out.append(
            Signal(
                name="backup_cost_growth_detected",
                description=(
                    "Backup storage costs appear unusually high."
                ),
                severity=Severity.WARNING,
                confidence=0.80,
                evidence={
                    "backup_cost_avg":
                        b.backup_cost.avg,
                },
            )
        )

    #
    # On-demand inefficiency
    #
    if (
        b.billing_mode == "PAY_PER_REQUEST"
        and _has_data(b.rcu_utilization)
        and (b.rcu_utilization.avg or 0) > 70
    ):
        out.append(
            Signal(
                name="on_demand_cost_inefficiency",
                description=(
                    "Sustained high throughput may make "
                    "provisioned capacity more economical."
                ),
                severity=Severity.OPTIMIZATION,
                confidence=0.75,
                evidence={
                    "billing_mode":
                        b.billing_mode,
                    "rcu_utilization":
                        b.rcu_utilization.avg,
                },
            )
        )

    return out


# ---------------------------------------------------------------------------
# Reliability + DR Signals
# ---------------------------------------------------------------------------

def _reliability_signals(
    b: TelemetryBundle,
) -> List[Signal]:

    out: List[Signal] = []

    #
    # PITR disabled
    #
    if b.pitr_enabled is False:
        out.append(
            Signal(
                name="pitr_disabled",
                description=(
                    "Point-in-time recovery is disabled."
                ),
                severity=Severity.HIGH,
                confidence=0.98,
                evidence={
                    "pitr_enabled": False,
                },
            )
        )

    #
    # Missing backups
    #
    if b.backup_enabled is False:
        out.append(
            Signal(
                name="backup_configuration_missing",
                description=(
                    "Backup configuration appears missing."
                ),
                severity=Severity.HIGH,
                confidence=0.90,
                evidence={
                    "backup_enabled": False,
                },
            )
        )

    #
    # Replication lag
    #
    if (
        _has_data(b.replication_lag)
        and (b.replication_lag.max or 0) > 60
    ):
        out.append(
            Signal(
                name="replication_lag_detected",
                description=(
                    "Global table replication lag exceeds "
                    "acceptable thresholds."
                ),
                severity=Severity.CRITICAL,
                confidence=0.90,
                evidence={
                    "replication_lag_seconds":
                        b.replication_lag.max,
                },
            )
        )

    return out


# ---------------------------------------------------------------------------
# Data Model Signals
# ---------------------------------------------------------------------------

def _data_model_signals(
    b: TelemetryBundle,
) -> List[Signal]:

    out: List[Signal] = []

    #
    # Hot keys
    #
    if (
        _has_data(b.hot_partition_ratio)
        and (b.hot_partition_ratio.max or 0) > 50
    ):
        out.append(
            Signal(
                name="inefficient_partition_key_detected",
                description=(
                    "Access distribution suggests inefficient "
                    "partition-key design."
                ),
                severity=Severity.HIGH,
                confidence=0.88,
                evidence={
                    "hot_partition_ratio":
                        b.hot_partition_ratio.max,
                    "partition_key":
                        b.partition_key,
                },
            )
        )

    #
    # Sparse GSIs
    #
    sparse_indexes = [
        gsi
        for gsi in (b.gsis or [])
        if gsi.get("sparse")
    ]

    if sparse_indexes:
        out.append(
            Signal(
                name="sparse_indexes_detected",
                description=(
                    "Sparse global secondary indexes detected."
                ),
                severity=Severity.WARNING,
                confidence=0.70,
                evidence={
                    "sparse_indexes":
                        [g.get("name") for g in sparse_indexes],
                },
            )
        )

    return out


# ---------------------------------------------------------------------------
# Operational Correlation Signals
# ---------------------------------------------------------------------------

def _operational_signals(
    b: TelemetryBundle,
) -> List[Signal]:

    out: List[Signal] = []

    if not b.events:
        return out

    deploys = [
        e
        for e in b.events
        if e.get("type") == "deployment"
    ]

    #
    # Deployment-correlated throttling
    #
    if (
        deploys
        and _has_data(b.throttled_requests)
        and (b.throttled_requests.max or 0) > 0
    ):
        out.append(
            Signal(
                name="deployment_correlated_throttling",
                description=(
                    "Recent deployment correlates with "
                    "throttling spike."
                ),
                severity=Severity.WARNING,
                confidence=0.65,
                evidence={
                    "deployment_count":
                        len(deploys),
                    "throttled_requests":
                        b.throttled_requests.max,
                },
            )
        )

    #
    # Deployment-correlated latency
    #
    if (
        deploys
        and _has_data(b.p99_latency)
        and (b.p99_latency.max or 0) > 200
    ):
        out.append(
            Signal(
                name="deployment_correlated_latency_spike",
                description=(
                    "Recent deployment correlates with "
                    "elevated latency."
                ),
                severity=Severity.WARNING,
                confidence=0.65,
                evidence={
                    "deployment_count":
                        len(deploys),
                    "p99_latency":
                        b.p99_latency.max,
                },
            )
        )

    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_signals(
    bundle: TelemetryBundle,
) -> List[Signal]:

    """
    Run all signal extractors.
    """

    signals: List[Signal] = []

    extractors = (
        _capacity_signals,
        _performance_signals,
        _cost_signals,
        _reliability_signals,
        _data_model_signals,
        _operational_signals,
    )

    for fn in extractors:

        try:
            signals.extend(fn(bundle))

        #
        # Never fail full pipeline
        #
        except Exception as e:

            import logging

            logging.getLogger(__name__).warning(
                "signal extractor %s failed: %s",
                fn.__name__,
                e,
            )

    return signals


def signals_by_name(
    signals: List[Signal],
) -> dict:

    """
    Convenience index for rules and agents.
    """

    return {
        signal.name: signal
        for signal in signals
    }