from typing import Dict, Any


def stop_instance(instance_id: str, ec2_client) -> Dict[str, Any]:
    """Stops an EC2 instance."""
    try:
        response = ec2_client.stop_instances(InstanceIds=[instance_id])
        return {"status": "success", "message": "Instance stopped", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


def start_instance(instance_id: str, ec2_client) -> Dict[str, Any]:
    """Starts an EC2 instance."""
    try:
        response = ec2_client.start_instances(InstanceIds=[instance_id])
        return {"status": "success", "message": "Instance started", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


def terminate_instance(instance_id: str, ec2_client) -> Dict[str, Any]:
    """Terminates an EC2 instance (destructive)."""
    try:
        response = ec2_client.terminate_instances(InstanceIds=[instance_id])
        return {"status": "success", "message": "Instance terminated", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


def change_instance_type(instance_id: str, new_type: str, ec2_client) -> Dict[str, Any]:
    """Changes EC2 instance type. Instance must be stopped."""
    try:
        response = ec2_client.modify_instance_attribute(
            InstanceId=instance_id,
            InstanceType={"Value": new_type},
        )
        return {"status": "success", "message": "Instance type updated", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


def enable_detailed_monitoring(instance_id: str, ec2_client) -> Dict[str, Any]:
    """Enables 1-minute CloudWatch monitoring."""
    try:
        response = ec2_client.monitor_instances(InstanceIds=[instance_id])
        return {"status": "success", "message": "Detailed monitoring enabled", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


def attach_iam_role(instance_id: str, role_name: str, ec2_client) -> Dict[str, Any]:
    """Attaches IAM role to EC2 instance."""
    try:
        response = ec2_client.associate_iam_instance_profile(
            InstanceId=instance_id,
            IamInstanceProfile={"Name": role_name},
        )
        return {"status": "success", "message": "IAM role attached", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


def create_auto_scaling_group(config: dict, autoscaling_client) -> Dict[str, Any]:
    """Creates an Auto Scaling Group."""
    try:
        response = autoscaling_client.create_auto_scaling_group(**config)
        return {"status": "success", "message": "ASG created", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


def schedule_instance_shutdown(instance_id: str, time: str) -> Dict[str, Any]:
    """
    Mock: Schedule shutdown.
    In production use EventBridge + Lambda.
    """
    return {
        "status": "success",
        "message": f"Mock schedule shutdown for {instance_id} at {time}",
        "data": None,
    }


ACTION_REGISTRY = {
    "stop_instance": stop_instance,
    "start_instance": start_instance,
    "terminate_instance": terminate_instance,
    "change_instance_type": change_instance_type,
    "enable_detailed_monitoring": enable_detailed_monitoring,
    "attach_iam_role": attach_iam_role,
    "create_auto_scaling_group": create_auto_scaling_group,
    "schedule_instance_shutdown": schedule_instance_shutdown,
}