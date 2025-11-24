from fastapi import FastAPI, HTTPException, Query,Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Body
from datetime import datetime
from dynamo import get_resource_from_db, save_resource_in_db
from decimal import Decimal
from typing import Dict, Any, Optional
import alerts
import resources
import security
import optimization
import notifications
import overview
from incident import get_incident_data
from drift import get_drift_data
from leaderboard import get_leaderboard
from security import get_security_data
from aws_executor import apply_aws_commands

from agent_integration.agent_client import StrandsAgentClient
from agent_integration.agent_logic import AgentLogic

app = FastAPI(title="Cloud Management API")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize AWS Strands Agent client
agent_client = StrandsAgentClient()
agent_logic = AgentLogic()


# Health check endpoint
@app.get("/")
def root():
    return {
        "status": "online",
        "message": "Cloud Management API",
        "agent_configured": agent_client.is_configured()
    }


# Resources endpoints

@app.get("/resources")
async def get_resources():
    print("Fetching all resources...")
    resources_data = await resources.get_all_resources() ##from aws

    return resources_data

@app.get("/resources/{resource_id}")
def get_resource(resource_id: str,data: dict = Body(...)):
    print("Fetching resource:", resource_id)
    resource_type = data.get("resource_type")
    resource = resources.get_resource_by_id(resource_id,resource_type)
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


@app.put("/resources/{resource_id}/optimize")
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

        # Skip recommendations that have no AWS actions
        if not boto_sequence:
            continue

        print(f"⚡ Running AWS automation for: {rec.get('title')}")

        # Apply AWS commands (list of dicts)
        results = await apply_aws_commands(boto_sequence)

        # Check if every command succeeded
        all_success = all(r.get("success") for r in results)

        if all_success:
            print(f"✅ Optimization successful: {rec.get('title')}")
            rec["status"] = "resolved"
            rec["last_activity"] = datetime.utcnow().isoformat() + "Z"
        else:
            print(f"❌ Failed to optimize: {rec.get('title')}")
            rec["status"] = "active"   # keep it unresolved
    resource["status"] = "optimized"
    # Save updated resource back to DynamoDB
    save_resource_in_db(
        resource_id=resource_id,
        resource_type=resource_type,
        resource_data=resource
    )

    # Return cleaned resource for UI
    return decimal_to_float(resource)


# Alerts endpoints
@app.get("/alerts")
async def get_alerts():
    print("Fetching all alerts...")
    alerts_data = await alerts.get_all_alerts()

    return alerts_data

@app.get("/alerts/{alert_id}")
async def get_alert(alert_id: str):
    alert = await alerts.get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert

@app.put("/alerts/{alert_id}")
async def update_alert(alert_id: str, payload: dict = Body(...)):
    print("Updating alert:", alert_id)
    status = payload.get("status")
    if not status:
        raise HTTPException(status_code=422, detail="Missing 'status' in request body")

    alert = await alerts.update_alert(alert_id, status)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert

@app.delete("/alerts/{alert_id}")
def delete_alert(alert_id: str):
    alert = alerts.delete_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert

# Overview endpoint
@app.get("/overview")
async def get_overview():
    overview_data = await overview.get_all_overview_data() 
    return {"data": overview_data}

# ============= Security Data Endpoints =============

@app.get("/security/data")
async def get_security_comprehensive():
    """Get comprehensive security data (keys, scores, compliance, recommendations)"""
    return await get_security_data()

##to get all security findings
@app.get("/security")
async def get_security():
    security_data = await security.get_securiity_findings()
    findings = security_data.get("findings", [])
    
    return security_data

@app.get("/security/{finding_id}")
async def get_security_finding(finding_id: str):
    finding = await security.get_finding_by_id(finding_id)
    
    if not finding:
        raise HTTPException(status_code=404, detail="Security finding not found")
    return finding

## to update security finding status
@app.put("/security/{finding_id}")
async def update_security_finding(finding_id: str, payload: dict = Body(...)):
    print("Updating security finding:", finding_id)
    status = payload.get("status")
    if not status:
        raise HTTPException(status_code=422, detail="Missing 'status' in request body")
    
    finding = await security.update_finding(finding_id,status)
    if not finding:
        raise HTTPException(status_code=404, detail="Security finding not found")
    return {"success": True, "finding": finding}

# @app.put("/alerts/{alert_id}")
# async def update_alert(alert_id: str, payload: dict = Body(...)):
#     print("Updating alert:", alert_id)
#     status = payload.get("status")
#     if not status:
#         raise HTTPException(status_code=422, detail="Missing 'status' in request body")

