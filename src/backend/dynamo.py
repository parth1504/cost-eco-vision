import os
import boto3
from datetime import datetime, timedelta
from dotenv import load_dotenv
from decimal import Decimal
load_dotenv()

# --- DynamoDB Setup ---
dynamodb = boto3.resource(
    "dynamodb",
    region_name=os.getenv("AWS_REGION"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)

# DynamoDB table reference
recommendations_table = dynamodb.Table("Recommendations")

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
        "cooldown_seconds": 86400,
        "is_optimized": resource_data.get("is_optimized"),
    }

    item = convert_floats(item)
    recommendations_table.put_item(Item=item)

    return item



# --- Get a recommendation for resource ---
def get_resource_from_db(resource_id, resource_type):
    response = recommendations_table.get_item(
        Key={
            "resource_id": resource_id,
            "resource_type": resource_type
        }
    )
    return response.get("Item")


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


# --- Cooldown Check ---
def is_in_cooldown(item):
    """Check if the resource is still within cooldown period."""
    if not item or "last_checked_time" not in item:
        return False

    last_time = datetime.fromisoformat(item["last_checked_time"])
    cooldown = timedelta(seconds=item.get("cooldown_seconds", 86400))

    return datetime.utcnow() < last_time + cooldown
