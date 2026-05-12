"""
Cost Optimization Engine
========================
Deterministic, explainable optimization intelligence layer.

Consumes resource objects + analyzer-agent recommendations from the
Recommendations table and computes:
  - idle resource detection
  - right-sizing recommendations (slider-driven)
  - smart scheduling opportunities
  - auto-scaling optimization
  - storage optimization
  - monthly bill prediction
  - optimization score (0-100)
  - CO2 reduction estimation
  - implementation plan (immediate / short-term / long-term)

No ML, no external services. All calculations are confidence-weighted
and derived from existing resource metrics + recommendations.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Dict, List, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# CO2 per dollar of compute (kg CO2 per $1/month of cloud spend)
# Based on rough AWS carbon footprint data: ~0.0004 metric tons CO2 per $1
# = 0.4 kg per $1/month, annualized
CO2_KG_PER_DOLLAR_MONTH_ANNUALIZED = 0.4

# Utilization thresholds
IDLE_CPU_THRESHOLD = 5.0          # % — below this = idle
IDLE_NETWORK_THRESHOLD = 1000.0   # bytes/sec avg
UNDERUTIL_CPU_THRESHOLD = 20.0    # % — below this = underutilized
MODERATE_UTIL_CPU_THRESHOLD = 40.0  # % — below this at aggressive levels

# Right-sizing savings tiers (% of resource cost saved)
RIGHTSIZING_SAVINGS_RATE_CONSERVATIVE = 0.20   # 20% savings for clear downsizing
RIGHTSIZING_SAVINGS_RATE_MODERATE = 0.30       # 30% at moderate aggression
RIGHTSIZING_SAVINGS_RATE_AGGRESSIVE = 0.40     # 40% at full aggression

# Scheduling savings — fraction of monthly cost saved by off-hours shutdown
SCHEDULING_SAVINGS_FRACTION = 0.42  # ~10 hrs off per weekday + weekends

# Auto-scaling waste reduction rates by sensitivity
AUTOSCALING_BASE_WASTE_FRACTION = 0.15  # baseline over-provisioning waste

# Storage optimization
STORAGE_GLACIER_SAVINGS_RATE = 0.60     # Glacier is ~60% cheaper than S3 Standard
STORAGE_LIFECYCLE_SAVINGS_RATE = 0.25   # lifecycle transitions save ~25%


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _get_cpu_avg(resource: Dict[str, Any]) -> float:
    metrics = resource.get("metrics") or {}
    # Try nested cpu dict first (EC2 shape), then flat
    cpu = metrics.get("cpu") or {}
    if isinstance(cpu, dict):
        return _safe_float(cpu.get("avg"))
    return _safe_float(metrics.get("cpu_avg", 0))


def _get_network_avg(resource: Dict[str, Any]) -> float:
    metrics = resource.get("metrics") or {}
    net_in = metrics.get("network_in") or {}
    net_out = metrics.get("network_out") or {}
    avg_in = _safe_float(net_in.get("avg") if isinstance(net_in, dict) else 0)
    avg_out = _safe_float(net_out.get("avg") if isinstance(net_out, dict) else 0)
    return avg_in + avg_out


def _get_monthly_cost(resource: Dict[str, Any]) -> float:
    return _safe_float(resource.get("monthly_cost", 0))


def _resource_type(resource: Dict[str, Any]) -> str:
    return (resource.get("resource_type") or resource.get("type") or "").upper()


def _is_compute(resource: Dict[str, Any]) -> bool:
    return _resource_type(resource) in ("EC2", "LAMBDA", "ECS")


def _is_storage(resource: Dict[str, Any]) -> bool:
    return _resource_type(resource) in ("S3", "EBS", "EFS")


def _is_database(resource: Dict[str, Any]) -> bool:
    return _resource_type(resource) in ("DYNAMODB", "RDS")


def _recommendation_savings(resource: Dict[str, Any]) -> float:
    """Sum all numeric savings from a resource's recommendations."""
    total = 0.0
    for rec in (resource.get("recommendations") or []):
        s = rec.get("saving", 0)
        if s and s != "N/A":
            total += _safe_float(s)
    return total


