from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from services.optimization import (
    get_optimization_data,
    update_optimization_config,
    apply_optimization,
)

router = APIRouter(prefix="/optimization", tags=["optimization"])


@router.get("")
async def get_optimization():
    """Return full optimization analysis computed from live resources."""
    return await get_optimization_data()


@router.post("/config")
async def update_config(payload: Dict[str, Any]):
    """Update optimization config (sliders/toggles) and recompute projections."""
    return await update_optimization_config(payload)


@router.post("/apply")
def apply_action(optimization_id: str):
    """Queue an optimization plan for execution."""
    result = apply_optimization(optimization_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result
