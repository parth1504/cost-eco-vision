from fastapi import APIRouter, Response
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io

router = APIRouter(prefix="/incident", tags=["incident"])


@router.get("/data")
def get_incident():
    """Get incident room data (timeline, root cause, checklist)"""
    return get_incident_data()


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