def _cost_type_recommendations(resource: Dict[str, Any]) -> List[Dict]:
    """Return only cost-type recommendations."""
    return [
        r for r in (resource.get("recommendations") or [])
        if (r.get("type") or "").lower() == "cost"
    ]


def _avg_confidence(resources: List[Dict], default: float = 0.85) -> float:
    """Average confidence across cost recommendations. Falls back to default."""
    confs = []
    for r in resources:
        for rec in _cost_type_recommendations(r):
            c = rec.get("confidence")
            if c is not None:
                confs.append(_safe_float(c))
    return sum(confs) / len(confs) if confs else default


# ---------------------------------------------------------------------------
# 1. Idle Resource Detection
# ---------------------------------------------------------------------------

def analyze_idle_resources(resources: List[Dict]) -> Dict[str, Any]:
    idle = []
    total_savings = 0.0

    for r in resources:
        if not _is_compute(r):
            continue
        cpu = _get_cpu_avg(r)
        net = _get_network_avg(r)
        cost = _get_monthly_cost(r)
        status = (r.get("status") or "").lower()

        if status in ("stopped", "terminated"):
            continue

        if cpu < IDLE_CPU_THRESHOLD and net < IDLE_NETWORK_THRESHOLD:
            idle.append({
                "resource_id": r.get("resource_id"),
                "name": r.get("name"),
                "type": _resource_type(r),
                "cpu_avg": round(cpu, 2),
                "network_avg": round(net, 2),
                "monthly_cost": round(cost, 2),
                "action": "stop_or_terminate",
            })
            total_savings += cost

    confidence = 0.91 if idle else 0.5

    return {
        "enabled": True,
        "estimated_savings": round(total_savings, 2),
        "affected_resources": len(idle),
        "resources": idle,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# 2. Right-Sizing (slider-driven)
# ---------------------------------------------------------------------------

def analyze_rightsizing(
    resources: List[Dict],
    optimization_level: int = 70,
) -> Dict[str, Any]:
    """
    optimization_level: 0 (conservative) → 100 (aggressive)
    Higher levels lower the CPU threshold to catch more resources.
    """
    level_frac = optimization_level / 100.0

    # Dynamic threshold: conservative=10%, aggressive=45%
    cpu_threshold = UNDERUTIL_CPU_THRESHOLD + level_frac * (MODERATE_UTIL_CPU_THRESHOLD - UNDERUTIL_CPU_THRESHOLD)

    # Dynamic savings rate
    savings_rate = RIGHTSIZING_SAVINGS_RATE_CONSERVATIVE + level_frac * (
        RIGHTSIZING_SAVINGS_RATE_AGGRESSIVE - RIGHTSIZING_SAVINGS_RATE_CONSERVATIVE
    )

    candidates = []
    total_savings = 0.0

    for r in resources:
        if not _is_compute(r):
            continue
        cpu = _get_cpu_avg(r)
        cost = _get_monthly_cost(r)
        status = (r.get("status") or "").lower()
        if status in ("stopped", "terminated"):
            continue

        if cpu < cpu_threshold and cost > 0:
            projected = round(cost * savings_rate, 2)
            # Use analyzer recommendation savings if available
            rec_savings = _recommendation_savings(r)
            actual_savings = max(projected, rec_savings)

            candidates.append({
                "resource_id": r.get("resource_id"),
                "name": r.get("name"),
                "type": _resource_type(r),
                "cpu_avg": round(cpu, 2),
                "current_cost": round(cost, 2),
                "projected_savings": round(actual_savings, 2),
            })
            total_savings += actual_savings

    return {
        "optimization_level": optimization_level,
        "cpu_threshold_used": round(cpu_threshold, 1),
        "estimated_savings": round(total_savings, 2),
        "candidates": len(candidates),
        "resources": candidates,
        "confidence": _avg_confidence(resources, 0.85),
    }


# ---------------------------------------------------------------------------
# 3. Smart Scheduling
# ---------------------------------------------------------------------------

def analyze_scheduling(resources: List[Dict]) -> Dict[str, Any]:
    """
    Detect compute resources that can be stopped during off-hours.
    Uses tags (Environment=dev/test/staging) and low off-hours patterns.
    """
    schedulable = []
    total_savings = 0.0

    dev_keywords = {"dev", "test", "staging", "sandbox", "qa", "demo"}

    for r in resources:
        if not _is_compute(r):
            continue
        cost = _get_monthly_cost(r)
        status = (r.get("status") or "").lower()
        if status in ("stopped", "terminated") or cost == 0:
            continue

        tags = r.get("tags") or {}
        name = (r.get("name") or "").lower()
        env_tag = (tags.get("Environment") or tags.get("environment") or "").lower()

        is_dev = (
            env_tag in dev_keywords
            or any(kw in name for kw in dev_keywords)
        )

        if is_dev:
            savings = round(cost * SCHEDULING_SAVINGS_FRACTION, 2)
            schedulable.append({
                "resource_id": r.get("resource_id"),
                "name": r.get("name"),
                "type": _resource_type(r),
                "monthly_cost": round(cost, 2),
                "projected_savings": savings,
                "suggested_schedule": "Stop 6 PM - 8 AM weekdays + weekends",
                "reason": f"Tagged/named as {env_tag or 'dev/test'}",
            })
            total_savings += savings

    return {
        "enabled": True,
        "estimated_savings": round(total_savings, 2),
        "schedulable_resources": len(schedulable),
        "resources": schedulable,
        "confidence": 0.88 if schedulable else 0.5,
    }


# ---------------------------------------------------------------------------
# 4. Auto-Scaling Optimization
# ---------------------------------------------------------------------------

def analyze_autoscaling(
    resources: List[Dict],
    sensitivity: int = 50,
) -> Dict[str, Any]:
    """
    sensitivity: 0 (conservative) → 100 (aggressive)
    Higher sensitivity = tighter scaling thresholds = less waste.
    """
    sens_frac = sensitivity / 100.0 if sensitivity <= 100 else sensitivity / 10.0

    # Waste reduction improves with sensitivity
    waste_reduction = AUTOSCALING_BASE_WASTE_FRACTION * (0.3 + 0.7 * sens_frac)

    compute_resources = [r for r in resources if _is_compute(r)]
    total_compute_cost = sum(_get_monthly_cost(r) for r in compute_resources)
    total_savings = round(total_compute_cost * waste_reduction, 2)

    # Compute avg peak-to-mean ratio for explainability
    peak_ratios = []
    for r in compute_resources:
        metrics = r.get("metrics") or {}
        cpu = metrics.get("cpu") or {}
        if isinstance(cpu, dict):
            avg = _safe_float(cpu.get("avg"))
            mx = _safe_float(cpu.get("max"))
            if avg > 0 and mx > 0:
                peak_ratios.append(mx / avg)

    avg_peak_ratio = round(sum(peak_ratios) / len(peak_ratios), 2) if peak_ratios else 1.0

    return {
        "sensitivity": sensitivity,
        "estimated_savings": total_savings,
        "total_compute_cost": round(total_compute_cost, 2),
        "waste_reduction_pct": round(waste_reduction * 100, 1),
        "avg_peak_to_mean_ratio": avg_peak_ratio,
        "optimized_thresholds": {
            "scale_up_cpu": round(60 + sens_frac * 20),     # 60-80%
            "scale_down_cpu": round(20 + sens_frac * 15),   # 20-35%
            "cooldown_seconds": round(300 - sens_frac * 180),  # 300-120s
        },
        "confidence": 0.82,
    }


# ---------------------------------------------------------------------------
# 5. Storage Optimization
# ---------------------------------------------------------------------------

def analyze_storage(resources: List[Dict]) -> Dict[str, Any]:
    candidates = []
    total_savings = 0.0

    for r in resources:
        if not _is_storage(r):
            continue
        cost = _get_monthly_cost(r)
        config = r.get("config") or {}

        suggestions = []

        # Check lifecycle policy
        has_lifecycle = bool(config.get("lifecycle_rules"))
        if not has_lifecycle and cost > 0:
            lifecycle_savings = round(cost * STORAGE_LIFECYCLE_SAVINGS_RATE, 2)
            suggestions.append({
                "action": "add_lifecycle_policy",
                "description": "Add lifecycle policy to transition old objects to cheaper tiers",
                "projected_savings": lifecycle_savings,
            })
            total_savings += lifecycle_savings

        # Check for Glacier-eligible data
        metrics = r.get("metrics") or {}
        size_bytes = _safe_float(metrics.get("total_size_bytes") or metrics.get("size_bytes", 0))
        object_count = _safe_float(metrics.get("object_count", 0))

        if size_bytes > 1_000_000_000 and not has_lifecycle:  # > 1 GB
            glacier_savings = round(cost * STORAGE_GLACIER_SAVINGS_RATE, 2)
            suggestions.append({
                "action": "archive_to_glacier",
                "description": "Archive large infrequently-accessed data to Glacier",
                "projected_savings": glacier_savings,
            })
            # Don't double-count — take max
            if glacier_savings > (total_savings - sum(s["projected_savings"] for s in suggestions[:-1])):
                pass  # already counted via lifecycle

        # Also count analyzer-agent savings for storage resources
        rec_savings = _recommendation_savings(r)
        if rec_savings > 0:
            total_savings = max(total_savings, rec_savings)

        if suggestions:
            candidates.append({
                "resource_id": r.get("resource_id"),
                "name": r.get("name"),
                "type": _resource_type(r),
                "monthly_cost": round(cost, 2),
                "suggestions": suggestions,
            })

    return {
        "enabled": True,
        "estimated_savings": round(total_savings, 2),
        "candidates": len(candidates),
        "resources": candidates,
        "confidence": 0.87 if candidates else 0.5,
    }


# ---------------------------------------------------------------------------
# 6. Monthly Bill Prediction
# ---------------------------------------------------------------------------

def predict_monthly_bill(
    resources: List[Dict],
    config: Dict[str, Any],
    section_results: Dict[str, Dict],
) -> Dict[str, Any]:
    current_cost = sum(_get_monthly_cost(r) for r in resources)

    # Aggregate savings from enabled sections
    total_savings = 0.0
    breakdown = {}

    if config.get("idle_resources_enabled", False):
        s = section_results.get("idle", {}).get("estimated_savings", 0)
        total_savings += s
        breakdown["idle_resources"] = round(s, 2)

    s = section_results.get("rightsizing", {}).get("estimated_savings", 0)
    total_savings += s
    breakdown["right_sizing"] = round(s, 2)

    if config.get("scheduling_enabled", False):
        s = section_results.get("scheduling", {}).get("estimated_savings", 0)
        total_savings += s
        breakdown["scheduling"] = round(s, 2)

    s = section_results.get("autoscaling", {}).get("estimated_savings", 0)
    total_savings += s
    breakdown["auto_scaling"] = round(s, 2)

    if config.get("storage_optimization_enabled", False):
        s = section_results.get("storage", {}).get("estimated_savings", 0)
        total_savings += s
        breakdown["storage"] = round(s, 2)

    optimized_cost = max(0, current_cost - total_savings)

    # Weighted confidence
    confidences = [
        section_results.get(k, {}).get("confidence", 0.8)
        for k in ("idle", "rightsizing", "scheduling", "autoscaling", "storage")
    ]
    avg_conf = sum(confidences) / len(confidences)

    return {
        "current_month_cost": round(current_cost, 2),
        "optimized_cost": round(optimized_cost, 2),
        "predicted_savings": round(total_savings, 2),
        "savings_breakdown": breakdown,
        "confidence": round(avg_conf, 2),
    }


# ---------------------------------------------------------------------------
# 7. Optimization Score
# ---------------------------------------------------------------------------

def compute_optimization_score(
    resources: List[Dict],
    section_results: Dict[str, Dict],
) -> int:
    total = len(resources)
    if total == 0:
        return 100

    # Factor 1: % of resources already optimized (30 points)
    optimized_count = sum(
        1 for r in resources
        if r.get("is_optimized") or r.get("status") == "optimized"
    )
    optimized_pct = optimized_count / total
    score_optimized = optimized_pct * 30

    # Factor 2: % of recommendations resolved (30 points)
    total_recs = 0
    resolved_recs = 0
    for r in resources:
        for rec in (r.get("recommendations") or []):
            total_recs += 1
            if (rec.get("status") or "").lower() == "resolved":
                resolved_recs += 1
    resolved_pct = resolved_recs / total_recs if total_recs > 0 else 1.0
    score_resolved = resolved_pct * 30

    # Factor 3: low idle waste (20 points)
    idle_count = section_results.get("idle", {}).get("affected_resources", 0)
    idle_ratio = idle_count / total
    score_idle = max(0, (1 - idle_ratio * 2)) * 20  # 0 idle = full 20 points

    # Factor 4: savings captured vs available (20 points)
    total_cost = sum(_get_monthly_cost(r) for r in resources)
    total_available_savings = sum(
        _recommendation_savings(r) for r in resources
    )
    if total_cost > 0:
        savings_ratio = min(1.0, total_available_savings / total_cost)
        # Lower available savings = higher score (less waste to fix)
        score_efficiency = (1 - savings_ratio) * 20
    else:
        score_efficiency = 20

    raw_score = score_optimized + score_resolved + score_idle + score_efficiency
    return max(0, min(100, round(raw_score)))


# ---------------------------------------------------------------------------
# 8. CO2 Reduction
# ---------------------------------------------------------------------------

def estimate_co2_reduction(
    total_monthly_savings: float,
) -> Dict[str, Any]:
    annual_savings = total_monthly_savings * 12
    co2_kg_annual = round(annual_savings * CO2_KG_PER_DOLLAR_MONTH_ANNUALIZED, 1)

    return {
        "co2_kg_per_year": co2_kg_annual,
        "equivalent_trees": round(co2_kg_annual / 22, 1),  # ~22 kg CO2 per tree/year
        "methodology": "Based on AWS carbon footprint estimates (~0.4 kg CO2 per $1/month annualized)",
    }


# ---------------------------------------------------------------------------
# 9. Implementation Plan
# ---------------------------------------------------------------------------

def generate_implementation_plan(
    section_results: Dict[str, Dict],
    config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    plan = []

    # Immediate (0-1 days): idle resource cleanup
    idle = section_results.get("idle", {})
    if config.get("idle_resources_enabled") and idle.get("affected_resources", 0) > 0:
        plan.append({
            "phase": "immediate",
            "timeframe": "0-1 days",
            "title": "Idle Resource Cleanup",
            "description": f"Stop {idle['affected_resources']} idle resource(s) with <{IDLE_CPU_THRESHOLD}% CPU",
            "estimated_savings": idle.get("estimated_savings", 0),
            "risk": "low",
            "actions": [
                f"Stop {r['resource_id']} ({r['type']})"
                for r in idle.get("resources", [])[:5]
            ],
        })

    # Short-term (1-7 days): right-sizing + scheduling
    rs = section_results.get("rightsizing", {})
    if rs.get("candidates", 0) > 0:
        plan.append({
            "phase": "short_term",
            "timeframe": "1-7 days",
            "title": "Resource Right-Sizing",
            "description": f"Resize {rs['candidates']} underutilized resource(s)",
            "estimated_savings": rs.get("estimated_savings", 0),
            "risk": "medium",
            "actions": [
                f"Right-size {r['resource_id']} (CPU avg: {r['cpu_avg']}%)"
                for r in rs.get("resources", [])[:5]
            ],
        })

    sched = section_results.get("scheduling", {})
    if config.get("scheduling_enabled") and sched.get("schedulable_resources", 0) > 0:
        plan.append({
            "phase": "short_term",
            "timeframe": "1-7 days",
            "title": "Smart Scheduling",
            "description": f"Enable off-hours scheduling for {sched['schedulable_resources']} dev/test resource(s)",
            "estimated_savings": sched.get("estimated_savings", 0),
            "risk": "low",
            "actions": [
                f"Schedule {r['resource_id']}: {r['suggested_schedule']}"
                for r in sched.get("resources", [])[:5]
            ],
        })

    # Long-term (1-4 weeks): auto-scaling + storage
    asc = section_results.get("autoscaling", {})
    if asc.get("estimated_savings", 0) > 0:
        plan.append({
            "phase": "long_term",
            "timeframe": "1-4 weeks",
            "title": "Auto-Scaling Optimization",
            "description": f"Tune scaling policies to reduce {asc.get('waste_reduction_pct', 0)}% over-provisioning waste",
            "estimated_savings": asc.get("estimated_savings", 0),
            "risk": "medium",
            "actions": [
                f"Set scale-up threshold to {asc.get('optimized_thresholds', {}).get('scale_up_cpu', 70)}% CPU",
                f"Set scale-down threshold to {asc.get('optimized_thresholds', {}).get('scale_down_cpu', 25)}% CPU",
                f"Reduce cooldown to {asc.get('optimized_thresholds', {}).get('cooldown_seconds', 180)}s",
            ],
        })

    stor = section_results.get("storage", {})
    if config.get("storage_optimization_enabled") and stor.get("candidates", 0) > 0:
        plan.append({
            "phase": "long_term",
            "timeframe": "1-4 weeks",
            "title": "Storage Tier Optimization",
            "description": f"Optimize {stor['candidates']} storage resource(s) with lifecycle policies",
            "estimated_savings": stor.get("estimated_savings", 0),
            "risk": "low",
            "actions": [
                f"Optimize {r['resource_id']}: {r['suggestions'][0]['description']}"
                for r in stor.get("resources", [])[:5]
                if r.get("suggestions")
            ],
        })

    return plan


# ---------------------------------------------------------------------------
# 10. Full Orchestrator
# ---------------------------------------------------------------------------

def run_optimization_analysis(
    resources: List[Dict[str, Any]],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Run the full optimization analysis pipeline.
    Returns everything the frontend needs in one payload.
    """
    # Run each analyzer
    idle = analyze_idle_resources(resources)
    rightsizing = analyze_rightsizing(resources, config.get("right_sizing_level", 70))
    scheduling = analyze_scheduling(resources)
    autoscaling = analyze_autoscaling(resources, config.get("auto_scaling_level", 50))
    storage = analyze_storage(resources)

    section_results = {
        "idle": idle,
        "rightsizing": rightsizing,
        "scheduling": scheduling,
        "autoscaling": autoscaling,
        "storage": storage,
    }

    # Bill prediction
    bill = predict_monthly_bill(resources, config, section_results)

    # Optimization score
    score = compute_optimization_score(resources, section_results)

    # CO2
    co2 = estimate_co2_reduction(bill["predicted_savings"])

    # Implementation plan
    plan = generate_implementation_plan(section_results, config)

    # Projections summary (matches frontend shape)
    projections = {
        "monthly": round(bill["predicted_savings"], 2),
        "yearly": round(bill["predicted_savings"] * 12, 2),
        "co2": co2["co2_kg_per_year"],
        "optimization_score": score,
    }

    return {
        "config": config,
        "projections": projections,
        "sections": {
            "idle_resources": idle,
            "right_sizing": rightsizing,
            "scheduling": scheduling,
            "auto_scaling": autoscaling,
            "storage": storage,
        },
        "bill_prediction": bill,
        "optimization_score": score,
        "co2_reduction": co2,
        "implementation_plan": plan,
    }
