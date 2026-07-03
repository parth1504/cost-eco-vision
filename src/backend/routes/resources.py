from fastapi import APIRouter, Body, HTTPException
from typing import Dict, Any, List
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel
from services import resources
from connections.db import get_resource_from_db, save_resource_in_db
from aws.util import apply_aws_commands
from services.resources import get_all_resources
from agents.actions_agent import ActionsAgent


router = APIRouter(prefix="/resources", tags=["resources"])
actions_agent = ActionsAgent()


class SelectedStep(BaseModel):
    recommendation_index: int
    step_indices: List[int]


class ApplyFixesRequest(BaseModel):
    resource_id: str
    resource_type: str
    selected_steps: List[SelectedStep]


@router.get("")
async def get_resources(force: bool = False):
    """
    Pass ?force=true to bypass the agent cooldown — useful after deploying
    a new rule so all resources get re-evaluated instead of waiting up to
    60 minutes for each cache to expire individually.
    """
    print(f"Fetching all resources... (force={force})")
    resources_data = await get_all_resources(force=force)
    return resources_data


@router.get("/{resource_id}")
def get_resource(resource_id: str, data: dict = Body(...)):
    print("Fetching resource:", resource_id)
    resource_type = data.get("resource_type")

    resource = resources.get_resource_by_id(resource_id, resource_type)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    return resource


def decimal_to_float(obj):
    """Convert DynamoDB Decimal types → float safely."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [decimal_to_float(v) for v in obj]
    return obj


@router.put("/{resource_id}/optimize")
async def optimize_resource_api(resource_id: str, data: dict = Body(...)):
    resource_type = data.get("resource_type")

    if not resource_type:
        raise HTTPException(status_code=400, detail="resource_type is required")

    # Load resource
    resource = get_resource_from_db(resource_id, resource_type)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    print(f"🚀 Starting full optimization for resource {resource_id}")

    recommendations = resource.get("recommendations", [])

    for rec in recommendations:
        boto_sequence = rec.get("boto3_sequence")

        if not boto_sequence:
            continue

        print(f"⚡ Running AWS automation for: {rec.get('title')}")

        results = await apply_aws_commands(boto_sequence)

        all_success = all(r.get("success") for r in results)

        if all_success:
            print(f"✅ Optimization successful: {rec.get('title')}")
            rec["status"] = "resolved"
            rec["last_activity"] = datetime.utcnow().isoformat() + "Z"
        else:
            print(f"❌ Failed to optimize: {rec.get('title')}")
            rec["status"] = "active"

    resource["status"] = "optimized"

    save_resource_in_db(
        resource_id=resource_id,
        resource_type=resource_type,
        resource_data=resource
    )

    return decimal_to_float(resource)


@router.post("/apply-fixes")
async def apply_selected_fixes(request: ApplyFixesRequest):
    resource = get_resource_from_db(request.resource_id, request.resource_type)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    recommendations = resource.get("recommendations", [])
    if not recommendations:
        raise HTTPException(status_code=400, detail="Resource has no recommendations")

    selected_map = {
        s.recommendation_index: s.step_indices for s in request.selected_steps
    }

    result = actions_agent.apply_selected_fixes(
        resource_id=request.resource_id,
        resource_type=request.resource_type,
        recommendations=recommendations,
        selected_step_indices=selected_map,
    )

    if result["status"] in ("completed", "partial_failure"):
        for r in result.get("results", []):
            rec_idx = r["recommendation_index"]
            if rec_idx < len(recommendations):
                recommendations[rec_idx]["status"] = (
                    "resolved" if r["all_success"] else "active"
                )
                recommendations[rec_idx]["last_activity"] = (
                    datetime.utcnow().isoformat() + "Z"
                )

        all_resolved = all(
            rec.get("status") == "resolved" for rec in recommendations
        )
        if all_resolved:
            resource["status"] = "optimized"

        save_resource_in_db(
            resource_id=request.resource_id,
            resource_type=request.resource_type,
            resource_data=resource,
        )

    return decimal_to_float(result)


@router.post("/preview-fixes")
async def preview_fixes(request: ApplyFixesRequest):
    resource = get_resource_from_db(request.resource_id, request.resource_type)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    recommendations = resource.get("recommendations", [])
    selected_map = {
        s.recommendation_index: s.step_indices for s in request.selected_steps
    }

    plan = actions_agent.preview_plan(recommendations, selected_map)
    return plan