from connections.aws import get_client

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import logging
from datetime import datetime, timedelta

# Set up logging
logger = logging.getLogger("aws_util")
logger.setLevel(logging.INFO)

# Add a handler to log to a file
file_handler = logging.FileHandler("aws_util.log")
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

aws_clients = {
    "s3": boto3.client("s3"),
    "ec2": boto3.client("ec2"),
    "iam": boto3.client("iam"),
    "acm": boto3.client("acm"),
    "dynamodb": boto3.client("dynamodb"),
}

CLI_TO_BOTO_MAPPINGS = {
    "instance-ids": "InstanceIds",
    "instance-id": "InstanceId",
    "instance-type": "InstanceType",
    "group-id": "GroupId",
    "volume-id": "VolumeId",
    "table-name": "TableName",
    "bucket": "Bucket",
}

cloudwatch = get_client("cloudwatch")
ce_client = boto3.client("ce")

def replace_placeholders(obj, mapping):
    """
    Recursively replace placeholders like {INSTANCE_ID} in strings,
    lists, and nested dictionaries.
    """
    if isinstance(obj, str):
        for key, value in mapping.items():
            obj = obj.replace(f"{{{key}}}", value)
        return obj

    elif isinstance(obj, list):
        return [replace_placeholders(item, mapping) for item in obj]

    elif isinstance(obj, dict):
        return {k: replace_placeholders(v, mapping) for k, v in obj.items()}

    else:
        return obj

async def apply_aws_commands(commands: list):
    """
    Executes boto3_sequence exactly as stored in DynamoDB.
    No placeholder replacement — assumes commands are already fully resolved.
    """

    print(f"Applying {len(commands)} AWS commands")
    results = []

    for cmd in commands:
        service = cmd.get("service")
        operation = cmd.get("operation")
        params = cmd.get("params", {})

        if service not in aws_clients:
            msg = f"Unsupported AWS service '{service}'"
            print(msg)
            results.append({"success": False, "error": msg})
            continue

        client = aws_clients[service]

        if not hasattr(client, operation):
            msg = f"Invalid AWS operation '{operation}'"
            print(msg)
            results.append({"success": False, "error": msg})
            continue

        try:
            print(f"Running AWS: {service}.{operation}({params})")
            
            fn = getattr(client, operation)
            response = fn(**params)

            print(f"Success: {service}.{operation}")

            results.append({
                "success": True,
                "operation": f"{service}.{operation}",
                "response": response
            })

        except ClientError as e:
            msg = str(e)
            print(f"AWS ClientError: {service}.{operation} - {msg}")
            results.append({
                "success": False,
                "operation": f"{service}.{operation}",
                "error": msg
            })

        except Exception as e:
            msg = str(e)
            print(f"Error: {service}.{operation} - {msg}")
            results.append({
                "success": False,
                "operation": f"{service}.{operation}",
                "error": msg
            })

    return results

def get_resource_cost(tag_key, tag_value):
    """
    Universal AWS Cost function for EC2, S3, DynamoDB...
    Uses AWS Cost Explorer with tag-based filtering.
    """
    from datetime import datetime, timedelta

    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=30)

    logger.info(f"Fetching cost for resources with tag {tag_key}:{tag_value}")

    try:
        response = ce_client.get_cost_and_usage(
            TimePeriod={"Start": start_date.isoformat(), "End": end_date.isoformat()},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            Filter={
                "Tags": {
                    "Key": tag_key,
                    "Values": [tag_value]
                }
            }
        )

        results = response.get("ResultsByTime", [])
        if results and results[0]["Total"]:
            cost = float(results[0]["Total"]["UnblendedCost"]["Amount"])
            logger.info(f"Cost fetched successfully: {cost}")
            return cost

    except NoCredentialsError:
        logger.error("AWS credentials not found. Please configure them.")

    except ClientError as e:
        if e.response['Error']['Code'] == 'AccessDeniedException':
            logger.error("Access denied: Ensure Cost Explorer is enabled and permissions are set.")
        else:
            logger.error(f"AWS ClientError: {e}")

    except Exception as e:
        logger.error(f"Cost lookup failed for {tag_key}:{tag_value} → {e}")

    return 0.0


def should_run_agent(last_agent_run: str, threshold_minutes: int = 60,force=False,) -> bool:
    if force:
        return True
    if not last_agent_run:
        return True

    try:
        last_run_time = datetime.fromisoformat(last_agent_run.replace("Z", ""))
        return datetime.utcnow() - last_run_time > timedelta(minutes=threshold_minutes)
    except Exception:
        return True  # fail-safe → recompute

def generate_recommendation_id(resource_id, title):
    return f"{resource_id}:{title.replace(' ', '~')}"

def normalize_tags(tags):
    return {tag["Key"]: tag["Value"] for tag in tags or []}
def execute_boto3_sequence(sequence, clients):

    results = []

    for step in sequence:
        service = step["service"]
        operation = step["operation"]
        params = step["params"]

        client = clients.get(service)

        try:
            func = getattr(client, operation)
            response = func(**params)

            results.append({
                "status": "success",
                "operation": operation
            })

        except Exception as e:
            results.append({
                "status": "failed",
                "operation": operation,
                "error": str(e)
            })

    return results