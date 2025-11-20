# Mock data for Incident Coordinator

mock_incident_timeline = [
    {
        "id": "event-1",
        "timestamp": "2024-01-15T14:30:00Z",
        "type": "Alert",
        "source": "CloudWatch",
        "message": "High CPU utilization detected on web-server-1",
        "severity": "Warning"
    },
    {
        "id": "event-2",
        "timestamp": "2024-01-15T14:32:15Z",
        "type": "Metric",
        "source": "DataDog",
        "message": "Response time increased to 2.4s (normal: 0.8s)",
        "severity": "Warning"
    },
    {
        "id": "event-3",
        "timestamp": "2024-01-15T14:35:00Z",
        "type": "Alert",
        "source": "PagerDuty",
        "message": "Service degradation reported by monitoring",
        "severity": "Critical"
    },
    {
        "id": "event-4",
        "timestamp": "2024-01-15T14:36:30Z",
        "type": "Action",
        "source": "AWS Console",
        "message": "Auto-scaling triggered, launching 2 additional instances",
        "severity": "Info"
    },
    {
        "id": "event-5",
        "timestamp": "2024-01-15T14:40:00Z",
        "type": "Log",
        "source": "Application Logs",
        "message": "Memory leak detected in background worker process",
        "severity": "Critical"
    },
    {
        "id": "event-6",
        "timestamp": "2024-01-15T14:42:00Z",
        "type": "Action",
        "source": "Manual Intervention",
        "message": "Restarted background worker service",
        "severity": "Info"
    },
    {
        "id": "event-7",
        "timestamp": "2024-01-15T14:45:00Z",
        "type": "Metric",
        "source": "CloudWatch",
        "message": "CPU utilization normalized to 45%",
        "severity": "Info"
    }
]

mock_root_cause_analysis = {
    "primaryCause": "Memory leak in background worker process causing resource exhaustion",
    "contributingFactors": [
        "Inefficient database query in batch processing job",
        "Missing connection pool limits",
        "Inadequate monitoring alerts for memory usage"
    ],
    "immediateActions": [
        "Restart affected services",
        "Apply hotfix for memory management",
        "Increase monitoring frequency",
        "Review and optimize database queries"
    ],
    "confidence": 94
}

mock_mitigation_checklist = [
    {
        "id": "1",
        "task": "Identify root cause",
        "completed": False
    },
    {
        "id": "2",
        "task": "Scale affected resources",
        "completed": True
    },
    {
        "id": "3",
        "task": "Update monitoring thresholds",
        "completed": False
    },
    {
        "id": "4",
        "task": "Notify stakeholders",
        "completed": True
    },
    {
        "id": "5",
        "task": "Document incident details",
        "completed": False
    },
    {
        "id": "6",
        "task": "Schedule post-incident review",
        "completed": False
    }
]

def get_incident_data():
    """Return all incident room data"""
    return {
        "timeline": mock_incident_timeline,
        "rootCause": mock_root_cause_analysis,
        "checklist": mock_mitigation_checklist
    }
