"""
Simulation service — log-aware optimization simulation for right-sizing and auto-scaling.

Derives system characteristics from resource metrics/recommendations (proxy for logs)
and simulates the impact of slider-driven optimization on latency, error rates,
retry amplification, and cost.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from services.cost_engine import (
    _safe_float,
    _get_cpu_avg,
    _get_monthly_cost,
    _is_compute,
    _resource_type,
)


# ---------------------------------------------------------------------------
# System characteristic inference (derived from metrics, acts as log proxy)
# ---------------------------------------------------------------------------

def infer_system_characteristics(resources: List[Dict]) -> Dict[str, Any]:
    """
    Infer system-level behavioral characteristics from resource metrics
    and recommendations. These serve as a proxy for log-derived signals.
    """
    compute = [r for r in resources if _is_compute(r)]
    if not compute:
        return _default_characteristics()

    cpu_avgs = [_get_cpu_avg(r) for r in compute]
    costs = [_get_monthly_cost(r) for r in compute]
    total_cost = sum(costs)

    # Latency sensitivity: high CPU avg → latency-sensitive workload
    avg_cpu = sum(cpu_avgs) / len(cpu_avgs) if cpu_avgs else 0
    latency_sensitivity = min(1.0, avg_cpu / 60.0)

    # Retry behavior: inferred from network metrics variability
    retry_factor = 0.0
    for r in compute:
        metrics = r.get("metrics") or {}
        net_in = metrics.get("network_in") or {}
        net_out = metrics.get("network_out") or {}
        if isinstance(net_in, dict) and isinstance(net_out, dict):
            avg_in = _safe_float(net_in.get("avg", 0))
            max_in = _safe_float(net_in.get("max", 0))
            if avg_in > 0 and max_in > avg_in * 3:
                retry_factor += 0.3
    retry_factor = min(1.0, retry_factor)

    # System fragility: resources with many recommendations = fragile
    total_recs = sum(len(r.get("recommendations") or []) for r in compute)
    fragility = min(1.0, total_recs / max(len(compute) * 3, 1))

    # Critical components: high-cost resources are critical
    cost_threshold = total_cost * 0.4 if total_cost > 0 else float("inf")
    critical_count = sum(1 for c in costs if c >= cost_threshold)

    return {
        "latency_sensitivity": round(latency_sensitivity, 2),
        "retry_behavior": round(retry_factor, 2),
        "fragility": round(fragility, 2),
        "critical_component_count": critical_count,
        "total_compute_resources": len(compute),
        "avg_cpu_utilization": round(avg_cpu, 1),
    }


def _default_characteristics() -> Dict[str, Any]:
    return {
        "latency_sensitivity": 0.5,
        "retry_behavior": 0.2,
        "fragility": 0.3,
        "critical_component_count": 0,
        "total_compute_resources": 0,
        "avg_cpu_utilization": 0,
    }


# ---------------------------------------------------------------------------
# Risk zone classification
# ---------------------------------------------------------------------------

def classify_risk_zone(slider_value: float, max_value: float, chars: Dict) -> str:
    """Classify slider position as safe / moderate / risky."""
    normalized = slider_value / max_value if max_value > 0 else 0

    # Fragile or latency-sensitive systems have tighter safe zones
    sensitivity_penalty = (chars["latency_sensitivity"] + chars["fragility"]) / 2
    safe_ceiling = 0.5 - sensitivity_penalty * 0.2
    risky_floor = 0.75 - sensitivity_penalty * 0.15

    if normalized <= safe_ceiling:
        return "safe"
    elif normalized <= risky_floor:
        return "moderate"
    else:
        return "risky"


# ---------------------------------------------------------------------------
# Right-Sizing Simulation
# ---------------------------------------------------------------------------

def simulate_rightsizing(
    resources: List[Dict],
    optimization_level: int,
    chars: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Simulate the impact of right-sizing at the given optimization level.
    Returns executive and developer views.
    """
    level_frac = optimization_level / 100.0
    compute = [r for r in resources if _is_compute(r)]
    total_cost = sum(_get_monthly_cost(r) for r in compute)

    # Capacity reduction mapped from slider
    capacity_reduction_pct = level_frac * 40  # 0-40% capacity reduction

    # Cost savings (damped by critical component protection)
    critical_damping = 1.0 - (chars["critical_component_count"] / max(len(compute), 1)) * 0.3
    raw_savings = total_cost * (capacity_reduction_pct / 100) * 0.7
    cost_savings = round(raw_savings * critical_damping, 2)

    # Latency impact: nonlinear — aggressive levels hit latency hard
    latency_base_ms = 2 + chars["latency_sensitivity"] * 15
    latency_increase_pct = round(
        (level_frac ** 1.8) * 40 * (1 + chars["latency_sensitivity"]), 1
    )
    latency_increase_ms = round(latency_base_ms * (latency_increase_pct / 100), 1)

    # Error rate: exponential increase at high levels
    error_rate_increase = round(
        (level_frac ** 2.5) * 3.0 * (1 + chars["fragility"]), 2
    )

    # Retry amplification
    retry_amplification = round(
        1.0 + (level_frac ** 2) * chars["retry_behavior"] * 2.5, 2
    )

    # Infra changes
    affected_replicas = max(0, round(len(compute) * level_frac * 0.6))

    risk_zone = classify_risk_zone(optimization_level, 100, chars)

    # Safe operating zone recommendation
    safe_max = round((0.5 - (chars["latency_sensitivity"] + chars["fragility"]) * 0.15) * 100)
    safe_max = max(20, min(70, safe_max))

    return {
        "risk_zone": risk_zone,
        "safe_operating_range": {"min": 0, "max": safe_max},
        "capacity_reduction_pct": round(capacity_reduction_pct, 1),
        "executive": {
            "cost_savings_monthly": cost_savings,
            "risk_level": risk_zone,
            "recommendation": _rightsizing_recommendation(risk_zone, cost_savings, safe_max),
        },
        "developer": {
            "latency_increase_pct": latency_increase_pct,
            "latency_increase_ms": latency_increase_ms,
            "error_rate_increase_pct": error_rate_increase,
            "retry_amplification_factor": retry_amplification,
            "replicas_affected": affected_replicas,
            "capacity_reduction_pct": round(capacity_reduction_pct, 1),
            "debugging_complexity": _debugging_complexity(level_frac, chars),
        },
    }


