from fastapi import APIRouter, Body, HTTPException
import security
from security import get_security_data
router = APIRouter(prefix="/security", tags=["security"])


@router.get("/data")
async def get_security_comprehensive():
    """Get comprehensive security data (keys, scores, compliance, recommendations)"""
    return await get_security_data()


# Get all findings
@router.get("")
async def get_security():
    security_data = await security.get_securiity_findings()
    findings = security_data.get("findings", [])  # (optional use)

    return security_data


@router.get("/{finding_id}")
async def get_security_finding(finding_id: str):
    finding = await security.get_finding_by_id(finding_id)

    if not finding:
        raise HTTPException(status_code=404, detail="Security finding not found")

    return finding


# Update finding status
@router.put("/{finding_id}")
async def update_security_finding(finding_id: str, payload: dict = Body(...)):
    print("Updating security finding:", finding_id)

    status = payload.get("status")
    if not status:
        raise HTTPException(status_code=422, detail="Missing 'status' in request body")

    finding = await security.update_finding(finding_id, status)

    if not finding:
        raise HTTPException(status_code=404, detail="Security finding not found")

    return {"success": True, "finding": finding}