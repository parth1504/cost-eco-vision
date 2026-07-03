from typing import Dict, Any, List
from datetime import datetime
import logging

from connections.aws import get_client
from .validator import validate_boto3_step
from .mapper import map_boto3_to_action, lookup_safe_action

logger = logging.getLogger("actions_executor")


def execute_boto3_sequence(boto3_sequence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []

    for i, step in enumerate(boto3_sequence):
        service = step.get("service", "")
        operation = step.get("operation", "")
        params = step.get("params", {})

        ok, msg = validate_boto3_step(step)
        if not ok:
            results.append({
                "step": i,
                "status": "blocked",
                "operation": f"{service}.{operation}",
                "reason": msg,
            })
            continue

        try:
            client = get_client(service)
            fn = getattr(client, operation)
            response = fn(**params)

            results.append({
                "step": i,
                "status": "success",
                "operation": f"{service}.{operation}",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            })
        except Exception as e:
            logger.error(f"Step {i} failed: {service}.{operation} — {e}")
            results.append({
                "step": i,
                "status": "error",
                "operation": f"{service}.{operation}",
                "error": str(e),
            })

    return results


def execute_single_action(action_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    fn = lookup_safe_action(action_name)
    if fn is None:
        return {
            "status": "blocked",
            "reason": f"Action '{action_name}' not in safe registry",
        }

    try:
        client_name = _infer_client(action_name)
        client = get_client(client_name) if client_name else None

        if client:
            result = fn(**params, **{f"{client_name}_client": client})
        else:
            result = fn(**params)

        return {
            "status": result.get("status", "success"),
            "message": result.get("message", ""),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.error(f"Action '{action_name}' failed: {e}")
        return {"status": "error", "error": str(e)}


def _infer_client(action_name: str) -> str:
    if any(k in action_name for k in ("instance", "monitoring", "scaling")):
        return "ec2"
    if any(k in action_name for k in ("bucket", "public_access", "encryption", "versioning", "lifecycle", "acl")):
        return "s3"
    if any(k in action_name for k in ("table", "pitr", "capacity", "point_in_time", "tag_table")):
        return "dynamodb"
    return ""
