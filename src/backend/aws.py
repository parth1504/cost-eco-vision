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

ec2_recommendations = [
    {
        "title": "Instance Underutilized — Right-size to t3.small",
        "description": (
            "The instance has consistently low CPU and network utilization for the last 7 days. "
            "Downsizing to a smaller instance type can significantly reduce cost without affecting performance."
        ),
        "type": "cost",
        "severity": "warning",
        "saving": 42.75,  # monthly savings estimate
        "issue": "Low CPU utilization (<5%) detected for 7 days",
        "impact": "medium",
        "status": "active",
        "solution_steps": [
            {
                "step": 1,
                "command": "aws ec2 stop-instances --instance-ids {INSTANCE_ID}",
                "description": "Stops the EC2 instance before changing instance type."
            },
            {
                "step": 2,
                "command": "aws ec2 modify-instance-attribute --instance-id {INSTANCE_ID} --instance-type \"t3.small\"",
                "description": "Modifies the instance type to a more cost-efficient size."
            },
            {
                "step": 3,
                "command": "aws ec2 start-instances --instance-ids {INSTANCE_ID}",
                "description": "Restarts the instance after applying the change."
            }
        ]
    },

    {
        "title": "Instance Missing Detailed Monitoring",
        "description": (
            "The instance is using basic monitoring which provides fewer metrics at 5-minute intervals. "
            "Enabling detailed monitoring provides 1-minute metrics for more accurate auto scaling and alerting."
        ),
        "type": "performance",
        "severity": "info",
        "saving": "N/A",
        "status": "active",
        "issue": "Detailed monitoring is disabled",
        "impact": "low",
        "solution_steps": [
            {
                "step": 1,
                "command": "aws ec2 monitor-instances --instance-ids {INSTANCE_ID}",
                "description": "Enables detailed 1-minute CloudWatch monitoring for the EC2 instance."
            }
        ]
    },

    # {
    #     "title": "Publicly Accessible EC2 Instance",
    #     "description": (
    #         "The instance has a public IP and a security group rule that allows inbound access from 0.0.0.0/0. "
    #         "This poses a major security risk and violates most compliance benchmarks (CIS, PCI, SOC2)."
    #     ),
    #     "type": "security",
    #     "severity": "critical",
    #     "saving": "N/A",
    #     "issue": "Security group open to the world (0.0.0.0/0)",
    #     "impact": "high",
    #     "solution_steps": [
    #         {
    #             "step": 1,
    #             "command": "aws ec2 revoke-security-group-ingress --group-id {SG_ID} --protocol tcp --port 22 --cidr 0.0.0.0/0",
    #             "description": "Removes the insecure inbound rule from the security group."
    #         },
    #         {
    #             "step": 2,
    #             "command": "aws ec2 authorize-security-group-ingress --group-id {SG_ID} --protocol tcp --port 22 --cidr {YOUR_IP}/32",
    #             "description": "Restricts SSH access to your IP only."
    #         }
    #     ]
    # },

    # {
    #     "title": "EBS Volume Attached but Unused",
    #     "description": (
    #         "An EBS volume attached to this instance has had no read/write activity for more than 30 days. "
    #         "You may be paying for unused storage."
    #     ),
    #     "type": "cost",
    #     "severity": "warning",
    #     "saving": 12.0,  # monthly volume cost
    #     "issue": "Unused EBS volume detected",
    #     "impact": "low",
    #     "solution_steps": [
    #         {
    #             "step": 1,
    #             "command": "aws ec2 detach-volume --volume-id {VOLUME_ID}",
    #             "description": "Detaches the unused volume."
    #         },
    #         {
    #             "step": 2,
    #             "command": "aws ec2 delete-volume --volume-id {VOLUME_ID}",
    #             "description": "Deletes the unused volume to eliminate cost."
    #         }
    #     ]
    # },

    # {
    #     "title": "Missing IMDSv2 Protection",
    #     "description": (
    #         "The instance metadata service is configured for IMDSv1, which is susceptible to SSRF attacks. "
    #         "Enforcing IMDSv2 significantly improves instance security posture."
    #     ),
    #     "type": "security",
    #     "severity": "high",
    #     "saving": "N/A",
    #     "issue": "IMDSv1 still enabled",
    #     "impact": "high",
    #     "solution_steps": [
    #         {
    #             "step": 1,
    #             "command": "aws ec2 modify-instance-metadata-options --instance-id {INSTANCE_ID} --http-endpoint enabled --http-tokens required",
    #             "description": "Configures the instance to require IMDSv2."
    #         }
    #     ]
    # }
]
# ---------- EC2 ----------
async def list_ec2_instances():
    """Fetch all EC2 instances and enrich with DynamoDB-backed state."""
    try:
        ec2 = session.client("ec2")
        response = ec2.describe_instances()
        instances = []
        

        for reservation in response.get("Reservations", []):
            for instance in reservation.get("Instances", []):

                instance_id = instance.get("InstanceId")
                
                # --- CHECK DYNAMODB ---
                db_item = get_resource_from_db(instance_id, "EC2")
                
                if db_item:
                    # Load stored fields (important for state persistence)
                    instance_data=db_item
                    instance_data['resource_id']=instance_id
                else:
                    # Save new record
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
                        "resource_id": instance_id,
                        "name": name_tag,
                        "type": "EC2",
                        "status": state.lower(),
                        "utilization": utilization,
                        "monthly_cost": cost,
                        "region": region,
                        "provider": "AWS",
                        "is_optimized": False,
                        "last_activity": launch_time.isoformat() if launch_time else None,
                        "creation_date": launch_time.isoformat() if launch_time else None,
                        "recommendations": ec2_recommendations
                    }

                    saved = save_resource_in_db(instance_id, "EC2", instance_data)

                instances.append(instance_data)

        return instances

    except Exception as e:
        print(f"Error in list_ec2_instances: {e}")
        return []


