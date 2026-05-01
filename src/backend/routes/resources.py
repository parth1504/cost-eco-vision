from fastapi import APIRouter, Body, HTTPException
from typing import Dict, Any
from decimal import Decimal
from datetime import datetime
from . import resources
from connections.db import get_resource_from_db, save_resource_in_db
from aws.util import apply_aws_commands
from services.resources import get_all_resources


router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("")
async def get_resources():
    print("Fetching all resources...")
    resources_data = await get_all_resources()  # from AWS
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