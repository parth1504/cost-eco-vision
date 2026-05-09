"""
Signal extraction (Feature Extraction Layer + lightweight Anomaly Detection).

This is the load-bearing intelligence layer the spec called out:
  "The LLM MUST NOT consume raw telemetry dumps directly. A dedicated
   intermediate intelligence layer must transform raw telemetry into
   structured findings and signals."

Each signal is a discrete, named observation about the instance, with:
  - confidence (how sure are we?)
  - evidence (the raw numbers that support it)
  - severity (a hint, not a final verdict)

Downstream rule engine + sub-agents consume the SIGNALS, never the
raw bundle. This is what stops the LLM from hallucinating because it
saw `cpu_avg=18.7%` and pattern-matched "low CPU".

Anomaly detection is lightweight by design — rolling z-score + simple
deviation checks. We avoid sklearn / Prophet here for hackathon scope;
the architecture supports plugging them in (see `_zscore_anomaly`).
"""

from __future__ import annotations

import statistics
from typing import List, Optional

from agent.ec2_agent.types import MetricSeries, Severity, Signal, TelemetryBundle


# ---------------------------------------------------------------------------
# Anomaly primitives
# ---------------------------------------------------------------------------

def _zscore_anomaly(values: List[float], threshold: float = 2.5) -> Optional[float]:
    """
    Rolling z-score deviation. Returns the z-score of the latest value
    against the rest of the series, or None if not enough data.
    """
    if not values or len(values) < 4:
        return None
    history = values[:-1]
    latest = values[-1]
    mu = statistics.mean(history)
    sigma = statistics.pstdev(history) if len(history) > 1 else 0.0
    if sigma == 0:
        return 0.0 if latest == mu else float("inf")
    z = (latest - mu) / sigma
    return z if abs(z) >= threshold else None


def _has_data(s: Optional[MetricSeries]) -> bool:
    return s is not None and len(s.points) > 0 and s.avg is not None


# ---------------------------------------------------------------------------
# Per-domain extractors
# ---------------------------------------------------------------------------

def _cpu_signals(b: TelemetryBundle) -> List[Signal]:
    out: List[Signal] = []
    if not _has_data(b.cpu):
        return out
    avg, mx = b.cpu.avg, b.cpu.max

    # Sustained high
    if avg is not None and avg > 80:
        out.append(Signal(
            name="cpu_sustained_high",
            description=f"CPU average {avg:.1f}% over the observed window — sustained saturation.",
            severity=Severity.HIGH,
            confidence=min(1.0, 0.7 + (avg - 80) / 40),
            evidence={"cpu_avg": avg, "cpu_max": mx, "window": "7d"},
        ))
    # Sustained low (idle)
    if avg is not None and avg < 5 and (mx is None or mx < 15):
        out.append(Signal(
            name="cpu_sustained_low",
            description=f"CPU consistently below 5% (avg {avg:.2f}%, peak {mx or 0:.2f}%) — idle.",
            severity=Severity.MEDIUM,
            confidence=0.9,
            evidence={"cpu_avg": avg, "cpu_max": mx, "window": "7d"},
        ))
    # Bursty
    if avg is not None and mx is not None and avg < 20 and mx > 70:
        out.append(Signal(
            name="cpu_bursty",
            description=f"Low average ({avg:.1f}%) with high peaks ({mx:.1f}%) — bursty workload pattern.",
            severity=Severity.MEDIUM,
            confidence=0.8,
            evidence={"cpu_avg": avg, "cpu_max": mx, "spread": mx - avg},
        ))
    # Statistical anomaly
    z = _zscore_anomaly(b.cpu.values)
    if z is not None:
        out.append(Signal(
            name="cpu_anomaly",
            description=f"Latest CPU value deviates by {z:.1f}σ from recent baseline.",
            severity=Severity.WARNING,
            confidence=0.6,
            evidence={"zscore": z, "values": b.cpu.values[-5:]},
        ))
    return out