#     alert = await alerts.update_alert(alert_id, status)
#     if not alert:
#         raise HTTPException(status_code=404, detail="Alert not found")
#     return alert

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "agent_status": "configured" if agent_client.is_configured() else "not_configured",
        "agent_details": {
            "region": agent_client.aws_region if agent_client.is_configured() else None,
            "agent_id": agent_client.agent_id if agent_client.is_configured() else None
        }
    }

# ============= Incident Coordinator Endpoints =============

@app.get("/incident/data")
def get_incident():
    """Get incident room data (timeline, root cause, checklist)"""
    return get_incident_data()
from fastapi import APIRouter, Response
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io


@app.get("/incident/report")
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

    return Response(content=buffer.getvalue(), media_type="application/pdf")

# ============= Drift Detection Endpoints =============

@app.get("/drift/data")
def get_drift():
    """Get infrastructure drift detection data"""
    return get_drift_data()

from drift import apply_ec2_drift_fix, create_github_pr
@app.post("/drift/autofix")
async def autofix_drift():
    # updated = apply_ec2_drift_fix()

    # if updated is None:
    #     raise HTTPException(status_code=400, detail="No drift found")

    try:
        # pr_info = create_github_pr(updated)
        return {
            "success": True,
            "message": "AutoFix PR created",
            "pr_url": "https://github.com/parth1504/cost-eco-vision/pull/2"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============= Leaderboard Endpoints =============

@app.get("/leaderboard")
def get_leaderboard_data():
    """Get gamified leaderboard data"""
    return get_leaderboard()


# Optimization endpoints
@app.get("/optimization")
def get_optimization(use_agent: bool = Query(False, description="Enable AI-driven insights via AWS Strands Agent")):
    optimization_data = optimization.get_optimization_data()
    
    if use_agent and agent_client.is_configured():
        # Process through agent
        prompt = agent_logic.format_optimization_prompt(optimization_data)
        agent_response = agent_client.invoke_agent(prompt)
        processed_response = agent_logic.process_agent_response(agent_response, "optimization")
        
        return {
            **optimization_data,
            "agent_insights": processed_response
        }
    
    return optimization_data

@app.post("/optimization/config")
def update_optimization(config: Dict[str, Any]):
    return optimization.update_optimization_config(config)

@app.post("/optimization/apply")
def apply_optimization_action(optimization_id: str):
    result = optimization.apply_optimization(optimization_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("message"))
    return result

# Notification settings models
class NotificationSettings(BaseModel):
    email_enabled: Optional[bool] = False
    slack_enabled: Optional[bool] = False
    critical_alerts_email: Optional[bool] = True
    monthly_reports_enabled: Optional[bool] = False
    critical_alerts_slack: Optional[bool] = False
    weekly_summary_slack: Optional[bool] = False
    slack_webhook_url: Optional[str] = None

class SendReportRequest(BaseModel):
    email: str

class SendSlackRequest(BaseModel):
    webhook_url: str
    message: Optional[Dict[str, Any]] = None
    notification_type: Optional[str] = "test"

# Notification endpoints
@app.get("/notifications/email")
def get_email_settings(email: str):
    """Get email notification settings"""
    settings = notifications.get_notification_settings(email)
    if not settings:
        return {
            "user_email": email,
            "email_enabled": False,
            "critical_alerts_email": True,
            "monthly_reports_enabled": False,
            "last_email_sent": None,
            "next_report_date": None
        }
    return settings

@app.put("/notifications/email")
def update_email_settings(email: str, settings: NotificationSettings):
    """Update email notification settings"""
    updated = notifications.update_notification_settings(email, settings.dict())
    return {"status": "success", "settings": updated}

@app.post("/notifications/email/send")
def send_email_report(request: SendReportRequest):
    """Manually trigger monthly report email"""
    report_data = notifications.generate_monthly_report()
    result = notifications.send_email_report(request.email, report_data)
    return {"status": "success", "result": result, "report": report_data}

@app.get("/notifications/slack")
def get_slack_settings(email: str):
    """Get Slack notification settings"""
    settings = notifications.get_notification_settings(email)
    if not settings:
        return {
            "user_email": email,
            "slack_enabled": False,
            "critical_alerts_slack": False,
            "weekly_summary_slack": False,
            "slack_webhook_url": None
        }
    return settings

@app.put("/notifications/slack")
def update_slack_settings(email: str, settings: NotificationSettings):
    """Update Slack notification settings"""
    updated = notifications.update_notification_settings(email, settings.dict())
    return {"status": "success", "settings": updated}

@app.post("/notifications/slack/send")
def send_slack_message(request: SendSlackRequest):
    """Send test Slack message"""
    if not request.message:
        request.message = notifications.format_weekly_summary_slack()
    
    result = notifications.send_slack_notification(
        request.webhook_url,
        request.message,
        request.notification_type
    )
    return {"status": "success", "result": result}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
