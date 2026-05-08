import logging

# Initialize logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from typing import Dict, Any, List, Optional
from services.description_cache import get_description

# Static descriptions per rule. Boilerplate that doesn't depend on
# per-resource context — see services/description_cache.py for rationale.
DESCRIPTIONS = {
    "s3.public_access": (
        "This S3 bucket allows public access, the leading cause of data "
        "leakage incidents in cloud breaches. Enabling Block Public Access "
        "prevents accidental exposure via ACLs, bucket policies, or new "
        "objects with permissive settings."
    ),
    "s3.encryption_disabled": (
        "This S3 bucket lacks server-side encryption at rest, violating "
        "common compliance frameworks (SOC2, HIPAA, PCI-DSS). Enabling "
        "AES-256 encryption is free and protects data from unauthorized "
        "access at the storage layer."
    ),
    "s3.versioning_disabled": (
        "Versioning is disabled on this S3 bucket. Without versioning, "
        "accidental deletions or overwrites are unrecoverable. Versioning "
        "protects against operational errors and ransomware-style data "
        "destruction."
    ),
    "s3.low_usage": (
        "This S3 bucket holds less than 1GB of data. Configuring a "
        "lifecycle policy to transition objects to S3 Standard-IA or "
        "Glacier after 30 days reduces storage cost with minimal impact on "
        "access patterns."
    ),
}


def check_s3_public_access(resource: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    config = resource.get("config", {})
    bucket_name = resource.get("name")

    if config.get("public_access_blocked") is False:
        description = get_description(
            "s3.public_access",
            prompt=f"Explain why public access on S3 bucket '{bucket_name}' is a critical security risk and should be blocked.",
            static_text=DESCRIPTIONS["s3.public_access"],
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
        description = get_description(
            "s3.encryption_disabled",
            prompt=f"Explain why enabling encryption on S3 bucket '{bucket_name}' is important for data protection and compliance.",
            static_text=DESCRIPTIONS["s3.encryption_disabled"],
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
        description = get_description(
            "s3.versioning_disabled",
            prompt=f"Explain why enabling versioning on S3 bucket '{bucket_name}' improves resilience and recovery.",
            static_text=DESCRIPTIONS["s3.versioning_disabled"],
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
    metrics = resource.get("metrics", {}) or {}
    bucket_name = resource.get("name")
    storage_bytes = metrics.get("storage_bytes")

    # Skip if size is unknown — firing "low storage" on an unmeasured bucket
    # is a false positive. (Previously this crashed with TypeError because
    # `.get(key, 0)` returns None when the key exists with None value.)
    if storage_bytes is None:
        return None

    if storage_bytes < (1 * 1024 * 1024 * 1024):
        description = get_description(
            "s3.low_usage",
            prompt=f"Explain cost optimization strategies for an S3 bucket '{bucket_name}' storing less than 1GB of data.",
            static_text=DESCRIPTIONS["s3.low_usage"],
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
    Delegates to the analysis layer.

    NOTE: the "< 1 day old" safety guard has been removed so freshly-
    imported buckets surface recommendations immediately.
    """
    if not resource or resource.get("type") != "S3":
        return []

    if resource.get("is_optimized"):
        return []

    return analyze_s3_resource(resource)