# ---------- S3 ----------
s3_recommendations = [
    # {
    #     "title": "Archive Cold Data to S3 Glacier",
    #     "description": (
    #         "The bucket contains objects that have not been accessed in over 90 days. "
    #         "Moving them to S3 Glacier reduces storage costs significantly while keeping the data accessible."
    #     ),
    #     "type": "cost",
    #     "severity": "warning",
    #     "saving": 28.40,   # estimated monthly savings
    #     "issue": "Cold data detected (>90 days no access)",
    #     "impact": "medium",
    #     "solution_steps": [
    #         {
    #             "step": 1,
    #             "command": "aws s3 ls s3://{BUCKET_NAME}/ --recursive --human-readable --summarize",
    #             "description": "List all objects in the bucket with metadata to identify cold data."
    #         },
    #         {
    #             "step": 2,
    #             "command": (
    #                 "aws s3api put-object-tagging --bucket {BUCKET_NAME} --key {OBJECT_KEY} "
    #                 "--tagging 'TagSet=[{Key=glacier-archive,Value=true}]'"
    #             ),
    #             "description": "Tag objects eligible for Glacier transition."
    #         },
    #         {
    #             "step": 3,
    #             "command": (
    #                 "aws s3api put-bucket-lifecycle-configuration --bucket {BUCKET_NAME} "
    #                 "--lifecycle-configuration file://glacier-policy.json"
    #             ),
    #             "description": "Apply a lifecycle policy to automatically transition cold objects to Glacier."
    #         }
    #     ]
    # },

    # {
    #     "title": "Enable Server-Side Encryption",
    #     "description": (
    #         "The bucket is not encrypted. Storing unencrypted objects in S3 violates most "
    #         "security compliance standards like SOC2, HIPAA, and PCI."
    #     ),
    #     "type": "security",
    #     "severity": "critical",
    #     "saving": "N/A",
    #     "issue": "Bucket has no default encryption",
    #     "impact": "high",
    #     "solution_steps": [
    #         {
    #             "step": 1,
    #             "command": (
    #                 "aws s3api put-bucket-encryption --bucket {BUCKET_NAME} "
    #                 "--server-side-encryption-configuration "
    #                 "'{\"Rules\":[{\"ApplyServerSideEncryptionByDefault\":{\"SSEAlgorithm\":\"AES256\"}}]}'"
    #             ),
    #             "description": "Enables default AES-256 encryption on all new S3 objects."
    #         }
    #     ]
    # },

    {
        "title": "Block Public Access to Bucket",
        "description": (
            "This S3 bucket is publicly accessible. Public access without necessity is a major "
            "security risk and often leads to data leakage incidents."
        ),
        "type": "security",
        "severity": "critical",
        "saving": "N/A",
        "status": "active",
        "issue": "Public access block disabled",
        "impact": "high",
        "solution_steps": [
            {
                "step": 1,
                "command": (
                    "aws s3api put-public-access-block --bucket {BUCKET_NAME} "
                    "--public-access-block-configuration "
                    "'{\"BlockPublicAcls\":true,\"IgnorePublicAcls\":true,\"BlockPublicPolicy\":true,\"RestrictPublicBuckets\":true}'"
                ),
                "description": "Blocks all forms of public access to the bucket."
            }
        ]
    },

    # {
    #     "title": "Enable S3 Access Logging",
    #     "description": (
    #         "Bucket access logging is disabled. Logging provides insights into suspicious activity "
    #         "and is essential for audit and security investigations."
    #     ),
    #     "type": "security",
    #     "severity": "medium",
    #     "saving": "N/A",
    #     "issue": "Access logging disabled",
    #     "impact": "medium",
    #     "solution_steps": [
    #         {
    #             "step": 1,
    #             "command": (
    #                 "aws s3api put-bucket-logging --bucket {BUCKET_NAME} "
    #                 "--bucket-logging-status "
    #                 "'{\"LoggingEnabled\":{\"TargetBucket\":\"{LOG_BUCKET}\",\"TargetPrefix\":\"logs/\"}}'"
    #             ),
    #             "description": "Enables logging by writing access logs to a designated bucket or folder."
    #         }
    #     ]
    # },

    {
        "title": "Delete Unused Multipart Uploads",
        "description": (
            "There are aborted or in-progress multipart uploads older than 7 days. "
            "These accumulate storage and cost unnecessarily."
        ),
        "type": "cost",
        "severity": "warning",
        "saving": 5.60,    # estimated cost reclamation
        "issue": "Orphaned multipart uploads detected",
        "impact": "low",
        "status": "active",
        "solution_steps": [
            {
                "step": 1,
                "command": "aws s3api list-multipart-uploads --bucket {BUCKET_NAME}",
                "description": "Identify ongoing or abandoned multipart uploads."
            },
            {
                "step": 2,
                "command": (
                    "aws s3api abort-multipart-upload --bucket {BUCKET_NAME} "
                    "--key {OBJECT_KEY} --upload-id {UPLOAD_ID}"
                ),
                "description": "Abort unused multipart uploads to clean up wasted storage."
            }
        ]
    }
]

