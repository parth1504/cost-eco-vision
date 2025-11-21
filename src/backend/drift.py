
mock_drift_detections = [
    {
    "id": "drift-ec2-1",
    "resource": "prod-webserver",
    "resourceType": "EC2",
    "driftType": "Configuration",
    "severity": "High",
    "actualValue": "InstanceType: t3.large",
    "expectedValue": "InstanceType: t3.medium",
    "lastSync": "2024-01-14T08:45:00Z"
},

    {
    "id": "drift-s3-1",
    "resource": "backup-storage",
    "resourceType": "S3",
    "driftType": "Security",
    "severity": "Critical",
    "actualValue": "PublicAccess: Allowed, Encryption: Disabled",
    "expectedValue": "PublicAccess: Blocked, Encryption: AES-256",
    "lastSync": "2024-01-14T09:12:00Z"
}

]


def get_drift_data():
    """Return all drift detection data"""
    return {
        "drifts": mock_drift_detections
    }
