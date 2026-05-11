"""
Terraform Drift Detection API Routes
-------------------------------------
Endpoints:
- GET /drift/detect - Compare Terraform state vs AWS
- POST /drift/fix - Create PR to fix drift (user chooses direction)
"""

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from typing import Literal

from services.drift import detect_terraform_drifts
from services.drift_pr_creator import create_drift_fix_pr

router = APIRouter(prefix="/drift", tags=["drift"])


class DriftFixRequest(BaseModel):
    """Request body for fixing a drift."""
    drift: dict  # The full drift object from /detect response
    fix_direction: Literal["terraform_to_aws", "aws_to_terraform"]


@router.get("/detect")
def detect_drift(
    tf_state_file: str = Query(default="terraform-generated/terraform.tfstate"),  # This is correct
    region: str = Query(default="us-east-1"),
):
    """
    Compare Terraform state against live AWS.
    Returns all detected drifts.
    """
    try:
        print(f"Received request to /drift/detect with tf_state_file={tf_state_file} and region={region}")
        result = detect_terraform_drifts(tf_state_file, region)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data")
def get_drift_data(
    tf_state_file: str = Query(default="terraform-generated/terraform.tfstate"),
    region: str = Query(default="us-east-1"),
):
    """
    Alias for /detect to match frontend expectations.
    """

    print(f"Received request to /drift/data with tf_state_file={tf_state_file} and region={region}")
    return detect_drift(tf_state_file, region)


@router.post("/fix")
def fix_drift(request: DriftFixRequest):
    """
    Create a GitHub PR to fix the drift.
    User chooses the fix direction:
    - "terraform_to_aws": Update Terraform to match AWS (AWS is truth)
    - "aws_to_terraform": Run terraform apply to force AWS to match Terraform
    """
    print(f"Received request to /drift/fix with drift={request.drift} and fix_direction={request.fix_direction}")
    try:
        result = create_drift_fix_pr(
            drift=request.drift,
            fix_direction=request.fix_direction,
        )
        return {
            "status": "ok",
            "message": f"PR created successfully: {result['pr_url']}",
            **result,
        }
    except Exception as e:
        print(f"Error in /drift/fix: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))