from datetime import datetime
from typing import List, Dict, Any

mock_alerts: List[Dict[str, Any]] = [
    {
        "id": "alert-1",
        "title": "EC2 Instance Running Idle",
        "message": "Instance i-0123456789abcdef has been running with <5% CPU for 7 days",
        "severity": "Warning",
        "source": "Cost",
        "affected_resources": ["i-0123456789abcdef"],
        "status": "active",
        "timestamp": "2025-01-15T10:30:00Z",
    },
    {
        "id": "alert-2",
        "title": "S3 Bucket Publicly Accessible",
        "message": "Bucket prod-data-storage has public read access enabled",
        "severity": "Critical",
        "source": "Security",
        "affected_resources": ["prod-data-storage"],
        "status": "active",
        "timestamp": "2025-01-15T09:15:00Z",
    },
    {
        "id": "alert-3",
        "title": "RDS Database Underutilized",
        "message": "Database prod-mysql-01 running at 15% capacity",
        "severity": "Warning",
        "source": "Cost",
        "affected_resources": ["prod-mysql-01"],
        "status": "active",
        "timestamp": "2025-01-15T08:45:00Z",
    },
]

def get_all_alerts():
    return mock_alerts

def get_alert_by_id(alert_id: str):
    return next((alert for alert in mock_alerts if alert["id"] == alert_id), None)

def update_alert(alert_id: str, updates: Dict[str, Any]):
    for alert in mock_alerts:
        if alert["id"] == alert_id:
            alert.update(updates)
            return alert
    return None

def delete_alert(alert_id: str):
    global mock_alerts
    alert = get_alert_by_id(alert_id)
    if alert:
        mock_alerts = [a for a in mock_alerts if a["id"] != alert_id]
        return alert
    return None
