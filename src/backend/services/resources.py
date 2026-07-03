from typing import List, Dict, Any
from connections.db import get_resource_from_db
from aws.ec2 import list_ec2_instances
from aws.s3 import list_s3_buckets
from aws.dynamodb import list_dynamodb_tables
from connections.gcp import list_cloud_storage


running_resources=0
idle_resources=0
async def get_all_resources(force: bool = False):
    """
    Fetch live AWS resources. Pass force=True to bypass the agent cooldown
    (forces fresh metric/config fetch + agent re-run on every resource).
    """
    print(f"Fetching all resources from AWS... (force={force})")
    ec2_resources = await list_ec2_instances(force=force)
    s3_resources = await list_s3_buckets(force=force)
    dynamo_resources = await list_dynamodb_tables(force=force)
    resources = ec2_resources + s3_resources + dynamo_resources

    for res in resources:
        if res.get("status") == "running":
            global running_resources
            running_resources += 1
        else:
            global idle_resources
            idle_resources += 1

        # Frontend renders `resource.last_activity` via new Date(...) — alias
        # from whichever timestamp we actually have on the resource so it
        # doesn't render "Invalid Date". last_agent_run is set on every build
        # / re-run; creation_date is a fallback for resources that never ran
        # the agent for some reason.
        if not res.get("last_activity"):
            res["last_activity"] = (
                res.get("last_agent_run")
                or res.get("metadata", {}).get("creation_date")
                or res.get("creation_date")
            )

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

