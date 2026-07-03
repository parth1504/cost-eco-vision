from typing import Dict, Any, Optional, Callable
from actions.ec2_actions import ACTION_REGISTRY as EC2_ACTIONS
from actions.s3_actions import ACTION_REGISTRY as S3_ACTIONS
from actions.dynamodb_actions import ACTION_REGISTRY as DYNAMODB_ACTIONS


SAFE_ACTION_REGISTRY: Dict[str, Callable] = {}
SAFE_ACTION_REGISTRY.update(EC2_ACTIONS)
SAFE_ACTION_REGISTRY.update(S3_ACTIONS)
SAFE_ACTION_REGISTRY.update(DYNAMODB_ACTIONS)

DANGEROUS_ACTIONS = {
    "terminate_instance",
    "delete_table",
    "delete_bucket_policy",
}

for name in DANGEROUS_ACTIONS:
    SAFE_ACTION_REGISTRY.pop(name, None)

BOTO3_TO_ACTION_MAP = {
    "ec2.stop_instances": "stop_instance",
    "ec2.start_instances": "start_instance",
    "ec2.modify_instance_attribute": "change_instance_type",
    "ec2.monitor_instances": "enable_detailed_monitoring",
    "s3.put_public_access_block": "block_public_access",
    "s3.put_bucket_acl": "remove_public_acl",
    "s3.put_bucket_encryption": "enable_bucket_encryption",
    "s3.put_bucket_versioning": "enable_versioning",
    "s3.put_bucket_lifecycle_configuration": "lifecycle_transition_to_glacier",
    "dynamodb.update_continuous_backups": "enable_point_in_time_recovery",
    "dynamodb.update_table": "update_read_write_capacity",
    "dynamodb.tag_resource": "tag_table",
}


def lookup_safe_action(action_name: str) -> Optional[Callable]:
    return SAFE_ACTION_REGISTRY.get(action_name)


def map_boto3_to_action(service: str, operation: str) -> Optional[str]:
    key = f"{service}.{operation}"
    return BOTO3_TO_ACTION_MAP.get(key)


def list_available_actions():
    return list(SAFE_ACTION_REGISTRY.keys())