async def list_s3_buckets():
    """Fetch all S3 buckets and enrich with DynamoDB-backed state."""
    try:
        s3 = session.client("s3")
        response = s3.list_buckets()
        buckets = []

        for bucket in response.get("Buckets", []):
            name = bucket.get("Name")
            

            db_item = get_resource_from_db(name, "S3")

            if db_item:
                bucket_data=db_item
                
            else:
                creation_date = bucket.get("CreationDate")

                try:
                    loc = s3.get_bucket_location(Bucket=name).get("LocationConstraint")
                    region = loc if loc else aws_region
                except Exception:
                    region = aws_region

                utilization = get_bucket_storage_utilization(name, region)
                cost = get_resource_cost("BucketName", name)

                bucket_data = {
                    "resource_id": name,
                    "name": name,
                    "type": "S3",
                    "status": "available",
                    "utilization": utilization,
                    "monthly_cost": cost,
                    "region": region,
                    "provider": "AWS",
                    "last_activity": creation_date.isoformat() if creation_date else None,
                    "is_optimized": False,
                    "recommendations": s3_recommendations
                }
                save_resource_in_db(name, "S3", bucket_data)

            buckets.append(bucket_data)

        return buckets

    except Exception as e:
        print(f"Error in list_s3_buckets: {e}")
        return []

