from typing import Dict, Any


def block_public_access(bucket_name: str, s3_client) -> Dict[str, Any]:
    """
    Blocks all forms of public access to an S3 bucket.
    Use when bucket is publicly exposed.
    """
    try:
        response = s3_client.put_public_access_block(
            Bucket=bucket_name,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
        return {"status": "success", "message": "Public access blocked", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


def remove_public_acl(bucket_name: str, s3_client) -> Dict[str, Any]:
    """
    Removes public ACLs from a bucket.
    Use when bucket ACL grants public read/write.
    """
    try:
        response = s3_client.put_bucket_acl(Bucket=bucket_name, ACL="private")
        return {"status": "success", "message": "Public ACL removed", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


def enable_bucket_encryption(bucket_name: str, s3_client) -> Dict[str, Any]:
    """
    Enables AES256 server-side encryption on a bucket.
    Use for compliance/security.
    """
    try:
        response = s3_client.put_bucket_encryption(
            Bucket=bucket_name,
            ServerSideEncryptionConfiguration={
                "Rules": [
                    {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            },
        )
        return {"status": "success", "message": "Encryption enabled", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


def enable_versioning(bucket_name: str, s3_client) -> Dict[str, Any]:
    """
    Enables versioning on a bucket.
    Useful for rollback and recovery.
    """
    try:
        response = s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={"Status": "Enabled"},
        )
        return {"status": "success", "message": "Versioning enabled", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


def delete_bucket_policy(bucket_name: str, s3_client) -> Dict[str, Any]:
    """
    Deletes bucket policy.
    Use if policy is overly permissive.
    """
    try:
        response = s3_client.delete_bucket_policy(Bucket=bucket_name)
        return {"status": "success", "message": "Bucket policy deleted", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


def restrict_bucket_to_vpc(bucket_name: str, s3_client) -> Dict[str, Any]:
    """
    Mock: Restricts bucket access to a VPC endpoint.
    In real use, attach a bucket policy with aws:SourceVpce condition.
    """
    try:
        return {
            "status": "success",
            "message": "Mock VPC restriction applied (implement via bucket policy)",
            "data": None,
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


def lifecycle_transition_to_glacier(bucket_name: str, days: int, s3_client) -> Dict[str, Any]:
    """
    Moves objects to Glacier after specified days.
    Useful for cost optimization.
    """
    try:
        response = s3_client.put_bucket_lifecycle_configuration(
            Bucket=bucket_name,
            LifecycleConfiguration={
                "Rules": [
                    {
                        "ID": "MoveToGlacier",
                        "Status": "Enabled",
                        "Filter": {"Prefix": ""},
                        "Transitions": [
                            {"Days": days, "StorageClass": "GLACIER"}
                        ],
                    }
                ]
            },
        )
        return {"status": "success", "message": "Lifecycle rule applied", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


ACTION_REGISTRY = {
    "block_public_access": block_public_access,
    "remove_public_acl": remove_public_acl,
    "enable_bucket_encryption": enable_bucket_encryption,
    "enable_versioning": enable_versioning,
    "delete_bucket_policy": delete_bucket_policy,
    "restrict_bucket_to_vpc": restrict_bucket_to_vpc,
    "lifecycle_transition_to_glacier": lifecycle_transition_to_glacier,
}