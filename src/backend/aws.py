import os
import boto3
from dotenv import load_dotenv
from datetime import datetime, timedelta
from recommendations import generate_recommendation

# Load credentials from .env
load_dotenv()

# Initialize AWS session
aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
aws_region = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")

session = boto3.Session(
    aws_access_key_id=aws_access_key,
    aws_secret_access_key=aws_secret_key,
    region_name=aws_region
)

# ---------- EC2 ----------
async def list_ec2_instances():
    """Fetch all EC2 instances and enrich with recommendations."""
    try:
        ec2 = session.client("ec2")
        response = ec2.describe_instances()
        instances = []
        recommendations=["Right-size to t3.small", "Enable detailed monitoring"]

        for reservation in response.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                instance_id = instance.get("InstanceId")
                state = instance.get("State", {}).get("Name", "unknown")
                instance_type = instance.get("InstanceType", "unknown")
                region = ec2.meta.region_name
                launch_time = instance.get("LaunchTime")
                
                name_tag = next(
                    (tag["Value"] for tag in instance.get("Tags", []) if tag["Key"] == "Name"),
                    "Unnamed-Instance"
                )

                utilization = 15  # placeholder
                cost = 89.5       # placeholder

                # --- Pass only relevant data to recommendation agent ---
                instance_data = {
                    "id": instance_id,
                    "name": name_tag,
                    "type": "EC2",
                    "status": state.capitalize(),
                    "utilization": utilization,
                    "monthly_cost": cost,
                    "region": region,
                    "last_activity": launch_time.isoformat() if launch_time else None
                }
                ##Uncomment below to enable dynamic recommendation generation
                # print("Generating recommendations for instance:", instance_id)
                # recommendations = await generate_recommendation(instance_data)
                # print("Recommendations for", instance_id, ":", recommendations)
                instance_data["recommendations"] = recommendations

                instances.append(instance_data)

        return instances

    except Exception as e:
        print(f"Error in list_ec2_instances: {e}")
        return []

# ---------- S3 ----------
async def list_s3_buckets():
    """Fetch all S3 buckets and enrich with recommendations."""
    try:
        s3 = session.client("s3")
        response = s3.list_buckets()
        buckets = []
        recommendations=["Archive old data to Glacier"]
        for bucket in response.get("Buckets", []):
            name = bucket.get("Name")
            creation_date = bucket.get("CreationDate")

            # Attempt to fetch bucket region (may return None for us-east-1)
            try:
                loc = s3.get_bucket_location(Bucket=name).get("LocationConstraint")
                region = loc if loc else aws_region
            except Exception:
                region = aws_region

            utilization = 5  # placeholder
            cost = 3.5       # placeholder

            bucket_data = {
                "id": name,
                "name": name,
                "type": "S3",
                "status": "Available",
                "utilization": utilization,
                "monthly_cost": cost,
                "region": region,
                "last_activity": creation_date.isoformat() if creation_date else None,
            }

            # print("Generating recommendations for S3 bucket:", name)
            # try:
            #     recommendations = await generate_recommendation(bucket_data)
            # except Exception as e:
            #     print(f"Recommendation generation failed for bucket {name}: {e}")
            #     recommendations = []

            bucket_data["recommendations"] = recommendations
            buckets.append(bucket_data)

        return buckets

    except Exception as e:
        print(f"Error in list_s3_buckets: {e}")
        return []

# ---------- DynamoDB ----------
async def list_dynamodb_tables():
    """Fetch all DynamoDB tables and enrich with recommendations."""
    try:
        dynamodb = session.client("dynamodb")
        response = dynamodb.list_tables()
        table_names = response.get("TableNames", [])
        tables = []
        recommendations=["Remove public access", "Enable encryption"]

        for name in table_names:
            try:
                desc = dynamodb.describe_table(TableName=name).get("Table", {})
            except Exception as e:
                print(f"Failed to describe DynamoDB table {name}: {e}")
                desc = {}

            item_count = desc.get("ItemCount")
            size_bytes = desc.get("TableSizeBytes")
            status = desc.get("TableStatus", "UNKNOWN")
            creation = desc.get("CreationDateTime")
            region = dynamodb.meta.region_name

            utilization = 8  # placeholder
            cost = 12.0      # placeholder

            table_data = {
                "id": name,
                "name": name,
                "type": "DynamoDB",
                "status": status,
                "utilization": utilization,
                "monthly_cost": cost,
                "region": region,
                "item_count": item_count,
                "table_size_bytes": size_bytes,
                "last_activity": creation.isoformat() if creation else None,
            }

            # print("Generating recommendations for DynamoDB table:", name)
            # try:
            #     recommendations = await generate_recommendation(table_data)
            # except Exception as e:
            #     print(f"Recommendation generation failed for table {name}: {e}")
            #     recommendations = []

            table_data["recommendations"] = recommendations
            tables.append(table_data)

        return tables

    except Exception as e:
        print(f"Error in list_dynamodb_tables: {e}")
        return []
