from typing import List, Dict, Any
from dynamo import get_resource_from_db
from aws import list_ec2_instances, list_s3_buckets, list_dynamodb_tables

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
running_resources=0
idle_resources=0
async def get_all_resources():
    # return mock_resources
    ec2_resources= await list_ec2_instances()
    s3_resources = await list_s3_buckets()
    dynamo_resources=await list_dynamodb_tables()  
    resources=ec2_resources + s3_resources + dynamo_resources
    for res in resources:
        if res['status']=='running':
            global running_resources
            running_resources+=1
        else:
            global idle_resources
            idle_resources+=1
    return resources

def get_resource_by_id(resource_id: str,resource_type: str):
    return get_resource_from_db(resource_id)

def get_running_resource() -> int:
    return running_resources

def get_idle_resource() -> int:
    return idle_resources

def update_resource(resource_id: str, updates: Dict[str, Any]):
    for resource in mock_resources:
        if resource["id"] == resource_id:
            resource.update(updates)
            return resource
    return None

