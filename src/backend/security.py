# Mock data for Security features

mock_security_findings = [
    {
        "id": "sec-1",
        "title": "RDS Instance Publicly Accessible",
        "severity": "Critical",
        "description": "Database instance can be accessed from the internet",
        "resource": "prod-db",
        "compliance": ["SOC 2", "ISO 27001", "GDPR"],
        "remediation": "Remove public access and configure VPC security groups",
        "status": "Open"
    },
    {
        "id": "sec-2",
        "title": "S3 Bucket Not Encrypted",
        "severity": "High",
        "description": "Sensitive data stored without encryption at rest",
        "resource": "backup-bucket",
        "compliance": ["SOC 2", "HIPAA"],
        "remediation": "Enable AES-256 server-side encryption",
        "estimatedCost": 12,
        "status": "Open"
    },
    {
        "id": "sec-3",
        "title": "Overly Permissive Security Group",
        "severity": "Medium",
        "description": "Security group allows inbound traffic from 0.0.0.0/0",
        "resource": "web-sg",
        "compliance": ["CIS Benchmark"],
        "remediation": "Restrict inbound rules to specific IP ranges",
        "status": "In Progress"
    },
    {
        "id": "sec-4",
        "title": "IAM User with Unnecessary Permissions",
        "severity": "High",
        "description": "User has AdministratorAccess but only needs read permissions",
        "resource": "dev-user-1",
        "compliance": ["SOC 2", "PCI DSS"],
        "remediation": "Apply principle of least privilege",
        "status": "Open"
    },
    {
        "id": "sec-5",
        "title": "Unpatched EC2 Instance",
        "severity": "Critical",
        "description": "Instance running with 15 critical security patches pending",
        "resource": "legacy-app-server",
        "compliance": ["CIS Benchmark"],
        "remediation": "Apply latest security patches",
        "estimatedCost": 0,
        "status": "Open"
    }
]

mock_security_keys = [
    {
        "id": "key-1",
        "name": "AWS API Key - Production",
        "type": "API Key",
        "lastUsed": "2024-01-10T14:30:00Z",
        "expiresIn": 15,
        "status": "Active"
    },
    {
        "id": "key-2",
        "name": "GitHub Deploy Key",
        "type": "SSH Key",
        "lastUsed": "2023-12-20T08:15:00Z",
        "expiresIn": -5,
        "status": "Expired"
    },
    {
        "id": "key-3",
        "name": "Service Account - Monitoring",
        "type": "Service Account",
        "lastUsed": "2023-10-15T12:00:00Z",
        "expiresIn": 90,
        "status": "Unused"
    },
    {
        "id": "key-4",
        "name": "SSL Certificate",
        "type": "Certificate",
        "lastUsed": "2024-01-15T10:00:00Z",
        "expiresIn": 45,
        "status": "Active"
    }
]

mock_security_score = {
    "current": 78,
    "previous": 75,
    "trend": [
        {"week": "Week 1", "score": 72},
        {"week": "Week 2", "score": 74},
        {"week": "Week 3", "score": 71},
        {"week": "Week 4", "score": 76},
        {"week": "Week 5", "score": 75},
        {"week": "Week 6", "score": 78}
    ],
    "weeklyData": [
        {"day": "Mon", "score": 75},
        {"day": "Tue", "score": 76},
        {"day": "Wed", "score": 74},
        {"day": "Thu", "score": 77},
        {"day": "Fri", "score": 78},
        {"day": "Sat", "score": 78},
        {"day": "Sun", "score": 78}
    ]
}

mock_compliance_coverage = {
    "soc2": 85,
    "iso27001": 78,
    "gdpr": 92,
    "hipaa": 68,
    "cisBenchmark": 81
}

mock_security_recommendations = [
    {
        "id": "rec-1",
        "title": "Enable MFA for all IAM users",
        "priority": "High",
        "effort": "Low",
        "impact": "Prevents unauthorized access"
    },
    {
        "id": "rec-2",
        "title": "Rotate expired security keys",
        "priority": "Critical",
        "effort": "Medium",
        "impact": "Eliminates security vulnerabilities"
    },
    {
        "id": "rec-3",
        "title": "Enable CloudTrail logging",
        "priority": "Medium",
        "effort": "Low",
        "impact": "Improves audit capabilities"
    }
]

def get_all_findings():
    """Return all security findings with summary"""
    summary = {
        "critical": sum(1 for f in mock_security_findings if f["severity"] == "Critical"),
        "high": sum(1 for f in mock_security_findings if f["severity"] == "High"),
        "medium": sum(1 for f in mock_security_findings if f["severity"] == "Medium"),
        "low": sum(1 for f in mock_security_findings if f["severity"] == "Low"),
        "open": sum(1 for f in mock_security_findings if f["status"] == "Open"),
        "in_progress": sum(1 for f in mock_security_findings if f["status"] == "In Progress"),
        "fixed": sum(1 for f in mock_security_findings if f["status"] == "Fixed")
    }
    
    return {
        "findings": mock_security_findings,
        "summary": summary
    }

def get_finding_by_id(finding_id: str):
    """Return a specific finding by ID"""
    return next((f for f in mock_security_findings if f["id"] == finding_id), None)

def update_finding(finding_id: str, updates: dict):
    """Update a finding with new data"""
    for finding in mock_security_findings:
        if finding["id"] == finding_id:
            finding.update(updates)
            return finding
    return None

def get_security_data():
    """Return comprehensive security data including keys, scores, and compliance"""
    return {
        "keys": mock_security_keys,
        "score": mock_security_score,
        "compliance": mock_compliance_coverage,
        "recommendations": mock_security_recommendations
    }
