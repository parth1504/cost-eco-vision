import os
import boto3
from dotenv import load_dotenv
from datetime import datetime, timedelta


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
def list_ec2_instances():
    """Fetch all EC2 instances with basic details."""
    print("Fetching resources from AWS...")
    ec2 = session.client("ec2")
    response = ec2.describe_instances()
    instances = []
    co
    for reservation in response.get("Reservations", []):
        for instance in reservation.get("Instances", []):
            instances.append({
                "InstanceId": instance["InstanceId"],
                "State": instance["State"]["Name"],
                "Type": instance["InstanceType"],
                "LaunchTime": instance["LaunchTime"].isoformat()
            })
    return instances

# ---------- S3 ----------
def list_s3_buckets():
    """Fetch all S3 bucket names."""
    s3 = session.client("s3")
    response = s3.list_buckets()
    return [bucket["Name"] for bucket in response["Buckets"]]

# ---------- CloudWatch ----------
def get_ec2_cpu_utilization(instance_id):
    """Fetch recent CPU utilization metrics for an EC2 instance."""
    cloudwatch = session.client("cloudwatch")
    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName="CPUUtilization",
        Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        StartTime=datetime.utcnow() - timedelta(hours=1),
        EndTime=datetime.utcnow(),
        Period=300,
        Statistics=["Average"]
    )
    data_points = response.get("Datapoints", [])
    if not data_points:
        return {"InstanceId": instance_id, "CPUUtilization": None}
    return {
        "InstanceId": instance_id,
        "CPUUtilization": round(data_points[-1]["Average"], 2)
    }
