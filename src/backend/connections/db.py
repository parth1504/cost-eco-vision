from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from decimal import Decimal
import logging

from connections.aws import get_client
load_dotenv()

# --- DynamoDB Setup ---
dynamodb =  boto3.resource("dynamodb")
# DynamoDB table references
recommendations_table = dynamodb.Table("Recommendations")
alerts_table = dynamodb.Table("Alerts")
incidents_table = dynamodb.Table("Incidents")
security_triage_table = dynamodb.Table("SecurityTriage")
descriptions_table = dynamodb.Table("Descriptions")

# Set up logging
logger = logging.getLogger("db")
logger.setLevel(logging.INFO)

def convert_floats(obj):
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: convert_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_floats(v) for v in obj]
    return obj


def save_resource_in_db(resource_id, resource_type, resource_data):
    """Save full resource metadata with initial state."""
    item = {
        "resource_id": resource_id,
        "resource_type": resource_type,
        "is_optimized": False,
        "status": resource_data.get("status"),
        "monthly_cost": resource_data.get("monthly_cost"),
        "utilization": resource_data.get("utilization"),
        "provider": resource_data.get("provider"),
        "region": resource_data.get("region"),
        "recommendations": resource_data.get("recommendations"),
        "last_checked_time": datetime.utcnow().isoformat(),
        "is_optimized": resource_data.get("is_optimized"),
        "last_agent_run": resource_data.get("last_agent_run"),
        "config": resource_data.get("config"),
        "metrics": resource_data.get("metrics"),
        "name": resource_data.get("name"),
        


    }

    item = convert_floats(item)
    recommendations_table.put_item(Item=item)

    return item


# --- Get a recommendation for resource ---
def get_resource_from_db(resource_id, resource_type):
    try:
        response = recommendations_table.get_item(
            Key={
                "resource_id": resource_id,
                "resource_type": resource_type
            }
        )
        return response.get("Item")
    except ClientError as e:
        # Table doesn't exist yet — treat as cache miss instead of crashing the API.
        # Run `python -m scripts.setup_dynamodb` to create it.
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            print("[db] Recommendations table missing — run scripts/setup_dynamodb.py")
            return None
        raise


# --- Update recommendation status ---
def update_resource_status(resource_id, resource_type, new_status):
    response = recommendations_table.update_item(
        Key={
            "resource_id": resource_id,
            "resource_type": resource_type
        },
        UpdateExpression="SET #s = :val",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":val": new_status},
        ReturnValues="UPDATED_NEW"
    )
    return response


# =============================================================================
# Alerts table
# =============================================================================

def upsert_alert(alert: dict):
    """Persist an alert (idempotent — same alert_id overwrites)."""
    item = convert_floats({**alert, "last_seen_time": datetime.utcnow().isoformat()})
    try:
        alerts_table.put_item(Item=item)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            print("[db] Alerts table missing — run scripts/setup_dynamodb.py")
            return None
        raise
    return item


def get_alerts_for_incident(incident_id: str):
    """Use the GSI to fetch all alerts that belong to a given incident."""
    try:
        response = alerts_table.query(
            IndexName="incident_id-index",
            KeyConditionExpression="incident_id = :iid",
            ExpressionAttributeValues={":iid": incident_id},
        )
        return response.get("Items", [])
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return []
        raise


def set_alert_incident(alert_id: str, incident_id: str):
    """Tag an alert with its incident membership."""
    try:
        alerts_table.update_item(
            Key={"alert_id": alert_id},
            UpdateExpression="SET incident_id = :iid",
            ExpressionAttributeValues={":iid": incident_id},
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return
        raise


# =============================================================================
# Incidents table
# =============================================================================

def upsert_incident(incident: dict):
    """Persist or update an incident row."""
    item = convert_floats({**incident, "updated_at": datetime.utcnow().isoformat()})
    try:
        incidents_table.put_item(Item=item)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            print("[db] Incidents table missing — run scripts/setup_dynamodb.py")
            return None
        raise
    return item


def get_incident(incident_id: str):
    try:
        response = incidents_table.get_item(Key={"incident_id": incident_id})
        return response.get("Item")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return None
        raise


def list_incidents():
    """Scan all incidents (fine for small N; switch to a status-GSI if it grows)."""
    try:
        response = incidents_table.scan()
        return response.get("Items", [])
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return []
        raise


# =============================================================================
# Security triage cache
# =============================================================================

def upsert_security_triage(finding_id: str, triage: dict):
    """Cache LLM triage output for a security finding."""
    item = convert_floats({
        "finding_id": finding_id,
        **triage,
        "cached_at": datetime.utcnow().isoformat(),
    })
    try:
        security_triage_table.put_item(Item=item)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            print("[db] SecurityTriage table missing — run scripts/setup_dynamodb.py")
            return None
        raise
    return item


def get_security_triage(finding_id: str):
    try:
        response = security_triage_table.get_item(Key={"finding_id": finding_id})
        return response.get("Item")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return None
        raise


def list_security_triage():
    try:
        response = security_triage_table.scan()
        return response.get("Items", [])
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return []
        raise


# =============================================================================
# Description cache (rule_id → static text or LLM-generated text)
# =============================================================================

def get_description_from_cache(cache_key: str):
    try:
        response = descriptions_table.get_item(Key={"cache_key": cache_key})
        item = response.get("Item")
        return item.get("text") if item else None
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return None
        raise


def upsert_description_in_cache(cache_key: str, text: str):
    try:
        descriptions_table.put_item(Item={
            "cache_key": cache_key,
            "text": text,
            "cached_at": datetime.utcnow().isoformat(),
        })
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            print("[db] Descriptions table missing — run scripts/setup_dynamodb.py")
            return
        raise


# --- Cooldown Check ---
def is_in_cooldown(item):
    """Check if the resource is still within cooldown period."""
    if not item or "last_checked_time" not in item:
        return False

    last_time = datetime.fromisoformat(item["last_checked_time"])
    cooldown = timedelta(seconds=item.get("cooldown_seconds", 86400))

    return datetime.utcnow() < last_time + cooldown
