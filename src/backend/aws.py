import os
import boto3
from dotenv import load_dotenv
from datetime import datetime, timedelta
from recommendations import get_resource_from_db
from recommendations import save_resource_in_db

# Load credentials from .env
load_dotenv()

# Initialize AWS session
aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
aws_region = os.getenv("AWS_DEFAULT_REGION", "eu-north-1")

session = boto3.Session(
    aws_access_key_id=aws_access_key,
    aws_secret_access_key=aws_secret_key,
    region_name=aws_region
)

# ---------- EC2 ----------
async def list_ec2_instances():
    """Fetch all EC2 instances and enrich with DynamoDB-backed state."""
    try:
        ec2 = session.client("ec2")
        response = ec2.describe_instances()
        instances = []
        default_recommendations = ["Right-size to t3.small", "Enable detailed monitoring"]

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

                utilization = get_instance_utilization(instance_id, region, launch_time)
                cost = get_resource_cost("InstanceId", instance_id)

                # Base object
                instance_data = {
                    "id": instance_id,
                    "name": name_tag,
                    "type": "EC2",
                    "status": state.lower(),
                    "utilization": utilization,
                    "monthly_cost": cost,
                    "region": region,
                    "last_activity": launch_time.isoformat() if launch_time else None,
                    "creation_date": launch_time.isoformat() if launch_time else None,
                    "recommendations": default_recommendations
                }

                # --- CHECK DYNAMODB ---
                db_item = get_resource_from_db(instance_id, "EC2")

                if db_item:
                    # Load stored fields (important for state persistence)
                    instance_data["is_optimized"] = db_item.get("is_optimized", False)
                    instance_data["recommendations"] = db_item.get("recommendations", default_recommendations)
                else:
                    # Save new record
                    saved = save_resource_in_db(instance_id, "EC2", instance_data)
                    instance_data["is_optimized"] = False

                instances.append(instance_data)

        return instances

    except Exception as e:
        print(f"Error in list_ec2_instances: {e}")
        return []


# ---------- S3 ----------
async def list_s3_buckets():
    """Fetch all S3 buckets and enrich with DynamoDB-backed state."""
    try:
        s3 = session.client("s3")
        response = s3.list_buckets()
        buckets = []
        default_recommendations = ["Archive old data to Glacier"]

        for bucket in response.get("Buckets", []):
            name = bucket.get("Name")
            creation_date = bucket.get("CreationDate")

            try:
                loc = s3.get_bucket_location(Bucket=name).get("LocationConstraint")
                region = loc if loc else aws_region
            except Exception:
                region = aws_region

            utilization = get_bucket_storage_utilization(name, region)
            cost = get_resource_cost("BucketName", name)

            bucket_data = {
                "id": name,
                "name": name,
                "type": "S3",
                "status": "available",
                "utilization": utilization,
                "monthly_cost": cost,
                "region": region,
                "last_activity": creation_date.isoformat() if creation_date else None,
                "recommendations": default_recommendations
            }

            db_item = get_resource_from_db(name, "S3")

            if db_item:
                bucket_data["is_optimized"] = db_item.get("is_optimized", False)
                bucket_data["recommendations"] = db_item.get("recommendations", default_recommendations)
            else:
                save_resource_in_db(name, "S3", bucket_data)
                bucket_data["is_optimized"] = False

            buckets.append(bucket_data)

        return buckets

    except Exception as e:
        print(f"Error in list_s3_buckets: {e}")
        return []

# ---------- DynamoDB ----------
async def list_dynamodb_tables():
    """Fetch all DynamoDB tables and enrich with DynamoDB-backed state."""
    try:
        dynamodb_client = session.client("dynamodb")
        response = dynamodb_client.list_tables()
        table_names = response.get("TableNames", [])
        tables = []
        default_recommendations = ["Remove public access", "Enable encryption"]

        for name in table_names:
            try:
                desc = dynamodb_client.describe_table(TableName=name).get("Table", {})
            except Exception as e:
                print(f"Failed to describe DynamoDB table {name}: {e}")
                desc = {}

            item_count = desc.get("ItemCount")
            size_bytes = desc.get("TableSizeBytes")
            status = desc.get("TableStatus", "UNKNOWN")
            creation = desc.get("CreationDateTime")
            region = dynamodb_client.meta.region_name

            utilization = get_consumed_read_write_capacity(name, region)
            cost = get_resource_cost("TableName", name)

            table_data = {
                "id": name,
                "name": name,
                "type": "DynamoDB",
                "status": status.lower(),
                "utilization": utilization,
                "monthly_cost": cost,
                "region": region,
                "item_count": item_count,
                "table_size_bytes": size_bytes,
                "last_activity": creation.isoformat() if creation else None,
                "recommendations": default_recommendations
            }

            db_item = get_resource_from_db(name, "DynamoDB")

            if db_item:
                table_data["is_optimized"] = db_item.get("is_optimized", False)
                table_data["recommendations"] = db_item.get("recommendations", default_recommendations)
            else:
                table_data["is_optimized"] = False

                save_resource_in_db(name, "DynamoDB", table_data)

            tables.append(table_data)

        return tables

    except Exception as e:
        print(f"Error in list_dynamodb_tables: {e}")
        return []

