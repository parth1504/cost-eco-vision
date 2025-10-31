from typing import List, Dict, Any
from aws import list_ec2_instances

mock_resources: List[Dict[str, Any]] = [
    {
        "id": "i-0123456789",
        "name": "web-server-1",
        "type": "EC2",
        "status": "Running",
        "utilization": 15,
        "monthly_cost": 89.50,
        "region": "us-east-1",
        "recommendations": ["Right-size to t3.small", "Enable detailed monitoring"],
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
        "recommendations": ["Remove public access", "Enable encryption"],
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
        "recommendations": ["Archive old data to Glacier"],
        "last_activity": "2024-01-14T20:15:00Z"
    }
]

def get_all_resources():
    return mock_resources
    resources=list_ec2_instances()
    print(f"Resources fetched: {resources}")
    return resources

def get_resource_by_id(resource_id: str):
    return next((resource for resource in mock_resources if resource["id"] == resource_id), None)

def update_resource(resource_id: str, updates: Dict[str, Any]):
    for resource in mock_resources:
        if resource["id"] == resource_id:
            resource.update(updates)
            return resource
    return None
