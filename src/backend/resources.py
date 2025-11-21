from typing import List, Dict, Any

mock_resources: List[Dict[str, Any]] = [
    {
        "id": "i-0123456789",
        "name": "web-server-1",
        "type": "EC2",
        "status": "Running",
        "utilization": 15,
        "monthly_cost": 89.50,
        "region": "us-east-1",
        "provider": "AWS",
        "recommendations": ["Right-size to t3.small", "Enable detailed monitoring"],
        "commands": [
            {"step": 1, "title": "Stop EC2 Instance", "command": "aws ec2 stop-instances --instance-ids i-0123456789"},
            {"step": 2, "title": "Modify Instance Type", "command": "aws ec2 modify-instance-attribute --instance-id i-0123456789 --instance-type t3.small"},
            {"step": 3, "title": "Start EC2 Instance", "command": "aws ec2 start-instances --instance-ids i-0123456789"}
        ],
        "last_activity": "2024-01-15T12:00:00Z"
    },
    {
        "id": "prod-db",
        "name": "Production Database",
        "type": "RDS",
        "status": "Running",
        "utilization": 67,
        "monthly_cost": 234.00,
        "region": "us-east-1",
        "provider": "AWS",
        "recommendations": ["Remove public access", "Enable encryption"],
        "commands": [
            {"step": 1, "title": "Disable Public Access", "command": "aws rds modify-db-instance --db-instance-identifier prod-db --no-publicly-accessible"},
            {"step": 2, "title": "Enable Encryption", "command": "aws rds modify-db-instance --db-instance-identifier prod-db --storage-encrypted"}
        ],
        "last_activity": "2024-01-15T11:30:00Z"
    },
    {
        "id": "backup-bucket",
        "name": "Backup Storage",
        "type": "S3",
        "status": "Optimized",
        "utilization": 0,
        "monthly_cost": 45.20,
        "region": "us-east-1",
        "provider": "GCP",
        "recommendations": ["Archive old data to Glacier"],
        "commands": [
            {"step": 1, "title": "Create Lifecycle Policy", "command": "gsutil lifecycle set archive-policy.json gs://backup-bucket"},
            {"step": 2, "title": "Move Old Data", "command": "gsutil -m mv gs://backup-bucket/old/* gs://backup-bucket/archive/"}
        ],
        "last_activity": "2024-01-14T20:15:00Z"
    }
]

def get_all_resources():
    return mock_resources

def get_resource_by_id(resource_id: str):
    return next((resource for resource in mock_resources if resource["id"] == resource_id), None)

def update_resource(resource_id: str, updates: Dict[str, Any]):
    for resource in mock_resources:
        if resource["id"] == resource_id:
            resource.update(updates)
            return resource
    return None
