from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import alerts
import resources
import security
import optimization
import notifications

app = FastAPI(title="Cloud Management API")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Alerts endpoints
@app.get("/alerts")
def get_alerts():
    return alerts.get_all_alerts()

@app.get("/alerts/{alert_id}")
def get_alert(alert_id: str):
    alert = alerts.get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert

@app.put("/alerts/{alert_id}")
def update_alert(alert_id: str, updates: Dict[str, Any]):
    alert = alerts.update_alert(alert_id, updates)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert

@app.delete("/alerts/{alert_id}")
def delete_alert(alert_id: str):
    alert = alerts.delete_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert

# Resources endpoints
@app.get("/resources")
def get_resources():
    return resources.get_all_resources()

@app.get("/resources/{resource_id}")
def get_resource(resource_id: str):
    resource = resources.get_resource_by_id(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource

@app.put("/resources/{resource_id}/optimize")
def optimize_resource(resource_id: str):
    resource = resources.get_resource_by_id(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    # Apply optimization - reduce cost by 30%
    updated_resource = resources.update_resource(resource_id, {
        "status": "Optimized",
        "monthly_cost": round(resource["monthly_cost"] * 0.7, 2)
    })
    return updated_resource

# Security endpoints
@app.get("/security")
def get_security():
    return security.get_all_findings()

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
def get_optimization():
    return optimization.get_optimization_data()

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
