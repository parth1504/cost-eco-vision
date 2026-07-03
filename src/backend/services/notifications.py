from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import json

# Mock notification settings storage
notification_settings_db: Dict[str, Any] = {}

def get_notification_settings(email: str) -> Optional[Dict[str, Any]]:
    """Get notification settings for a user email"""
    return notification_settings_db.get(email)

def update_notification_settings(email: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    """Update notification settings for a user"""
    existing = notification_settings_db.get(email, {})
    
    # Update settings
    existing.update({
        "user_email": email,
        "email_enabled": settings.get("email_enabled", False),
        "slack_enabled": settings.get("slack_enabled", False),
        "critical_alerts_email": settings.get("critical_alerts_email", True),
        "monthly_reports_enabled": settings.get("monthly_reports_enabled", False),
        "critical_alerts_slack": settings.get("critical_alerts_slack", False),
        "weekly_summary_slack": settings.get("weekly_summary_slack", False),
        "slack_webhook_url": settings.get("slack_webhook_url"),
        "updated_at": datetime.now().isoformat()
    })
    
    # Set next report date if monthly reports are enabled
    if settings.get("monthly_reports_enabled") and not existing.get("next_report_date"):
        existing["next_report_date"] = (datetime.now() + timedelta(days=30)).isoformat()
    
    notification_settings_db[email] = existing
    return existing

def generate_monthly_report() -> Dict[str, Any]:
    """Generate comprehensive monthly report data"""
    return {
        "report_period": {
            "start": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
            "end": datetime.now().strftime("%Y-%m-%d")
        },
        "infrastructure_overview": {
            "total_resources": 45,
            "active_servers": 12,
            "total_instances": 23,
            "avg_cpu_utilization": 67,
            "avg_memory_utilization": 72,
            "avg_storage_utilization": 58,
            "idle_resources": 8,
            "idle_cost_impact": "$2,340/month"
        },
        "cost_optimization": {
            "underutilized_instances": 8,
            "potential_monthly_savings": "$4,567",
            "current_month_spend": "$18,234",
            "last_month_spend": "$19,890",
            "spend_change_percent": -8.3,
            "optimization_recommendations": 5
        },
        "alert_analytics": {
            "total_alerts": 47,
            "alerts_resolved": 32,
            "alerts_dismissed": 8,
            "alerts_active": 7,
            "top_issues": [
                "High CPU utilization on web-server-1",
                "Unused EBS volumes in us-east-1",
                "Security group allows unrestricted access"
            ]
        },
        "security_health": {
            "vulnerabilities_detected": 12,
            "vulnerabilities_resolved": 8,
            "compliance_drift_resources": 3,
            "open_security_findings": 4
        },
        "ai_recommendations": [
            "Right-size EC2 instances in dev environment to save $1,200/month",
            "Enable auto-scaling for production workloads to optimize costs",
            "Archive S3 data older than 90 days to Glacier for 40% storage savings"
        ]
    }

def send_email_report(email: str, report_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send email report (mock implementation)
    In production, integrate with AWS SES or SendGrid
    """
    print(f"📧 Sending monthly report to {email}")
    print(f"Report data: {json.dumps(report_data, indent=2)}")
    
    # Update last sent date
    if email in notification_settings_db:
        notification_settings_db[email]["last_email_sent"] = datetime.now().isoformat()
        notification_settings_db[email]["next_report_date"] = (datetime.now() + timedelta(days=30)).isoformat()
    
    return {
        "status": "sent",
        "email": email,
        "timestamp": datetime.now().isoformat(),
        "report_summary": {
            "total_resources": report_data["infrastructure_overview"]["total_resources"],
            "potential_savings": report_data["cost_optimization"]["potential_monthly_savings"],
            "active_alerts": report_data["alert_analytics"]["alerts_active"]
        }
    }

def send_slack_notification(webhook_url: str, message: Dict[str, Any], notification_type: str) -> Dict[str, Any]:
    """
    Send Slack notification (mock implementation)
    In production, use requests.post() with webhook_url
    """
    print(f"💬 Sending Slack {notification_type} notification")
    print(f"Webhook: {webhook_url}")
    print(f"Message: {json.dumps(message, indent=2)}")
    
    return {
        "status": "sent",
        "webhook_url": webhook_url,
        "notification_type": notification_type,
        "timestamp": datetime.now().isoformat()
    }

def format_critical_alert_slack(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Format critical alert for Slack"""
    return {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚨 Critical Alert: {alert.get('title', 'Unknown Alert')}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{alert.get('severity', 'Unknown')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Timestamp:*\n{alert.get('timestamp', datetime.now().isoformat())}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Source:*\n{alert.get('source', 'Unknown')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Status:*\n{alert.get('status', 'Active')}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Message:*\n{alert.get('message', 'No details available')}"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Details"
                        },
                        "url": f"http://localhost:5173/alerts?id={alert.get('id', '')}"
                    }
                ]
            }
        ]
    }

def format_weekly_summary_slack() -> Dict[str, Any]:
    """Format weekly summary for Slack"""
    return {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📊 Weekly Cloud Infrastructure Summary"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": "*Alerts This Week:*\n12 total (8 resolved)"
                    },
                    {
                        "type": "mrkdwn",
                        "text": "*Cost Trend:*\n↓ 5.2% vs last week"
                    },
                    {
                        "type": "mrkdwn",
                        "text": "*Optimization Opportunities:*\n5 recommended actions"
                    },
                    {
                        "type": "mrkdwn",
                        "text": "*Security Findings:*\n3 new, 4 resolved"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Top Recommendations:*\n• Right-size EC2 instances in dev ($1.2K/mo savings)\n• Enable auto-scaling for production\n• Archive old S3 data to Glacier"
                }
            }
        ]
    }
