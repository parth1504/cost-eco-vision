# Mock data for Incident Coordinator

mock_incident_timeline = [
    {
        "id": "event-1",
        "timestamp": "2024-01-15T09:13:00Z",
        "type": "Alert",
        "source": "AWS S3",
        "message": "Public access detected: Bucket 'backup-storage-0189' allows READ permissions to AllUsers.",
        "severity": "Critical"
    },
    {
        "id": "event-2",
        "timestamp": "2024-01-15T09:14:00Z",
        "type": "PolicyAnalysis",
        "source": "IAM Analyzer",
        "message": "Bucket policy review confirmed anonymous READ access via ACL and missing Block Public Access settings.",
        "severity": "High"
    },
    {
        "id": "event-3",
        "timestamp": "2024-01-15T09:15:00Z",
        "type": "Escalation",
        "source": "Unified Efficiency Agent",
        "message": "Exposure risk escalated to CRITICAL. Immediate remediation recommended: Block Public Access, remove 'AllUsers' ACL, enable encryption.",
        "severity": "Critical"
    }
]


mock_root_cause_analysis = {
    "primaryCause": "Misconfigured access control policy leading to unintended resource exposure",
    "contributingFactors": [
        "Lack of automated configuration checks",
        "Missing preventive guardrail policies",
        "Insufficient visibility into recent configuration changes"
    ],
    "immediateActions": [
        "Revoke unintended access permissions",
        "Apply corrective configuration updates",
        "Enable stricter policy enforcement",
        "Trigger organization-wide configuration audit"
    ],
    "confidence": 92
}


mock_mitigation_checklist = [
    {
        "id": "1",
        "task": "Validate incident details and confirm severity",
        "completed": False
    },
    {
        "id": "2",
        "task": "Identify impacted resources and users",
        "completed": False
    },
    {
        "id": "3",
        "task": "Apply containment actions to prevent further impact",
        "completed": False
    },
    {
        "id": "4",
        "task": "Review and update relevant security or access policies",
        "completed": False
    },
    {
        "id": "5",
        "task": "Notify key stakeholders and incident response team",
        "completed": False
    },
    {
        "id": "6",
        "task": "Document root cause, analysis, and remediation steps",
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
