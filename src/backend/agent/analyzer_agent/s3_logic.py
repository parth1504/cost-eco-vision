import logging

# Initialize logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from typing import Dict, Any, List, Optional
from agent.llm.llm_client import get_llm_client


def _generate_description(prompt: str) -> str:
    logger.info("Generating description for prompt: %s", prompt)
    try:
        llm = get_llm_client()
        return llm.generate(prompt)
    except Exception as e:
        logger.error("Error generating description: %s", e)
        return prompt


def check_s3_public_access(resource: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    config = resource.get("config", {})
    bucket_name = resource.get("name")

    if config.get("public_access_blocked") is False:
        description = _generate_description(
            f"Explain why public access on S3 bucket '{bucket_name}' is a critical security risk and should be blocked."
        )

        return {
            "title": "Public Access Enabled on S3 Bucket",
            "description": description,
            "type": "security",
            "severity": "critical",
            "saving": "N/A",
            "status": "active",
            "issue": "Public access is not blocked",
            "impact": "high",
            "solution_steps": [
                {
                    "step": 1,
                    "command": f"aws s3api put-public-access-block --bucket {bucket_name} --public-access-block-configuration '{{\"BlockPublicAcls\":true,\"IgnorePublicAcls\":true,\"BlockPublicPolicy\":true,\"RestrictPublicBuckets\":true}}'",
                    "description": "Block all forms of public access to the bucket."
                }
            ],
            "boto3_sequence": [
                {
                    "service": "s3",
                    "operation": "put_public_access_block",
                    "params": {
                        "Bucket": bucket_name,
                        "PublicAccessBlockConfiguration": {
                            "BlockPublicAcls": True,
                            "IgnorePublicAcls": True,
                            "BlockPublicPolicy": True,
                            "RestrictPublicBuckets": True
                        }
                    }
                }
            ]
        }
    return None


def check_s3_encryption(resource: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    config = resource.get("config", {})
    bucket_name = resource.get("name")

    if config.get("encryption_enabled") is False:
        description = _generate_description(
            f"Explain why enabling encryption on S3 bucket '{bucket_name}' is important for data protection and compliance."
        )

        return {
            "title": "S3 Bucket Encryption Disabled",
            "description": description,
            "type": "security",
            "severity": "high",
            "saving": "N/A",
            "status": "active",
            "issue": "Encryption at rest is not enabled",
            "impact": "high",
            "solution_steps": [
                {
                    "step": 1,
                    "command": f"aws s3api put-bucket-encryption --bucket {bucket_name} --server-side-encryption-configuration '{{\"Rules\":[{{\"ApplyServerSideEncryptionByDefault\":{{\"SSEAlgorithm\":\"AES256\"}}}}]}}'",
                    "description": "Enable AES256 encryption on the bucket."
                }
            ],
            "boto3_sequence": [
                {
                    "service": "s3",
                    "operation": "put_bucket_encryption",
                    "params": {
                        "Bucket": bucket_name,
                        "ServerSideEncryptionConfiguration": {
                            "Rules": [
                                {
                                    "ApplyServerSideEncryptionByDefault": {
                                        "SSEAlgorithm": "AES256"
                                    }
                                }
                            ]
                        }
                    }
                }
            ]
        }
    return None


def check_s3_versioning(resource: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    config = resource.get("config", {})
    bucket_name = resource.get("name")

    if config.get("versioning_enabled") is False:
        description = _generate_description(
            f"Explain why enabling versioning on S3 bucket '{bucket_name}' improves resilience and recovery."
        )

        return {
            "title": "S3 Bucket Versioning Disabled",
            "description": description,
            "type": "resilience",
            "severity": "medium",
            "saving": "N/A",
            "status": "active",
            "issue": "Versioning is disabled",
            "impact": "medium",
            "solution_steps": [
                {
                    "step": 1,
                    "command": f"aws s3api put-bucket-versioning --bucket {bucket_name} --versioning-configuration Status=Enabled",
                    "description": "Enable versioning for recovery and rollback."
                }
            ],
            "boto3_sequence": [
                {
                    "service": "s3",
                    "operation": "put_bucket_versioning",
                    "params": {
                        "Bucket": bucket_name,
                        "VersioningConfiguration": {
                            "Status": "Enabled"
                        }
                    }
                }
            ]
        }
    return None


def check_s3_low_usage(resource: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    metrics = resource.get("metrics", {})
    bucket_name = resource.get("name")
    storage_bytes = metrics.get("storage_bytes", 0)

    if storage_bytes < (1 * 1024 * 1024 * 1024):
        description = _generate_description(
            f"Explain cost optimization strategies for an S3 bucket '{bucket_name}' storing less than 1GB of data."
        )

        return {
            "title": "Low Storage Utilization in S3 Bucket",
            "description": description,
            "type": "cost",
            "severity": "medium",
            "saving": "Potential minor savings",
            "status": "active",
            "issue": "Very low storage usage",
            "impact": "low",
            "solution_steps": [
                {
                    "step": 1,
                    "command": f"aws s3api put-bucket-lifecycle-configuration --bucket {bucket_name} --lifecycle-configuration file://lifecycle.json",
                    "description": "Configure lifecycle policies to transition objects to cheaper storage classes."
                }
            ],
            "boto3_sequence": [
                {
                    "service": "s3",
                    "operation": "put_bucket_lifecycle_configuration",
                    "params": {
                        "Bucket": bucket_name,
                        "LifecycleConfiguration": {
                            "Rules": [
                                {
                                    "ID": "LowUsageTransition",
                                    "Status": "Enabled",
                                    "Filter": {"Prefix": ""},
                                    "Transitions": [
                                        {
                                            "Days": 30,
                                            "StorageClass": "STANDARD_IA"
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                }
            ]
        }
    return None


def analyze_s3_resource(resource: Dict[str, Any]) -> List[Dict[str, Any]]:
    recommendations = []

    for check in [
        check_s3_public_access,
        check_s3_encryption,
        check_s3_versioning,
        check_s3_low_usage,
    ]:
        result = check(resource)
        if result:
            recommendations.append(result)

    return recommendations

def generate_s3_recommendations(resource):
    """
    Entry point for S3 analyzer agent.
    Ensures safety checks and delegates to analysis layer.
    """

    if not resource or resource.get("type") != "S3":
        return []

    # Skip if already optimized (context awareness)
    if resource.get("is_optimized"):
        return []

    # Optional safety: skip very new buckets
    metadata = resource.get("metadata", {})
    creation_date = metadata.get("creation_date")

    if creation_date:
        try:
            from datetime import datetime, timedelta
            created = datetime.fromisoformat(creation_date.replace("Z", ""))
            if datetime.utcnow() - created < timedelta(days=1):
                return []
        except Exception:
            pass

    return analyze_s3_resource(resource)