def _memory_signals(b: TelemetryBundle) -> List[Signal]:
    out: List[Signal] = []
    if _has_data(b.memory):
        avg = b.memory.avg
        if avg is not None and avg > 85:
            out.append(Signal(
                name="memory_pressure_detected",
                description=f"Memory utilization average {avg:.1f}% — sustained pressure.",
                severity=Severity.HIGH,
                confidence=0.85,
                evidence={"memory_avg": avg, "memory_max": b.memory.max},
            ))
    if _has_data(b.swap):
        if (b.swap.avg or 0) > 5:
            out.append(Signal(
                name="swap_exhaustion",
                description=f"Swap usage average {b.swap.avg:.1f}% — system memory exhausted.",
                severity=Severity.HIGH,
                confidence=0.9,
                evidence={"swap_avg": b.swap.avg},
            ))
    # OOM kills from log signals
    oom = b.log_signals.get("oom_kills", 0)
    if oom > 0:
        out.append(Signal(
            name="oom_killed",
            description=f"{oom} OOM-kill events detected in recent logs.",
            severity=Severity.CRITICAL,
            confidence=0.95,
            evidence={"oom_kill_count": oom},
        ))
    return out


def _disk_ebs_signals(b: TelemetryBundle) -> List[Signal]:
    out: List[Signal] = []
    if _has_data(b.disk_used_pct) and (b.disk_used_pct.max or 0) > 90:
        out.append(Signal(
            name="disk_full_risk",
            description=f"Disk usage peaked at {b.disk_used_pct.max:.1f}% — at risk of filling.",
            severity=Severity.HIGH,
            confidence=0.9,
            evidence={"disk_max": b.disk_used_pct.max},
        ))
    if _has_data(b.ebs_burst_balance):
        # min represents the trough we're worried about
        burst_min = b.ebs_burst_balance.min
        if burst_min is not None and burst_min < 30:
            out.append(Signal(
                name="ebs_burst_balance_low",
                description=f"EBS burst balance dipped to {burst_min:.0f}% — IO performance throttling likely.",
                severity=Severity.MEDIUM,
                confidence=0.85,
                evidence={"ebs_burst_min": burst_min},
            ))
    return out


def _network_signals(b: TelemetryBundle) -> List[Signal]:
    out: List[Signal] = []
    if _has_data(b.network_in) and _has_data(b.network_out):
        peak = max(b.network_in.max or 0, b.network_out.max or 0)
        # 100 MB/s as a coarse threshold for "saturating a small instance"
        if peak > 100 * 1024 * 1024:
            out.append(Signal(
                name="network_saturation_detected",
                description=f"Network peak {peak/1024/1024:.0f} MB/s suggests saturation on smaller instance types.",
                severity=Severity.WARNING,
                confidence=0.7,
                evidence={"net_peak_bytes": peak},
            ))
    if _has_data(b.packet_drops) and (b.packet_drops.max or 0) > 0:
        out.append(Signal(
            name="packet_drops_observed",
            description=f"Up to {b.packet_drops.max:.0f} packet drops detected — possible instance bandwidth or driver issue.",
            severity=Severity.MEDIUM,
            confidence=0.8,
            evidence={"packet_drops_max": b.packet_drops.max},
        ))
    return out


def _reliability_signals(b: TelemetryBundle) -> List[Signal]:
    out: List[Signal] = []
    if _has_data(b.status_check_failed) and (b.status_check_failed.max or 0) > 0:
        out.append(Signal(
            name="status_check_failures",
            description="EC2 status check failed at least once in the recent window.",
            severity=Severity.CRITICAL,
            confidence=0.95,
            evidence={"status_check_max": b.status_check_failed.max},
        ))
    if b.reboot_count_7d >= 3:
        out.append(Signal(
            name="reboot_loop_detected",
            description=f"{b.reboot_count_7d} reboots in the last 7 days — likely instability or reboot loop.",
            severity=Severity.CRITICAL,
            confidence=0.9,
            evidence={"reboot_count_7d": b.reboot_count_7d},
        ))
    if b.autoscaling_attached is False:
        out.append(Signal(
            name="no_autoscaling",
            description="Instance is standalone (no Auto Scaling Group) — single point of failure.",
            severity=Severity.MEDIUM,
            confidence=0.85,
            evidence={"asg_attached": False},
        ))
    if b.autoscaling_az_count is not None and b.autoscaling_az_count < 2 and b.autoscaling_attached:
        out.append(Signal(
            name="single_az_deployment",
            description=f"ASG spans only {b.autoscaling_az_count} AZ — AZ failure causes full outage.",
            severity=Severity.HIGH,
            confidence=0.9,
            evidence={"az_count": b.autoscaling_az_count},
        ))
    return out