def _rightsizing_recommendation(zone: str, savings: float, safe_max: int) -> str:
    if zone == "safe":
        return f"Safe to apply. Projected savings: ${savings}/mo with minimal risk."
    elif zone == "moderate":
        return f"Moderate risk. Consider staying below {safe_max}% for production workloads."
    else:
        return f"High risk — latency and error rates will increase significantly. Not recommended for production."


def _debugging_complexity(level_frac: float, chars: Dict) -> str:
    score = level_frac * 2 + chars["fragility"]
    if score < 0.8:
        return "low"
    elif score < 1.5:
        return "medium"
    else:
        return "high"


# ---------------------------------------------------------------------------
# Auto-Scaling Simulation
# ---------------------------------------------------------------------------

def simulate_autoscaling(
    resources: List[Dict],
    sensitivity: int,
    chars: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Simulate auto-scaling behavior at the given sensitivity level (0-10).
    """
    sens_frac = sensitivity / 10.0
    compute = [r for r in resources if _is_compute(r)]
    total_cost = sum(_get_monthly_cost(r) for r in compute)

    # Scaling frequency: higher sensitivity = more frequent scaling
    base_events_per_day = 2
    scaling_events_per_day = round(base_events_per_day + sens_frac * 12, 1)

    # Cost impact: sweet spot in the middle
    # Low sensitivity → over-provisioned (cost waste)
    # High sensitivity → under-provisioned during spikes (retries + latency)
    # Normalize sensitivity (expected input: 0–10)
    sens_frac = sensitivity / 10.0

    # Clamp to [0, 1] to avoid invalid math
    sens_frac = max(0.0, min(1.0, sens_frac))

    # Safe base (prevents negative fractional powers)
    base = max(0.0, 1 - sens_frac)

    # Calculations
    over_scaling_waste = round(total_cost * 0.12 * (base ** 1.5), 2)
    under_scaling_cost = round(total_cost * 0.05 * (sens_frac ** 2), 2)

    # Net savings (ensure it's realistic)
    gross_savings = total_cost * 0.15 * sens_frac
    net_savings = round(gross_savings - under_scaling_cost, 2)
    # Responsiveness vs stability tradeoff
    response_time_sec = round(300 - sens_frac * 180)  # 300s → 120s
    stability_score = round(10 - sens_frac * 6, 1)     # 10 → 4

    # Latency during under-scaling events
    spike_latency_increase_pct = round(
        (sens_frac ** 2) * 25 * (1 + chars["latency_sensitivity"]), 1
    )

    # Retry amplification during scale-up lag
    retry_during_scaling = round(
        1.0 + (sens_frac ** 1.5) * chars["retry_behavior"] * 1.8, 2
    )

    risk_zone = classify_risk_zone(sensitivity, 10, chars)

    # Safe zone
    safe_max = round((0.6 - chars["fragility"] * 0.15) * 10)
    safe_max = max(3, min(8, safe_max))

    return {
        "risk_zone": risk_zone,
        "safe_operating_range": {"min": 0, "max": safe_max},
        "executive": {
            "cost_savings_monthly": max(0, net_savings),
            "over_provisioning_waste": over_scaling_waste,
            "risk_level": risk_zone,
            "recommendation": _autoscaling_recommendation(risk_zone, net_savings, safe_max),
        },
        "developer": {
            "scaling_events_per_day": scaling_events_per_day,
            "response_time_sec": response_time_sec,
            "stability_score": stability_score,
            "spike_latency_increase_pct": spike_latency_increase_pct,
            "retry_during_scaling_factor": retry_during_scaling,
            "over_scaling_waste_monthly": over_scaling_waste,
            "under_scaling_risk_monthly": under_scaling_cost,
            "debugging_complexity": _scaling_debug_complexity(sens_frac, chars),
        },
    }


def _autoscaling_recommendation(zone: str, savings: float, safe_max: int) -> str:
    if zone == "safe":
        return f"Stable configuration. Net savings: ${max(0, savings)}/mo with reliable scaling."
    elif zone == "moderate":
        return f"Balanced — monitor for spike events. Consider staying at or below {safe_max} for critical systems."
    else:
        return f"Aggressive — frequent scaling may cause latency spikes during load transitions."


def _scaling_debug_complexity(sens_frac: float, chars: Dict) -> str:
    score = sens_frac * 2.5 + chars["retry_behavior"] * 1.5
    if score < 1.0:
        return "low"
    elif score < 2.0:
        return "medium"
    else:
        return "high"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_simulation(
    resources: List[Dict],
    right_sizing_level: int = 70,
    auto_scaling_sensitivity: int = 5,
) -> Dict[str, Any]:
    """Run full simulation for both sections. Called by the route."""
    chars = infer_system_characteristics(resources)

    rightsizing_sim = simulate_rightsizing(resources, right_sizing_level, chars)
    autoscaling_sim = simulate_autoscaling(resources, auto_scaling_sensitivity, chars)

    return {
        "system_characteristics": chars,
        "right_sizing": rightsizing_sim,
        "auto_scaling": autoscaling_sim,
    }
