from typing import List, Dict, Any

mock_security_findings: List[Dict[str, Any]] = [
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
        "title": "Unrotated IAM Access Keys",
        "severity": "High",
        "description": "IAM access keys have not been rotated in over 90 days",
        "resource": "legacy-api-key",
        "compliance": ["SOC 2", "ISO 27001"],
        "remediation": "Rotate IAM access keys and enable automatic rotation",
        "estimatedCost": 0,
        "status": "Open"
    }
]

def get_all_findings():
    return {
        "findings": mock_security_findings,
        "summary": {
            "total": len(mock_security_findings),
            "critical": len([f for f in mock_security_findings if f["severity"] == "Critical"]),
            "high": len([f for f in mock_security_findings if f["severity"] == "High"]),
            "medium": len([f for f in mock_security_findings if f["severity"] == "Medium"]),
            "open": len([f for f in mock_security_findings if f["status"] == "Open"])
        }
    }

def get_finding_by_id(finding_id: str):
    return next((finding for finding in mock_security_findings if finding["id"] == finding_id), None)

def update_finding(finding_id: str, updates: Dict[str, Any]):
    for finding in mock_security_findings:
        if finding["id"] == finding_id:
            finding.update(updates)
            return finding
    return None
