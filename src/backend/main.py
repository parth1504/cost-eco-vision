from fastapi import FastAPI, HTTPException, Query,Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Body
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
async def get_resources(use_agent: bool = Query(False, description="Enable AI-driven insights via AWS Strands Agent")):
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
def optimize_resource_api(resource_id: str, data: dict = Body(...)):
    resource_type = data.get("resource_type")

    if not resource_type:
        raise HTTPException(status_code=400, detail="resource_type is required")

    # Fetch stored resource from DynamoDB
    resource = get_resource_from_db(resource_id, resource_type)
    print("Optimizing resource:", resource)

    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found in DynamoDB")

    # Apply optimization
    resource["is_optimized"] = True
    resource["recommendations"] = []

    # Save updated resource back to DynamoDB
    save_resource_in_db(
    resource_id=resource_id,
    resource_type=resource_type,
    resource_data=resource   
)

    # Convert Decimal → float before returning to frontend
    cleaned_resource = decimal_to_float(resource)

    return cleaned_resource


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

# ============= Drift Detection Endpoints =============

@app.get("/drift/data")
def get_drift():
    """Get infrastructure drift detection data"""
    return get_drift_data()

# ============= Leaderboard Endpoints =============

@app.get("/leaderboard")
def get_leaderboard_data():
    """Get gamified leaderboard data"""
    return get_leaderboard()

# ============= Security Data Endpoints =============

@app.get("/security/data")
def get_security_comprehensive():
    """Get comprehensive security data (keys, scores, compliance, recommendations)"""
    return get_security_data()

# Overview endpoint
@app.get("/overview")
def get_overview(use_agent: bool = Query(False, description="Enable AI-driven insights via AWS Strands Agent")):
    overview_data = overview.get_all_overview_data()
    
    if use_agent and agent_client.is_configured():
        # Process through agent
        prompt = agent_logic.format_overview_prompt(overview_data)
        agent_response = agent_client.invoke_agent(prompt)
        processed_response = agent_logic.process_agent_response(agent_response, "overview")
        
        return {
            "data": overview_data,
            "agent_insights": processed_response
        }
    
    return {"data": overview_data}


# Security endpoints
@app.get("/security")
def get_security(use_agent: bool = Query(False, description="Enable AI-driven insights via AWS Strands Agent")):
    security_data = security.get_all_findings()
    findings = security_data.get("findings", [])
    
    if use_agent and agent_client.is_configured():
        # Process through agent
        prompt = agent_logic.format_security_prompt(findings)
        agent_response = agent_client.invoke_agent(prompt)
        processed_response = agent_logic.process_agent_response(agent_response, "security")
        
        return {
            **security_data,
            "agent_insights": processed_response
        }
    
    return security_data

@app.get("/security/{finding_id}")
def get_security_finding(finding_id: str):
    finding = security.get_finding_by_id(finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Security finding not found")
    return finding

@app.post("/security/update")
def update_security_finding(finding_id: str, updates: Dict[str, Any]):
    finding = security.update_finding(finding_id, updates)
    if not finding:
        raise HTTPException(status_code=404, detail="Security finding not found")
    return {"success": True, "finding": finding}

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
