from fastapi import APIRouter, Body, HTTPException, Response
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
from datetime import datetime
from services.incidents import (
    get_incident_detail,
    list_incidents,
    refresh_incidents,
    update_incident_status,
    VALID_STATUSES,
)
from services.incident_agent import analyze_incident
from services.correlation_layer2 import run_layer2_correlation
from services.incident_scenarios import seed_scenario, get_all_scenario_ids
from connections.db import get_incident

router = APIRouter(prefix="/incident", tags=["incident"])


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


@router.post("/seed-scenarios")
async def seed_microservice_scenarios(scenario_id: str = None):
    """Seed realistic microservice incident scenarios for demo/presentation."""
    return seed_scenario(scenario_id)


@router.get("/scenarios")
async def list_scenario_ids():
    """List available scenario IDs."""
    return get_all_scenario_ids()


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


@router.get("/{incident_id}/report")
async def generate_incident_report(incident_id: str):
    """Generate a PDF report from real incident data."""
    incident = get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    detail = await get_incident_detail(incident_id)
    analysis = incident.get("analysis") or {}
    root_cause = analysis.get("rootCause") or {}
    checklist = analysis.get("checklist") or []
    timeline = detail.get("timeline") or []

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    margin = 50
    y = height - margin

    def write_line(text: str, font="Helvetica", size=11, indent=0):
        nonlocal y
        if y < 60:
            pdf.showPage()
            y = height - margin
        pdf.setFont(font, size)
        pdf.drawString(margin + indent, y, text)
        y -= size + 4

    def write_section(title: str):
        nonlocal y
        y -= 8
        write_line(title, font="Helvetica-Bold", size=13)
        y -= 2

    # Header
    write_line("Incident Report", font="Helvetica-Bold", size=18)
    write_line(
        f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        size=9,
    )
    y -= 10

    # Summary
    write_section("Summary")
    write_line(f"Incident ID:  {incident_id}")
    write_line(f"Title:  {incident.get('title', 'N/A')}")
    write_line(f"Severity:  {(incident.get('severity') or 'N/A').upper()}")
    write_line(f"Status:  {(incident.get('status') or 'open').capitalize()}")
    write_line(f"Category:  {(incident.get('category') or 'N/A').capitalize()}")
    resources = incident.get("resources_affected") or []
    write_line(f"Affected Resources:  {', '.join(resources) if resources else 'N/A'}")
    write_line(f"Alerts in Incident:  {len(incident.get('member_alert_ids', []))}")

    # Lifecycle timestamps
    for field, label in [
        ("created_at", "Created"),
        ("investigating_at", "Investigation Started"),
        ("mitigated_at", "Mitigated"),
        ("resolved_at", "Resolved"),
    ]:
        val = incident.get(field) or detail.get(field)
        if val:
            write_line(f"{label}:  {val}")

    # Timeline
    if timeline:
        write_section("Alert Timeline")
        for event in timeline:
            ts = event.get("timestamp", "")
            try:
                ts_fmt = datetime.fromisoformat(ts.rstrip("Z")).strftime("%H:%M:%S")
            except Exception:
                ts_fmt = ts[:19] if ts else "N/A"
            sev = (event.get("severity") or "").upper()
            msg = event.get("message") or ""
            write_line(f"[{ts_fmt}]  [{sev}]  {msg[:90]}", size=10, indent=10)

    # Root Cause Analysis
    if root_cause:
        write_section("Root Cause Analysis")
        if root_cause.get("primaryCause"):
            write_line("Primary Cause:", font="Helvetica-Bold", size=11)
            write_line(f"  {root_cause['primaryCause']}", indent=10)

        factors = root_cause.get("contributingFactors") or []
        if factors:
            y -= 4
            write_line("Contributing Factors:", font="Helvetica-Bold", size=11)
            for f in factors:
                write_line(f"  - {f}", indent=10, size=10)

        actions = root_cause.get("immediateActions") or []
        if actions:
            y -= 4
            write_line("Immediate Actions:", font="Helvetica-Bold", size=11)
            for a in actions:
                write_line(f"  - {a}", indent=10, size=10)

        if root_cause.get("confidence") is not None:
            write_line(f"AI Confidence: {root_cause['confidence']}%", size=10)

    # Mitigation Checklist
    if checklist:
        write_section("Mitigation Checklist")
        for item in checklist:
            status = "DONE" if item.get("completed") else "TODO"
            write_line(f"  [{status}]  {item.get('task', '')}", indent=10, size=10)

    # Resolution summary
    write_section("Resolution")
    status = (incident.get("status") or "open").lower()
    if status == "resolved":
        write_line("This incident has been marked as resolved.")
        resolved_at = incident.get("resolved_at")
        if resolved_at:
            write_line(f"Resolved at: {resolved_at}")
    else:
        write_line(f"Current status: {status.capitalize()}. Incident is not yet resolved.")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="incident-report-{incident_id}.pdf"'
        },
    )