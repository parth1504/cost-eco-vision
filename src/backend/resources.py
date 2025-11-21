from typing import List, Dict, Any
from aws import list_ec2_instances,list_dynamodb_tables, list_s3_buckets
from dynamo import get_resource_from_db, save_resource_in_db


running_resources = 0
idle_resources = 0
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