# ---------- DynamoDB ----------
dynamodb_recommendations = [
    # {
    #     "title": "Remove Public Access from DynamoDB Table",
    #     "description": (
    #         "The table is accessible via overly permissive IAM policies. "
    #         "Public access exposes sensitive data and violates SOC2, PCI-DSS, and ISO 27001 guidelines."
    #     ),
    #     "type": "security",
    #     "severity": "critical",
    #     "saving": "N/A",
    #     "issue": "IAM policy allows public or wildcard (*) access",
    #     "impact": "high",
    #     "solution_steps": [
    #         {
    #             "step": 1,
    #             "command": (
    #                 "aws iam list-policies --query \"Policies[?contains(PolicyName, '{TABLE_NAME}')].Arn\""
    #             ),
    #             "description": "Identify IAM policies attached to the DynamoDB table."
    #         },
    #         {
    #             "step": 2,
    #             "command": (
    #                 "aws iam detach-role-policy --role-name {ROLE_NAME} --policy-arn {POLICY_ARN}"
    #             ),
    #             "description": "Detach any overly permissive role policies."
    #         },
    #         {
    #             "step": 3,
    #             "command": (
    #                 "aws iam put-role-policy --role-name {ROLE_NAME} --policy-name SecureAccessPolicy "
    #                 "--policy-document file://restricted-ddb-policy.json"
    #             ),
    #             "description": "Attach a secure least-privilege policy that restricts access."
    #         }
    #     ]
    # },

    {
        "title": "Enable DynamoDB Server-Side Encryption",
        "description": (
            "The table is not encrypted at rest. Unencrypted DynamoDB tables can lead to compliance failures "
            "and data exposure risks."
        ),
        "type": "security",
        "severity": "high",
        "status": "active",
        "saving": "N/A",
        "issue": "Encryption at rest is disabled",
        "impact": "high",
        "solution_steps": [
            {
                "step": 1,
                "command": (
                    "aws dynamodb update-table --table-name {TABLE_NAME} "
                    "--sse-specification Enabled=true,SSEType=KMS"
                ),
                "description": "Enable AWS KMS-based server-side encryption."
            }
        ]
    },

    # {
    #     "title": "Right-Size DynamoDB Read/Write Capacity",
    #     "description": (
    #         "Provisioned capacity is significantly higher than actual usage. "
    #         "Downsizing capacity reduces monthly cost without performance impact."
    #     ),
    #     "type": "cost",
    #     "severity": "warning",
    #     "saving": 12.80,  # Example savings
    #     "issue": "Provisioned RCU/WCU far above actual traffic",
    #     "impact": "medium",
    #     "solution_steps": [
    #         {
    #             "step": 1,
    #             "command": (
    #                 "aws dynamodb describe-table --table-name {TABLE_NAME} "
    #                 "--query 'Table.ProvisionedThroughput'"
    #             ),
    #             "description": "Check current read/write capacity settings."
    #         },
    #         {
    #             "step": 2,
    #             "command": (
    #                 "aws dynamodb update-table --table-name {TABLE_NAME} "
    #                 "--provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5"
    #             ),
    #             "description": "Reduce RCU/WCU to match actual usage."
    #         }
    #     ]
    # },

    {
        "title": "Enable Point-in-Time Recovery (PITR)",
        "description": (
            "Point-in-Time Recovery is disabled. Enabling PITR protects your DynamoDB tables from "
            "accidental writes, deletes, or corruption."
        ),
        "type": "security",
        "severity": "medium",
        "saving": "N/A",
        "status": "active",
        "issue": "PITR disabled",
        "impact": "medium",
        "solution_steps": [
            {
                "step": 1,
                "command": (
                    "aws dynamodb update-continuous-backups --table-name {TABLE_NAME} "
                    "--point-in-time-recovery-specification PointInTimeRecoveryEnabled=true"
                ),
                "description": "Enable point-in-time recovery."
            }
        ]
    },

    # {
    #     "title": "Remove Unused Global Secondary Indexes (GSI)",
    #     "description": (
    #         "One or more GSIs have extremely low read/write activity. "
    #         "Maintaining idle GSIs creates unnecessary monthly costs."
    #     ),
    #     "type": "cost",
    #     "severity": "warning",
    #     "saving": 4.20,
    #     "issue": "Low-traffic or unused indexes detected",
    #     "impact": "low",
    #     "solution_steps": [
    #         {
    #             "step": 1,
    #             "command": (
    #                 "aws dynamodb describe-table --table-name {TABLE_NAME} "
    #                 "--query 'Table.GlobalSecondaryIndexes'"
    #             ),
    #             "description": "Check all GSIs and their usage metrics."
    #         },
    #         {
    #             "step": 2,
    #             "command": (
    #                 "aws dynamodb update-table --table-name {TABLE_NAME} "
    #                 "--global-secondary-index-updates '[{\"Delete\": {\"IndexName\": \"{GSI_NAME}\"}}]'"
    #             ),
    #             "description": "Delete unused GSI to eliminate wasted capacity."
    #         }
    #     ]
    # }
]

async def list_dynamodb_tables():
    """Fetch all DynamoDB tables and enrich with DynamoDB-backed state."""
    try:
        dynamodb_client = session.client("dynamodb")
        response = dynamodb_client.list_tables()
        table_names = response.get("TableNames", [])
        tables = []

        for name in table_names:
            

            db_item = get_resource_from_db(name, "DynamoDB")

            if db_item:
                table_data=db_item
            else:
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
                    "resource_id": name,
                    "name": name,
                    "type": "DynamoDB",
                    "status": status.lower(),
                    "utilization": utilization,
                    "monthly_cost": cost,
                    "region": region,
                    "provider": "AWS",
                    "is_optimized": False,
                    "item_count": item_count,
                    "table_size_bytes": size_bytes,
                    "last_activity": creation.isoformat() if creation else None,
                    "recommendations": dynamodb_recommendations
                }

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

 