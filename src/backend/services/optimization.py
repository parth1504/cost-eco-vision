"""
Optimization service — wires the cost_engine to real resource data.

Replaces the old mock-data service. Config is held in-memory (same as before)
and projections are computed dynamically from live resources.
"""

from typing import Dict, Any

from services.resources import get_all_resources
from services.cost_engine import run_optimization_analysis


# In-memory config (same UX as before — survives across requests, resets on restart)
_optimization_config: Dict[str, Any] = {
    "idle_resources_enabled": True,
    "right_sizing_level": 70,
    "scheduling_enabled": False,
    "auto_scaling_level": 50,
    "storage_optimization_enabled": True,
}


async def get_optimization_data() -> Dict[str, Any]:
    """Fetch live resources and compute the full optimization analysis."""
    resources = await get_all_resources()
    return run_optimization_analysis(resources, _optimization_config)


async def update_optimization_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Update config sliders/toggles and recompute projections."""
    global _optimization_config
    config = payload.get("config") or payload
    _optimization_config.update(config)

    resources = await get_all_resources()
    result = run_optimization_analysis(resources, _optimization_config)
    return {
        "config": _optimization_config,
        "projections": result["projections"],
        "sections": result["sections"],
        "bill_prediction": result["bill_prediction"],
        "implementation_plan": result["implementation_plan"],
    }


def apply_optimization(optimization_id: str) -> Dict[str, Any]:
    """
    Placeholder for future integration with actions_agent.
    For now, acknowledge the request.
    """
    return {
        "success": True,
        "optimization_id": optimization_id,
        "message": f"Optimization plan '{optimization_id}' queued for execution via actions_agent.",
        "status": "queued",
    }
