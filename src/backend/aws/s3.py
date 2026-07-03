from connections.aws import get_client, get_region
from connections.db import get_resource_from_db, save_resource_in_db
from connections.db import get_resource_from_db, save_resource_in_db
from aws.util import replace_placeholders, get_resource_cost
from aws.util import should_run_agent
from agent.analyzer_agent.main import generateRecommendations

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


async def list_s3_buckets(force: bool = False):
    """
    Fetch all S3 buckets and enrich with DynamoDB-backed state.

    Pass force=True to bypass the cooldown and force a fresh agent re-run.
    On re-run we now re-fetch live metrics+config from AWS rather than
    feeding stale cached fields to the agent.
    """
    try:
        response = s3.list_buckets()
        buckets = []

        for bucket in response.get("Buckets", []):
            name = bucket.get("Name")
            db_item = get_resource_from_db(name, "S3")

            if db_item:
                last_run = db_item.get("last_agent_run")
                print(f"Bucket {name} last agent run: {last_run}, force={force}")

                if should_run_agent(last_run, force=force):
                    bucket_data = build_s3_resource(bucket)
                    bucket_data["is_optimized"] = db_item.get("is_optimized", False)
                    recommendations = generateRecommendations(bucket_data)
                    bucket_data["recommendations"] = recommendations
                    bucket_data["last_agent_run"] = datetime.utcnow().isoformat()
                    save_resource_in_db(name, "S3", bucket_data)
                else:
                    bucket_data = db_item
                    bucket_data["resource_id"] = name
            else:
                bucket_data = build_s3_resource(bucket)
                recommendations = generateRecommendations(bucket_data)
                bucket_data["recommendations"] = recommendations
                save_resource_in_db(name, "S3", bucket_data)

            buckets.append(bucket_data)

        return buckets

    except Exception as e:
        print(f"Error in list_s3_buckets: {e}")
        return []

def get_bucket_storage_utilization(bucket_name, region="us-east-1"):
    """
    Return S3 storage stats as a dict:
      {
        "size_bytes": <int>,           # total Standard storage bytes
        "object_count": <int|None>,    # not currently fetched (would require ListObjectsV2)
        "utilization_percent": <float> # against an assumed 100GB cap, capped at 100
      }
    Empty dict if unavailable.
    """
    try:
        size_metric = cloudwatch.get_metric_statistics(
            Namespace="AWS/S3",
            MetricName="BucketSizeBytes",
            Dimensions=[
                {"Name": "BucketName", "Value": bucket_name},
                {"Name": "StorageType", "Value": "StandardStorage"},
            ],
            StartTime=datetime.utcnow() - timedelta(days=3),
            EndTime=datetime.utcnow(),
            Period=86400,
            Statistics=["Average"],
        )

        points = sorted(size_metric.get("Datapoints", []), key=lambda d: d["Timestamp"])
        if not points:
            return {}

        standard_bytes = int(points[-1]["Average"])
        total_gb = standard_bytes / (1024 ** 3)
        utilization = min((total_gb / 100) * 100, 100)

        return {
            "size_bytes": standard_bytes,
            "object_count": None,  # needs ListObjectsV2 — not free, skip for now
            "utilization_percent": round(utilization, 2),
        }

    except Exception as e:
        print(f"Failed to fetch S3 utilization for {bucket_name}: {e}")
        return {}

def build_s3_resource(bucket):
    name = bucket.get("Name")

    return {
        "resource_id": name,
        "name": name,
        "type": "S3",
        "status": "available",
        "region": get_region(),
        "provider": "AWS",

        "metrics": get_s3_metrics(name),
        "config": get_s3_config(name),

        "monthly_cost": get_resource_cost("BucketName", name),

        "metadata": {
            "creation_date": bucket.get("CreationDate").isoformat()
            if bucket.get("CreationDate") else None
        },

        "is_optimized": False,
        "last_agent_run": datetime.utcnow().isoformat()
    }


def get_s3_metrics(bucket_name):
    """
    Return only the metric keys we actually have values for. Omitting a key
    (vs. setting it to None) lets downstream rules cleanly distinguish
    "data unavailable" from "data is genuinely zero" — None breaks numeric
    comparisons; missing keys can be defaulted via .get(key, 0).
    """
    utilization = get_bucket_storage_utilization(bucket_name, get_region()) or {}

    metrics = {}
    if utilization.get("size_bytes") is not None:
        metrics["storage_bytes"] = utilization["size_bytes"]
    if utilization.get("object_count") is not None:
        metrics["object_count"] = utilization["object_count"]
    return metrics

def get_s3_config(bucket_name):
    # Public access — distinguish "no PAB configured" (legitimate finding,
    # → False) from API errors we couldn't classify (→ None / unknown).
    try:
        pab = s3.get_public_access_block(Bucket=bucket_name)
        public_block = pab["PublicAccessBlockConfiguration"]
        public_access_blocked = all(public_block.values())
    except s3.exceptions.ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code == "NoSuchPublicAccessBlockConfiguration":
            public_access_blocked = False  # legitimately not blocked
        else:
            public_access_blocked = None   # unknown — don't fire false-positive
    except Exception:
        public_access_blocked = None

    # Encryption — same distinction.
    try:
        s3.get_bucket_encryption(Bucket=bucket_name)
        encryption_enabled = True
    except s3.exceptions.ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code == "ServerSideEncryptionConfigurationNotFoundError":
            encryption_enabled = False  # legitimately not encrypted
        else:
            encryption_enabled = None
    except Exception:
        encryption_enabled = None

    # Versioning — absence of "Enabled" means it's off, that's a known state.
    try:
        versioning = s3.get_bucket_versioning(Bucket=bucket_name)
        versioning_enabled = versioning.get("Status") == "Enabled"
    except Exception:
        versioning_enabled = None

    # Policy presence — boolean is fine here.
    try:
        s3.get_bucket_policy(Bucket=bucket_name)
        has_policy = True
    except Exception:
        has_policy = False

    return {
        "public_access_blocked": public_access_blocked,
        "encryption_enabled": encryption_enabled,
        "versioning_enabled": versioning_enabled,
        "has_bucket_policy": has_policy,
    }