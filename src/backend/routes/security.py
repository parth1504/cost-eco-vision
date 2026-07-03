from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from services import security
from services.security import (
    get_security_data,
    get_security_keys_and_certs,
    rotate_iam_access_key,
    delete_iam_access_key,
)
from services.compliance import get_compliance_summary
from services.security_triage_agent import triage_findings
from connections.db import get_security_triage

router = APIRouter(prefix="/security", tags=["security"])


def _merge_cached_triage(security_data: dict) -> dict:
    """Attach any previously-generated AI triage to each finding."""
    for f in security_data.get("findings", []):
        fid = f.get("id")
        if not fid:
            continue
        cached = get_security_triage(fid)
        if cached:
            f["aiTriage"] = {k: v for k, v in cached.items() if k not in ("finding_id", "cached_at")}
    return security_data


@router.get("/data")
async def get_security_comprehensive():
    """Get comprehensive security data (keys, scores, compliance, recommendations)"""
    return await get_security_data()


# Get all findings
@router.get("")
async def get_security():
    security_data = await security.get_securiity_findings()
    return _merge_cached_triage(security_data)


# IMPORTANT: these routes must be declared before "/{finding_id}" so FastAPI
# doesn't route their path segments into the dynamic param.

@router.get("/compliance")
def get_compliance():
    """Per-framework compliance scores from AWS Security Hub."""
    try:
        return get_compliance_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Compliance lookup failed: {e}")


# ========== NEW: KEYS & CERTIFICATES MANAGEMENT ==========

@router.get("/keys")
async def get_keys_and_certs(region: str = "us-east-1"):
    """
    Get all security keys and certificates with detailed analysis:
    - IAM access keys (with last used, rotation status, permissions)
    - ACM SSL/TLS certificates (with expiry tracking)
    """
    try:
        result = await get_security_keys_and_certs(region)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RotateKeyRequest(BaseModel):
    key_id: str
    user_name: str


@router.post("/keys/rotate")
async def rotate_key(request: RotateKeyRequest):
    """
    Rotate an IAM access key.
    Creates new key, marks old key as inactive.
    User must update applications before deleting old key.
    """
    try:
        result = await rotate_iam_access_key(request.key_id, request.user_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class DeleteKeyRequest(BaseModel):
    key_id: str
    user_name: str


@router.post("/keys/delete")
async def delete_key(request: DeleteKeyRequest):
    """
    Delete an unused IAM access key.
    WARNING: This cannot be undone.
    """
    try:
        result = await delete_iam_access_key(request.key_id, request.user_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== END NEW ROUTES ==========


@router.post("/triage")
async def run_triage(force: bool = False):
    """
    Run the LLM triage agent over all current security findings.

    Adds context-aware severity, plain-language explanations, blast radius,
    and cross-finding correlations. Cached per finding_id; pass `?force=true`
    to regenerate.
    """
    security_data = await security.get_securiity_findings()
    findings = security_data.get("findings", [])
    if not findings:
        return {"triaged": 0, "findings": []}

    try:
        triages = triage_findings(findings, force=force)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Merge triage onto findings for the response.
    for f in findings:
        fid = f.get("id")
        if fid in triages:
            f["aiTriage"] = triages[fid]

    return {"triaged": len(triages), "findings": findings}


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