from typing import Dict, Any, List, Tuple

BLOCKED_OPERATIONS = {
    "delete_table",
    "terminate_instance",
    "delete_bucket",
    "delete_bucket_policy",
    "delete_db_instance",
    "remove_role_from_instance_profile",
    "delete_role",
    "detach_role_policy",
    "delete_policy",
    "put_role_policy",
    "create_role",
    "attach_role_policy",
    "put_user_policy",
}

ALLOWED_BOTO3_OPERATIONS = {
    "ec2": {
        "stop_instances",
        "start_instances",
        "modify_instance_attribute",
        "monitor_instances",
        "create_tags",
    },
    "s3": {
        "put_public_access_block",
        "put_bucket_acl",
        "put_bucket_encryption",
        "put_bucket_versioning",
        "put_bucket_lifecycle_configuration",
    },
    "dynamodb": {
        "update_continuous_backups",
        "update_table",
        "tag_resource",
    },
    "autoscaling": {
        "create_auto_scaling_group",
    },
}


def validate_action(action_name: str) -> Tuple[bool, str]:
    if action_name in BLOCKED_OPERATIONS:
        return False, f"Action '{action_name}' is blocked: destructive or dangerous operation"
    return True, "ok"


def validate_boto3_step(step: Dict[str, Any]) -> Tuple[bool, str]:
    service = step.get("service", "")
    operation = step.get("operation", "")

    if service not in ALLOWED_BOTO3_OPERATIONS:
        return False, f"Service '{service}' is not in the allowed list"

    if operation not in ALLOWED_BOTO3_OPERATIONS[service]:
        return False, f"Operation '{service}.{operation}' is not whitelisted"

    return True, "ok"


def validate_recommendation(recommendation: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors = []

    boto3_seq = recommendation.get("boto3_sequence", [])
    if not boto3_seq:
        errors.append("No boto3_sequence found in recommendation")
        return False, errors

    for i, step in enumerate(boto3_seq):
        ok, msg = validate_boto3_step(step)
        if not ok:
            errors.append(f"Step {i}: {msg}")

    return len(errors) == 0, errors
