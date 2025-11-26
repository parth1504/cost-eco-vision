# Mock data for Infrastructure Drift Detection

mock_drift_detections = [
    {
        "id": "drift-1",
        "resource": "prod-web-server",
        "resourceType": "EC2",
        "driftType": "Configuration",
        "severity": "High",
        "actualValue": "t3.large",
        "expectedValue": "t3.medium",
        "lastSync": "2024-01-14T10:30:00Z"
    },
    {
        "id": "drift-2",
        "resource": "database-security-group",
        "resourceType": "Security Group",
        "driftType": "Security",
        "severity": "Critical",
        "actualValue": "0.0.0.0/0 allowed on port 3306",
        "expectedValue": "10.0.0.0/8 only",
        "lastSync": "2024-01-14T09:15:00Z"
    },
    {
        "id": "drift-3",
        "resource": "s3-backup-bucket",
        "resourceType": "S3",
        "driftType": "Compliance",
        "severity": "Medium",
        "actualValue": "Versioning disabled",
        "expectedValue": "Versioning enabled",
        "lastSync": "2024-01-14T11:00:00Z"
    },
    {
        "id": "drift-4",
        "resource": "lambda-processor",
        "resourceType": "Lambda",
        "driftType": "Configuration",
        "severity": "High",
        "actualValue": "Memory: 512MB",
        "expectedValue": "Memory: 256MB",
        "lastSync": "2024-01-14T08:45:00Z"
    }
]

def get_drift_data():
    """Return all drift detection data"""
    return {
        "drifts": mock_drift_detections
    }
