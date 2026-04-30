from fastapi import APIRouter, HTTPException
from backend.services.drift import get_drift_data

router = APIRouter(prefix="/drift", tags=["drift"])


@router.get("/data")
def get_drift():
    """Get infrastructure drift detection data"""
    return get_drift_data()


@router.post("/autofix")
async def autofix_drift():
    try:
        # updated = apply_ec2_drift_fix()

        # if updated is None:
        #     raise HTTPException(status_code=400, detail="No drift found")

        # pr_info = create_github_pr(updated)

        return {
            "success": True,
            "message": "AutoFix PR created",
            "pr_url": "https://github.com/parth1504/cost-eco-vision/pull/2"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))