import boto3
from datetime import datetime, timedelta

def get_resource_cost(tag_key, tag_value):
    """
    Universal AWS Cost function for EC2, S3, DynamoDB...
    Uses AWS Cost Explorer with tag-based filtering.
    """
    ce = boto3.client("ce", region_name="us-east-1")  # CE always in us-east-1
    from datetime import datetime, timedelta

    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=30)

    try:
        response = ce.get_cost_and_usage(
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
            return float(results[0]["Total"]["UnblendedCost"]["Amount"])

    except Exception as e:
        print(f"Cost lookup failed for {tag_key}:{tag_value} → {e}")

    return 0.0

def get_instance_utilization(instance_id, region="eu-north-1",start_time=None,end_time=None):
    cloudwatch = boto3.client("cloudwatch", region_name=region)
    end_time = datetime.utcnow()

    metrics = cloudwatch.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName="CPUUtilization",
        Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        StartTime=start_time,
        EndTime=end_time,
        Period=86400,  # 1-day average
        Statistics=["Average"]
    )
    datapoints = metrics.get("Datapoints", [])
    return round(datapoints[-1]["Average"], 2) if datapoints else 0.0

def get_bucket_storage_utilization(bucket_name, region="eu-north-1"):
    """Return % of data in S3 Standard storage class (or fallback utilization)."""
    s3 = boto3.client("s3", region_name=region)
    cw = boto3.client("cloudwatch", region_name=region)

    try:
        # 1. Get total bucket size (in bytes)
        total_size_metric = cw.get_metric_statistics(
            Namespace="AWS/S3",
            MetricName="BucketSizeBytes",
            Dimensions=[
                {"Name": "BucketName", "Value": bucket_name},
                {"Name": "StorageType", "Value": "StandardStorage"}
            ],
            StartTime=datetime.utcnow() - timedelta(days=3),
            EndTime=datetime.utcnow(),
            Period=86400,
            Statistics=["Average"]
        )

        points = total_size_metric.get("Datapoints", [])
        if not points:
            return 0

        standard_bytes = points[-1]["Average"]

        # Fallback total storage: assume same as standard for now
        total_bytes = standard_bytes

        # Convert to % with a default capacity cap (e.g., 100 GB)
        total_gb = total_bytes / (1024 ** 3)
        utilization = min((total_gb / 100) * 100, 100)

        return round(utilization, 2)

    except Exception as e:
        print(f"Failed to fetch S3 utilization for {bucket_name}: {e}")
        return 0

def get_consumed_read_write_capacity(table_name, region="eu-north-1"):
    """Return % DynamoDB capacity usage based on consumed RCUs/WCUs."""
    cw = boto3.client("cloudwatch", region_name=region)
    dynamodb = boto3.client("dynamodb", region_name=region)

    try:
        desc = dynamodb.describe_table(TableName=table_name)["Table"]
        rc = desc.get("ProvisionedThroughput", {}).get("ReadCapacityUnits", 0)
        wc = desc.get("ProvisionedThroughput", {}).get("WriteCapacityUnits", 0)

        # On-demand tables return NONE
        if rc == 0 and wc == 0:
            return 0

        end = datetime.utcnow()
        start = end - timedelta(hours=12)

        # Read consumed
        read_metrics = cw.get_metric_statistics(
            Namespace="AWS/DynamoDB",
            MetricName="ConsumedReadCapacityUnits",
            Dimensions=[{"Name": "TableName", "Value": table_name}],
            StartTime=start,
            EndTime=end,
            Period=3600,
            Statistics=["Average"]
        )

        # Write consumed
        write_metrics = cw.get_metric_statistics(
            Namespace="AWS/DynamoDB",
            MetricName="ConsumedWriteCapacityUnits",
            Dimensions=[{"Name": "TableName", "Value": table_name}],
            StartTime=start,
            EndTime=end,
            Period=3600,
            Statistics=["Average"]
        )

        rc_used = read_metrics.get("Datapoints", [])
        wc_used = write_metrics.get("Datapoints", [])

        read_percent = (rc_used[-1]["Average"] / rc) * 100 if rc_used and rc > 0 else 0
        write_percent = (wc_used[-1]["Average"] / wc) * 100 if wc_used and wc > 0 else 0

        return round(max(read_percent, write_percent), 2)

    except Exception as e:
        print(f"Failed to get DynamoDB capacity for {table_name}: {e}")
        return 0

 