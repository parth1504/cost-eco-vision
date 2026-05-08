from fastapi import APIRouter, Body, HTTPException, Response, Body
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
from services.incident import get_incident_data
from services.incidents import (
    get_incident_detail,
    list_incidents,
    refresh_incidents,
    update_incident_status,
    VALID_STATUSES,
)
from services.incident_agent import analyze_incident
from services.correlation_layer2 import run_layer2_correlation

router = APIRouter(prefix="/incident", tags=["incident"])


@router.get("/data")
def get_incident():
    """[Legacy] Mock incident room data — kept until the new UI is wired up."""
    return get_incident_data()


# --- Real (correlation-backed) endpoints ---------------------------------

@router.post("/refresh")
async def refresh():
    """Re-run correlation over current alerts. Returns the resulting incidents."""
    return await refresh_incidents()


@router.post("/correlate-l2")
async def correlate_layer2():
    """
    Run an opt-in LLM Layer-2 correlation pass: looks at singleton alerts
    + existing incidents and asks the model to merge cross-service incidents
    that Layer-1 deterministic rules couldn't catch.

    Single LLM call. Mutations are applied in-place and recorded on each
    affected incident under `layer2_merges`.
    """
    try:
        return run_layer2_correlation()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Layer-2 correlation failed: {e}")


@router.get("")
async def list_all(include_resolved: bool = True):
    """List all known incidents (most recent first)."""
    return await list_incidents(include_resolved=include_resolved)


@router.get("/{incident_id}")
async def get_one(incident_id: str):
    """Return timeline + (cached) root cause + checklist for one incident."""
    detail = await get_incident_detail(incident_id)
    if not detail.get("timeline"):
        raise HTTPException(status_code=404, detail="Incident not found or has no alerts")
    return detail


@router.post("/{incident_id}/status")
async def set_status(incident_id: str, payload: dict = Body(...)):
    """
    Transition an incident to a new lifecycle status.
    Body: {"status": "open" | "investigating" | "mitigated" | "resolved"}
    """
    new_status = (payload or {}).get("status")
    if not new_status:
        raise HTTPException(status_code=422, detail="Missing 'status' in request body")
    if new_status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status {new_status!r}. Must be one of {list(VALID_STATUSES)}",
        )
    try:
        return await update_incident_status(incident_id, new_status)
    except ValueError as e:
        # Distinguish "not found" from "invalid transition" via message.
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 409
        raise HTTPException(status_code=code, detail=msg)


@router.post("/{incident_id}/analyze")
async def analyze(incident_id: str, force: bool = False):
    """
    Run the LLM agent for this incident — produces root cause + mitigation
    checklist via Claude tool-use against AWS resource data. Cached on the
    incident row; pass `?force=true` to regenerate.
    """
    try:
        analysis = await analyze_incident(incident_id, force=force)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return analysis


@router.get("/report")
def generate_incident_report():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, 750, "Incident Report – Public S3 Bucket Access")

    pdf.setFont("Helvetica", 12)
    y = 720

    sections = [
        "Incident ID: INC-2024-001",
        "Severity: CRITICAL",
        "Primary Cause: Public READ ACL on S3 bucket backup-storage-0189",
        "Contributing Factors:",
        "- Block Public Access disabled",
        "- Anonymous AllUsers READ permission",
        "- Missing encryption",
        "Immediate Actions:",
        "- Removed public ACL",
        "- Enabled Block Public Access",
        "- Enabled SSE-S3 encryption",
        "Resolution: Confirmed by IAM Analyzer",
    ]

    for line in sections:
        pdf.drawString(50, y, line)
        y -= 20

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf"
    )