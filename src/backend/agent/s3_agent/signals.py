"""
Signal extraction layer for S3 intelligence analysis.

This is the MOST important layer in the architecture.

The system MUST NOT allow downstream agents or LLM reasoning
to consume raw S3 telemetry directly.

Instead:
    raw telemetry
        →
    normalized telemetry
        →
    intelligence signals
        →
    recommendations

Signals represent meaningful storage observations:
    - storage inefficiencies
    - access anomalies
    - lifecycle gaps
    - durability risks
    - security exposures
    - retrieval anomalies
    - operational risks

Each signal contains:
    - severity
    - confidence
    - evidence
    - reasoning context

Downstream agents consume ONLY signals.
"""

from __future__ import annotations

import statistics
from typing import List, Optional

from agent.s3_agent.types import (
    MetricSeries,
    Severity,
    Signal,
    TelemetryBundle,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_data(series: Optional[MetricSeries]) -> bool:
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

    Detects abnormal deviation of latest datapoint
    against recent historical baseline.
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
        return 0.0 if latest == mu else float("inf")

    z = (latest - mu) / sigma

    return z if abs(z) >= threshold else None


# ---------------------------------------------------------------------------
# Storage Utilization Signals
# ---------------------------------------------------------------------------

def _storage_signals(b: TelemetryBundle) -> List[Signal]:
    out: List[Signal] = []

    #
    # Abnormal storage growth
    #
    if _has_data(b.storage_growth_rate):
        avg = b.storage_growth_rate.avg
        peak = b.storage_growth_rate.max

        if avg is not None and avg > 100 * 1024 * 1024 * 1024:
            out.append(
                Signal(
                    name="bucket_growth_abnormal",
                    description=(
                        "Bucket storage growth is unusually high "
                        "and may indicate runaway retention, "
                        "duplicate uploads, or lifecycle gaps."
                    ),
                    severity=Severity.HIGH,
                    confidence=0.85,
                    evidence={
                        "growth_avg_bytes_per_day": avg,
                        "growth_peak_bytes_per_day": peak,
                    },
                )
            )

    #
    # Excessive small objects
    #
    if _has_data(b.small_object_ratio):
        ratio = b.small_object_ratio.avg or 0

        if ratio > 60:
            out.append(
                Signal(
                    name="excessive_small_objects_detected",
                    description=(
                        "Large percentage of bucket objects are "
                        "very small files, increasing request "
                        "costs and metadata overhead."
                    ),
                    severity=Severity.MEDIUM,
                    confidence=0.9,
                    evidence={
                        "small_object_ratio": ratio,
                    },
                )
            )

    #
    # Stale storage
    #
    if _has_data(b.stale_object_ratio):
        stale = b.stale_object_ratio.avg or 0

        if stale > 40:
            out.append(
                Signal(
                    name="stale_objects_detected",
                    description=(
                        "Large amount of stored data appears "
                        "cold or inactive for extended periods."
                    ),
                    severity=Severity.MEDIUM,
                    confidence=0.85,
                    evidence={
                        "stale_object_ratio": stale,
                    },
                )
            )

    #
    # Storage anomaly
    #
    if _has_data(b.total_storage_bytes):
        z = _zscore_anomaly(b.total_storage_bytes.values)

        if z is not None:
            out.append(
                Signal(
                    name="storage_growth_anomaly",
                    description=(
                        "Latest bucket storage usage deviates "
                        "significantly from historical trend."
                    ),
                    severity=Severity.WARNING,
                    confidence=0.7,
                    evidence={
                        "zscore": z,
                        "recent_values": b.total_storage_bytes.values[-5:],
                    },
                )
            )

    return out


# ---------------------------------------------------------------------------
# Access Pattern Signals
# ---------------------------------------------------------------------------

def _access_pattern_signals(
    b: TelemetryBundle,
) -> List[Signal]:

    out: List[Signal] = []

    #
    # Retrieval spikes
    #
    if _has_data(b.retrieval_rate):
        z = _zscore_anomaly(b.retrieval_rate.values)

        if z is not None:
            out.append(
                Signal(
                    name="retrieval_spike_detected",
                    description=(
                        "Object retrieval activity spiked "
                        "significantly above historical baseline."
                    ),
                    severity=Severity.WARNING,
                    confidence=0.75,
                    evidence={
                        "retrieval_zscore": z,
                    },
                )
            )

    #
    # Request spike
    #
    if _has_data(b.get_requests):
        peak = b.get_requests.max or 0
        avg = b.get_requests.avg or 0

        if avg > 0 and peak > avg * 5:
            out.append(
                Signal(
                    name="burst_access_pattern_detected",
                    description=(
                        "Bucket exhibits bursty access patterns "
                        "with sudden request amplification."
                    ),
                    severity=Severity.MEDIUM,
                    confidence=0.8,
                    evidence={
                        "get_avg": avg,
                        "get_peak": peak,
                    },
                )
            )

    #
    # High transfer cost risk
    #
    if (
        _has_data(b.data_transfer_out)
        and _has_data(b.transfer_cost)
    ):
        transfer = b.transfer_cost.avg or 0

        if transfer > 100:
            out.append(
                Signal(
                    name="transfer_cost_anomaly_detected",
                    description=(
                        "Data transfer costs are unusually high "
                        "relative to normal storage operations."
                    ),
                    severity=Severity.HIGH,
                    confidence=0.8,
                    evidence={
                        "transfer_cost": transfer,
                    },
                )
            )

    return out


# ---------------------------------------------------------------------------
# Cost Optimization Signals
# ---------------------------------------------------------------------------

def _cost_signals(b: TelemetryBundle) -> List[Signal]:
    out: List[Signal] = []

    #
    # Missing lifecycle policy
    #
    if not b.lifecycle_enabled:
        out.append(
            Signal(
                name="missing_lifecycle_policy",
                description=(
                    "Bucket lacks lifecycle configuration "
                    "for archival or cleanup automation."
                ),
                severity=Severity.MEDIUM,
                confidence=0.95,
                evidence={
                    "lifecycle_enabled": False,
                },
            )
        )

    #
    # Glacier opportunity
    #
    if (
        _has_data(b.stale_object_ratio)
        and (b.stale_object_ratio.avg or 0) > 50
    ):
        out.append(
            Signal(
                name="cold_storage_candidate",
                description=(
                    "Large portion of bucket data appears "
                    "eligible for Glacier archival tiers."
                ),
                severity=Severity.OPTIMIZATION,
                confidence=0.85,
                evidence={
                    "stale_ratio": b.stale_object_ratio.avg,
                },
            )
        )

    #
    # Intelligent tiering opportunity
    #
    if (
        _has_data(b.intelligent_tiering_ratio)
        and (b.intelligent_tiering_ratio.avg or 0) < 20
    ):
        out.append(
            Signal(
                name="intelligent_tiering_underutilized",
                description=(
                    "Bucket appears to have limited usage "
                    "of Intelligent Tiering despite mixed "
                    "access patterns."
                ),
                severity=Severity.OPTIMIZATION,
                confidence=0.75,
                evidence={
                    "intelligent_tiering_ratio":
                        b.intelligent_tiering_ratio.avg,
                },
            )
        )

    return out


# ---------------------------------------------------------------------------
# Reliability + Durability Signals
# ---------------------------------------------------------------------------

def _reliability_signals(
    b: TelemetryBundle,
) -> List[Signal]:

    out: List[Signal] = []

    #
    # Missing versioning
    #
    if b.versioning_enabled is False:
        out.append(
            Signal(
                name="versioning_disabled",
                description=(
                    "Bucket versioning is disabled, "
                    "increasing accidental deletion "
                    "and overwrite risk."
                ),
                severity=Severity.HIGH,
                confidence=0.95,
                evidence={
                    "versioning_enabled": False,
                },
            )
        )

    #
    # Replication failures
    #
    if _has_data(b.replication_failures):
        failures = b.replication_failures.max or 0

        if failures > 0:
            out.append(
                Signal(
                    name="replication_failures_detected",
                    description=(
                        "Cross-region or replication operations "
                        "are failing."
                    ),
                    severity=Severity.CRITICAL,
                    confidence=0.95,
                    evidence={
                        "replication_failures": failures,
                    },
                )
            )

    #
    # Replication lag
    #
    if _has_data(b.replication_latency):
        latency = b.replication_latency.max or 0

        if latency > 900:
            out.append(
                Signal(
                    name="high_replication_latency",
                    description=(
                        "Replication latency exceeds acceptable "
                        "durability recovery windows."
                    ),
                    severity=Severity.HIGH,
                    confidence=0.85,
                    evidence={
                        "replication_latency_seconds": latency,
                    },
                )
            )

    #
    # Missing replication
    #
    if b.replication_enabled is False:
        out.append(
            Signal(
                name="cross_region_redundancy_gap",
                description=(
                    "Bucket lacks replication configuration "
                    "for regional durability protection."
                ),
                severity=Severity.MEDIUM,
                confidence=0.75,
                evidence={
                    "replication_enabled": False,
                },
            )
        )

    return out


# ---------------------------------------------------------------------------
# Security Signals
# ---------------------------------------------------------------------------

def _security_signals(b: TelemetryBundle) -> List[Signal]:
    out: List[Signal] = []

    #
    # Public exposure
    #
    if b.public_access_enabled:
        out.append(
            Signal(
                name="public_access_risk_detected",
                description=(
                    "Bucket allows public access and may expose "
                    "sensitive data."
                ),
                severity=Severity.CRITICAL,
                confidence=0.98,
                evidence={
                    "public_access_enabled": True,
                },
            )
        )

    #
    # Missing encryption
    #
    if b.encryption_enabled is False:
        out.append(
            Signal(
                name="unencrypted_storage_detected",
                description=(
                    "Bucket encryption at rest is disabled."
                ),
                severity=Severity.HIGH,
                confidence=0.98,
                evidence={
                    "encryption_enabled": False,
                },
            )
        )

    #
    # Missing KMS
    #
    if (
        b.encryption_enabled
        and b.kms_enabled is False
    ):
        out.append(
            Signal(
                name="kms_not_enabled",
                description=(
                    "Bucket encryption does not use KMS-managed keys."
                ),
                severity=Severity.WARNING,
                confidence=0.8,
                evidence={
                    "kms_enabled": False,
                },
            )
        )

    #
    # Missing access logging
    #
    if b.access_logging_enabled is False:
        out.append(
            Signal(
                name="audit_logging_disabled",
                description=(
                    "Bucket access logging is disabled, "
                    "reducing audit visibility."
                ),
                severity=Severity.MEDIUM,
                confidence=0.9,
                evidence={
                    "access_logging_enabled": False,
                },
            )
        )

    return out


# ---------------------------------------------------------------------------
# Operational Signals
# ---------------------------------------------------------------------------

def _operational_signals(
    b: TelemetryBundle,
) -> List[Signal]:

    out: List[Signal] = []

    #
    # Lifecycle failures
    #
    if _has_data(b.lifecycle_transition_failures):
        failures = b.lifecycle_transition_failures.max or 0

        if failures > 0:
            out.append(
                Signal(
                    name="lifecycle_transition_failures",
                    description=(
                        "Lifecycle transitions are failing "
                        "for some bucket objects."
                    ),
                    severity=Severity.WARNING,
                    confidence=0.85,
                    evidence={
                        "transition_failures": failures,
                    },
                )
            )

    #
    # Object lock missing for critical buckets
    #
    env = (b.tags or {}).get("Environment", "").lower()

    if env == "prod" and not b.object_lock_enabled:
        out.append(
            Signal(
                name="object_lock_not_enabled",
                description=(
                    "Production bucket lacks object lock "
                    "protection against accidental or "
                    "malicious deletion."
                ),
                severity=Severity.MEDIUM,
                confidence=0.8,
                evidence={
                    "environment": env,
                    "object_lock_enabled": False,
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
    Run all signal extraction domains.
    """

    signals: List[Signal] = []

    extractors = (
        _storage_signals,
        _access_pattern_signals,
        _cost_signals,
        _reliability_signals,
        _security_signals,
        _operational_signals,
    )

    for fn in extractors:
        try:
            signals.extend(fn(bundle))
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(
                "signal extractor %s failed: %s",
                fn.__name__,
                e,
            )

    return signals


def signals_by_name(signals: List[Signal]) -> dict:
    """
    Convenience index for rule lookups.
    """

    return {
        signal.name: signal
        for signal in signals
    }