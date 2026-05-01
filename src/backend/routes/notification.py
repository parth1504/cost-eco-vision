from fastapi import APIRouter
from typing import Dict, Any, Optional
import services.notifications as notifications

from pydantic import BaseModel
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


router = APIRouter(prefix="/notifications", tags=["notifications"])


# ---------------- EMAIL ---------------- #

@router.get("/email")
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


@router.put("/email")
def update_email_settings(email: str, settings: NotificationSettings):
    """Update email notification settings"""
    updated = notifications.update_notification_settings(email, settings.dict())
    return {"status": "success", "settings": updated}


@router.post("/email/send")
def send_email_report(request: SendReportRequest):
    """Manually trigger monthly report email"""
    report_data = notifications.generate_monthly_report()
    result = notifications.send_email_report(request.email, report_data)

    return {
        "status": "success",
        "result": result,
        "report": report_data
    }


# ---------------- SLACK ---------------- #

@router.get("/slack")
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


@router.put("/slack")
def update_slack_settings(email: str, settings: NotificationSettings):
    """Update Slack notification settings"""
    updated = notifications.update_notification_settings(email, settings.dict())
    return {"status": "success", "settings": updated}


@router.post("/slack/send")
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