def _security_signals(b: TelemetryBundle) -> List[Signal]:
    out: List[Signal] = []
    if b.imdsv2_required is False:
        out.append(Signal(
            name="imdsv1_in_use",
            description="Instance metadata service v1 still allowed — vulnerable to SSRF-based credential theft.",
            severity=Severity.HIGH,
            confidence=0.95,
            evidence={"imdsv2_required": False},
        ))
    if b.ebs_encrypted is False:
        out.append(Signal(
            name="ebs_unencrypted",
            description="Attached EBS volumes are not encrypted at rest.",
            severity=Severity.HIGH,
            confidence=0.95,
            evidence={"ebs_encrypted": False},
        ))
    if 22 in b.open_ports_world or 3389 in b.open_ports_world:
        out.append(Signal(
            name="ssh_rdp_open_to_world",
            description=f"Admin port(s) {b.open_ports_world} open to 0.0.0.0/0.",
            severity=Severity.CRITICAL,
            confidence=0.95,
            evidence={"open_ports": b.open_ports_world},
        ))
    if b.ami_age_days is not None and b.ami_age_days > 365:
        out.append(Signal(
            name="ami_outdated",
            description=f"AMI is {b.ami_age_days} days old — likely missing kernel/security patches.",
            severity=Severity.MEDIUM,
            confidence=0.8,
            evidence={"ami_age_days": b.ami_age_days},
        ))
    return out


def _cost_signals(b: TelemetryBundle) -> List[Signal]:
    out: List[Signal] = []
    # idle + cost > 0 is a strong waste signal
    if (
        _has_data(b.cpu)
        and b.cpu.avg is not None
        and b.cpu.avg < 5
        and b.monthly_cost > 0
    ):
        out.append(Signal(
            name="instance_idle_high_cost",
            description=f"Idle (CPU {b.cpu.avg:.1f}%) but costing ${b.monthly_cost:.2f}/mo.",
            severity=Severity.MEDIUM,
            confidence=0.9,
            evidence={"cpu_avg": b.cpu.avg, "monthly_cost": b.monthly_cost},
        ))
    # graviton hint: x86 family without intel-specific deps
    if b.instance_type and not b.instance_type.startswith(("t4g", "m6g", "c6g", "r6g", "m7g", "c7g")):
        if b.monthly_cost > 50:
            out.append(Signal(
                name="graviton_migration_candidate",
                description=f"Running on x86 ({b.instance_type}) costing ${b.monthly_cost:.2f}/mo — Graviton typically saves ~20%.",
                severity=Severity.LOW,
                confidence=0.5,  # low confidence: we don't know workload arch-compatibility
                evidence={"instance_type": b.instance_type, "monthly_cost": b.monthly_cost},
            ))
    # spot opportunity: dev/staging tagged + on-demand
    env = b.tags.get("Environment", "").lower()
    if env in ("dev", "staging", "test") and not b.is_spot:
        out.append(Signal(
            name="spot_candidate",
            description=f"Non-prod ({env}) instance running on-demand — spot savings up to 70%.",
            severity=Severity.LOW,
            confidence=0.7,
            evidence={"env": env, "is_spot": False, "monthly_cost": b.monthly_cost},
        ))
    return out


def _operational_signals(b: TelemetryBundle) -> List[Signal]:
    """Deployment-correlated signals. Rough timeline matching."""
    out: List[Signal] = []
    if not b.events or not _has_data(b.cpu):
        return out
    # crude: any deployment event in the last 48h + cpu_anomaly within 30min after
    # Real implementation would do windowed correlation; this gives the LLM
    # a coarse "deployment_correlated" hint to investigate.
    deploys = [e for e in b.events if e.get("type") == "deployment"]
    if deploys and (b.cpu.max or 0) > 80:
        out.append(Signal(
            name="deployment_correlated_latency_spike",
            description="Recent deployment correlates with sustained high CPU — possible regression.",
            severity=Severity.HIGH,
            confidence=0.6,
            evidence={"deployment_count": len(deploys), "cpu_max": b.cpu.max},
        ))
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_signals(bundle: TelemetryBundle) -> List[Signal]:
    """Run every per-domain extractor and concatenate signals."""
    signals: List[Signal] = []
    for fn in (
        _cpu_signals,
        _memory_signals,
        _disk_ebs_signals,
        _network_signals,
        _reliability_signals,
        _security_signals,
        _cost_signals,
        _operational_signals,
    ):
        try:
            signals.extend(fn(bundle))
        except Exception as e:  # pragma: no cover — defensive, never crash the pipeline
            import logging
            logging.getLogger(__name__).warning("signal extractor %s failed: %s", fn.__name__, e)
    return signals


def signals_by_name(signals: List[Signal]) -> dict:
    """Convenience index for rules that look up signals by canonical name."""
    return {s.name: s for s in signals}
