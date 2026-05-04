from connections.aws import get_client, get_region
from connections.db import get_resource_from_db, save_resource_in_db
from connections.db import get_resource_from_db, save_resource_in_db
from aws.util import replace_placeholders, get_resource_cost
from aws.util import should_run_agent
from backend.agent.analyzer_agent.main import generateRecommendations

from datetime import datetime, timedelta
aws_region = get_region()


s3 = get_client("s3")
cloudwatch = get_client("cloudwatch")

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
        ],
        "boto3_sequence": [{
            "service": "s3",
            "operation": "put_public_access_block",
            "params": {
                "Bucket": "{BUCKET_NAME}",
                "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True
                }
            }
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

    # {
    #     "title": "Delete Unused Multipart Uploads",
    #     "description": (
    #         "There are aborted or in-progress multipart uploads older than 7 days. "
    #         "These accumulate storage and cost unnecessarily."
    #     ),
    #     "type": "cost",
    #     "severity": "warning",
    #     "saving": 5.60,    # estimated cost reclamation
    #     "issue": "Orphaned multipart uploads detected",
    #     "impact": "low",
    #     "status": "active",
    #     "solution_steps": [
    #         {
    #             "step": 1,
    #             "command": "aws s3api list-multipart-uploads --bucket {BUCKET_NAME}",
    #             "description": "Identify ongoing or abandoned multipart uploads."
    #         },
    #         {
    #             "step": 2,
    #             "command": (
    #                 "aws s3api abort-multipart-upload --bucket {BUCKET_NAME} "
    #                 "--key {OBJECT_KEY} --upload-id {UPLOAD_ID}"
    #             ),
    #             "description": "Abort unused multipart uploads to clean up wasted storage."
    #         }
    #     ]
    # }
]


async def list_s3_buckets():
    """Fetch all S3 buckets and enrich with DynamoDB-backed state."""
    try:

        response = s3.list_buckets()
        buckets = []

        for bucket in response.get("Buckets", []):
            name = bucket.get("Name")

            db_item = get_resource_from_db(name, "S3")

            if db_item:

                bucket_data=db_item
                bucket_data["resource_id"] = name

                last_run= bucket_data.get("last_agent_run")
                print(f"Bucket {name} last agent run: {last_run}")
                if should_run_agent(last_run):
                    recommendations = generateRecommendations(bucket_data)
                    bucket_data["recommendations"] = recommendations
                    bucket_data["last_agent_run"] = datetime.utcnow().isoformat()

                    save_resource_in_db(name, "S3", bucket_data)

                
            else:
                bucket_data=build_s3_resource(bucket)
                
                print(f"Built S3 resource data for {name}: {bucket_data}")
                print("-------------------------------------------------------------------------")
                recommendations=generateRecommendations(bucket_data)
                bucket_data["recommendations"]=recommendations
            saved=save_resource_in_db(name, "S3", bucket_data)

            buckets.append(bucket_data)

        return buckets

    except Exception as e:
        print(f"Error in list_s3_buckets: {e}")
        return []

def get_bucket_storage_utilization(bucket_name, region="us-east-1"):
    """Return % of data in S3 Standard storage class (or fallback utilization)."""

    try:
        # 1. Get total bucket size (in bytes)
        total_size_metric = cloudwatch.get_metric_statistics(
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

def build_s3_resource(bucket, s3_client):
    name = bucket.get("Name")

    return {
        "resource_id": name,
        "name": name,
        "type": "S3",
        "status": "available",
        "region": get_region(),
        "provider": "AWS",

        "metrics": get_s3_metrics(name),
        "config": get_s3_config(name, s3_client),

        "monthly_cost": get_resource_cost("BucketName", name),

        "metadata": {
            "creation_date": bucket.get("CreationDate").isoformat()
            if bucket.get("CreationDate") else None
        },

        "is_optimized": False,
        "last_agent_run": datetime.utcnow().isoformat()
    }


def get_s3_metrics(bucket_name):
    utilization = get_bucket_storage_utilization(bucket_name, get_region())

    return {
        "storage_bytes": utilization.get("size_bytes") if utilization else None,
        "object_count": utilization.get("object_count") if utilization else None
    }

def get_s3_config(bucket_name, s3_client):
    # Public access
    try:
        pab = s3_client.get_public_access_block(Bucket=bucket_name)
        public_block = pab["PublicAccessBlockConfiguration"]
        public_access_blocked = all(public_block.values())
    except Exception:
        public_access_blocked = False

    # Encryption
    try:
        s3_client.get_bucket_encryption(Bucket=bucket_name)
        encryption_enabled = True
    except Exception:
        encryption_enabled = False

    # Versioning
    try:
        versioning = s3_client.get_bucket_versioning(Bucket=bucket_name)
        versioning_enabled = versioning.get("Status") == "Enabled"
    except Exception:
        versioning_enabled = False

    # Policy
    try:
        s3_client.get_bucket_policy(Bucket=bucket_name)
        has_policy = True
    except Exception:
        has_policy = False

    return {
        "public_access_blocked": public_access_blocked,
        "encryption_enabled": encryption_enabled,
        "versioning_enabled": versioning_enabled,
        "has_bucket_policy": has_policy
    }