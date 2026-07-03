"""
Drift Detection Service
-----------------------
Compares live AWS resource state against a stored baseline.
Uses static rules (no LLM calls) to detect and classify drift.

Flow:
1. On first run / manual trigger → snapshot current state as baseline
2. On subsequent checks → fetch live state, compare against baseline
3. Flag differences with severity based on static rules
"""

import boto3
import json
import os
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Baseline storage (JSON file for now — swap to DynamoDB/Postgres later)
# ---------------------------------------------------------------------------

BASELINE_DIR = os.path.join(os.path.dirname(__file__), "baselines")
os.makedirs(BASELINE_DIR, exist_ok=True)


def _baseline_path(resource_type: str) -> str:
    return os.path.join(BASELINE_DIR, f"{resource_type}_baseline.json")


def save_baseline(resource_type: str, data: dict):
    with open(_baseline_path(resource_type), "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_baseline(resource_type: str) -> dict | None:
    path = _baseline_path(resource_type)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# AWS fetchers — pull live state for each resource type
# ---------------------------------------------------------------------------

def fetch_ec2_state(region: str = "ap-south-1") -> dict:
    """Fetch all EC2 instances and their key config properties."""
    ec2 = boto3.client("ec2", region_name=region)
    paginator = ec2.get_paginator("describe_instances")

    instances = {}
    for page in paginator.paginate():
        for reservation in page["Reservations"]:
            for inst in reservation["Instances"]:
                iid = inst["InstanceId"]
                instances[iid] = {
                    "instance_type": inst["InstanceType"],
                    "state": inst["State"]["Name"],
                    "ami_id": inst.get("ImageId"),
                    "vpc_id": inst.get("VpcId"),
                    "subnet_id": inst.get("SubnetId"),
                    "security_groups": sorted(
                        [sg["GroupId"] for sg in inst.get("SecurityGroups", [])]
                    ),
                    "iam_role": (
                        inst.get("IamInstanceProfile", {}).get("Arn", "")
                    ),
                    "ebs_optimized": inst.get("EbsOptimized", False),
                    "monitoring": inst.get("Monitoring", {}).get("State"),
                    "tags": {
                        t["Key"]: t["Value"]
                        for t in inst.get("Tags", [])
                    },
                }
    return instances


def fetch_s3_state(region: str = "ap-south-1") -> dict:
    """Fetch S3 bucket configs: versioning, encryption, public access."""
    s3 = boto3.client("s3", region_name=region)
    buckets = {}

    for bucket in s3.list_buckets().get("Buckets", []):
        name = bucket["Name"]
        entry = {"name": name}

        # Versioning
        try:
            v = s3.get_bucket_versioning(Bucket=name)
            entry["versioning"] = v.get("Status", "Disabled")
        except Exception:
            entry["versioning"] = "Unknown"

        # Server-side encryption
        try:
            enc = s3.get_bucket_encryption(Bucket=name)
            rules = enc["ServerSideEncryptionConfiguration"]["Rules"]
            entry["encryption"] = rules[0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]
        except Exception:
            entry["encryption"] = "None"

        # Public access block
        try:
            pub = s3.get_public_access_block(Bucket=name)
            config = pub["PublicAccessBlockConfiguration"]
            entry["public_access_blocked"] = all([
                config.get("BlockPublicAcls", False),
                config.get("IgnorePublicAcls", False),
                config.get("BlockPublicPolicy", False),
                config.get("RestrictPublicBuckets", False),
            ])
        except Exception:
            entry["public_access_blocked"] = False

        buckets[name] = entry
    return buckets


def fetch_rds_state(region: str = "ap-south-1") -> dict:
    """Fetch RDS instance configs."""
    rds = boto3.client("rds", region_name=region)
    paginator = rds.get_paginator("describe_db_instances")

    instances = {}
    for page in paginator.paginate():
        for db in page["DBInstances"]:
            dbid = db["DBInstanceIdentifier"]
            instances[dbid] = {
                "instance_class": db["DBInstanceClass"],
                "engine": db["Engine"],
                "engine_version": db["EngineVersion"],
                "multi_az": db.get("MultiAZ", False),
                "storage_type": db.get("StorageType"),
                "allocated_storage_gb": db.get("AllocatedStorage"),
                "storage_encrypted": db.get("StorageEncrypted", False),
                "publicly_accessible": db.get("PubliclyAccessible", False),
                "backup_retention_days": db.get("BackupRetentionPeriod", 0),
                "deletion_protection": db.get("DeletionProtection", False),
                "auto_minor_version_upgrade": db.get("AutoMinorVersionUpgrade", False),
                "vpc_security_groups": sorted([
                    sg["VpcSecurityGroupId"]
                    for sg in db.get("VpcSecurityGroups", [])
                ]),
            }
    return instances


def fetch_sg_state(region: str = "ap-south-1") -> dict:
    """Fetch Security Group rules."""
    ec2 = boto3.client("ec2", region_name=region)
    paginator = ec2.get_paginator("describe_security_groups")

    groups = {}
    for page in paginator.paginate():
        for sg in page["SecurityGroups"]:
            sgid = sg["GroupId"]
            groups[sgid] = {
                "name": sg["GroupName"],
                "description": sg.get("Description", ""),
                "vpc_id": sg.get("VpcId"),
                "ingress_rules": _normalize_rules(sg.get("IpPermissions", [])),
                "egress_rules": _normalize_rules(sg.get("IpPermissionsEgress", [])),
            }
    return groups


def _normalize_rules(rules: list) -> list:
    """Flatten SG rules into comparable dicts."""
    normalized = []
    for rule in rules:
        base = {
            "protocol": rule.get("IpProtocol", "-1"),
            "from_port": rule.get("FromPort", 0),
            "to_port": rule.get("ToPort", 0),
        }
        for ip_range in rule.get("IpRanges", []):
            normalized.append({**base, "cidr": ip_range["CidrIp"]})
        for ip_range in rule.get("Ipv6Ranges", []):
            normalized.append({**base, "cidr_v6": ip_range["CidrIpv6"]})
    return sorted(normalized, key=lambda x: json.dumps(x, sort_keys=True))


# ---------------------------------------------------------------------------
# Severity rules — static, no LLM
# ---------------------------------------------------------------------------

# Maps (resource_type, field) → severity + reason template
# "Critical" = security risk or major cost impact
# "High"     = significant config change
# "Medium"   = moderate change, may be intentional
# "Low"      = minor / cosmetic

SEVERITY_RULES: dict[str, dict[str, dict]] = {
    "ec2": {
        "instance_type": {
            "severity": "High",
            "reason": "Instance type changed from {expected} to {actual}. May affect cost and performance.",
        },
        "security_groups": {
            "severity": "Critical",
            "reason": "Security groups changed. Was {expected}, now {actual}.",
        },
        "iam_role": {
            "severity": "Critical",
            "reason": "IAM role changed from {expected} to {actual}. Possible privilege escalation.",
        },
        "state": {
            "severity": "Medium",
            "reason": "Instance state changed from {expected} to {actual}.",
        },
        "ami_id": {
            "severity": "High",
            "reason": "AMI changed from {expected} to {actual}. Instance may have been relaunched.",
        },
        "subnet_id": {
            "severity": "High",
            "reason": "Subnet changed from {expected} to {actual}. Network topology drift.",
        },
        "monitoring": {
            "severity": "Low",
            "reason": "Monitoring changed from {expected} to {actual}.",
        },
    },
    "s3": {
        "versioning": {
            "severity": "High",
            "reason": "Bucket versioning changed from {expected} to {actual}. Data protection risk.",
        },
        "encryption": {
            "severity": "Critical",
            "reason": "Encryption changed from {expected} to {actual}. Data may be unencrypted.",
        },
        "public_access_blocked": {
            "severity": "Critical",
            "reason": "Public access block changed from {expected} to {actual}. Bucket may be publicly accessible.",
        },
    },
    "rds": {
        "instance_class": {
            "severity": "High",
            "reason": "RDS instance class changed from {expected} to {actual}. Cost/performance impact.",
        },
        "multi_az": {
            "severity": "High",
            "reason": "Multi-AZ changed from {expected} to {actual}. Availability impact.",
        },
        "storage_encrypted": {
            "severity": "Critical",
            "reason": "Storage encryption changed from {expected} to {actual}.",
        },
        "publicly_accessible": {
            "severity": "Critical",
            "reason": "Public accessibility changed from {expected} to {actual}. Security risk.",
        },
        "backup_retention_days": {
            "severity": "Medium",
            "reason": "Backup retention changed from {expected} to {actual} days.",
        },
        "deletion_protection": {
            "severity": "High",
            "reason": "Deletion protection changed from {expected} to {actual}.",
        },
        "engine_version": {
            "severity": "Medium",
            "reason": "Engine version changed from {expected} to {actual}.",
        },
        "vpc_security_groups": {
            "severity": "Critical",
            "reason": "VPC security groups changed. Was {expected}, now {actual}.",
        },
    },
    "sg": {
        "ingress_rules": {
            "severity": "Critical",
            "reason": "Inbound rules changed. Possible unauthorized port exposure.",
        },
        "egress_rules": {
            "severity": "High",
            "reason": "Outbound rules changed. May indicate data exfiltration risk.",
        },
    },
}

# Catch-all for fields not in the rules above
DEFAULT_SEVERITY = {
    "severity": "Low",
    "reason": "Field '{field}' changed from {expected} to {actual}.",
}


# ---------------------------------------------------------------------------
# Diff engine — compare baseline vs live state
# ---------------------------------------------------------------------------

def compare_resource(
    resource_type: str,
    resource_id: str,
    baseline: dict,
    live: dict,
) -> list[dict]:
    """Compare one resource's baseline vs live config. Return list of drifts."""
    drifts = []
    rules = SEVERITY_RULES.get(resource_type, {})

    all_keys = set(baseline.keys()) | set(live.keys())
    # Skip tags — too noisy for drift detection by default
    all_keys.discard("tags")
    all_keys.discard("name")

    for key in all_keys:
        expected = baseline.get(key)
        actual = live.get(key)

        if expected == actual:
            continue

        rule = rules.get(key, {
            **DEFAULT_SEVERITY,
            "reason": DEFAULT_SEVERITY["reason"].replace("{field}", key),
        })

        drifts.append({
            "resource_id": resource_id,
            "resource_type": resource_type.upper(),
            "field": key,
            "expected_value": str(expected),
            "actual_value": str(actual),
            "severity": rule["severity"],
            "reason": rule["reason"].format(
                expected=expected, actual=actual
            ),
            "detected_at": datetime.now(timezone.utc).isoformat(),
        })

    return drifts


def detect_all_drifts(
    resource_type: str,
    baseline_data: dict,
    live_data: dict,
) -> list[dict]:
    """Compare all resources of a type. Also detect new/deleted resources."""
    all_drifts = []

    baseline_ids = set(baseline_data.keys())
    live_ids = set(live_data.keys())

    # Resources in baseline but missing live → deleted
    for rid in baseline_ids - live_ids:
        all_drifts.append({
            "resource_id": rid,
            "resource_type": resource_type.upper(),
            "field": "_resource",
            "expected_value": "exists",
            "actual_value": "deleted / not found",
            "severity": "Critical",
            "reason": f"Resource {rid} existed in baseline but is no longer found. May have been terminated/deleted.",
            "detected_at": datetime.now(timezone.utc).isoformat(),
        })

    # Resources live but not in baseline → new (not necessarily drift, but worth flagging)
    for rid in live_ids - baseline_ids:
        all_drifts.append({
            "resource_id": rid,
            "resource_type": resource_type.upper(),
            "field": "_resource",
            "expected_value": "not in baseline",
            "actual_value": "exists",
            "severity": "Medium",
            "reason": f"New resource {rid} found that wasn't in the baseline. May be intentional.",
            "detected_at": datetime.now(timezone.utc).isoformat(),
        })

    # Resources in both → compare field by field
    for rid in baseline_ids & live_ids:
        drifts = compare_resource(
            resource_type, rid, baseline_data[rid], live_data[rid]
        )
        all_drifts.extend(drifts)

    return all_drifts


# ---------------------------------------------------------------------------
# Main API — what your FastAPI routes will call
# ---------------------------------------------------------------------------

FETCHERS = {
    "ec2": fetch_ec2_state,
    "s3": fetch_s3_state,
    "rds": fetch_rds_state,
    "sg": fetch_sg_state,
}


def snapshot_baseline(region: str = "ap-south-1") -> dict:
    """
    Capture current AWS state as the baseline.
    Call this once during initial setup, or when the user
    clicks 'Set Current State as Baseline'.
    """
    result = {}
    for rtype, fetcher in FETCHERS.items():
        try:
            data = fetcher(region)
            save_baseline(rtype, data)
            result[rtype] = {"status": "ok", "count": len(data)}
        except Exception as e:
            result[rtype] = {"status": "error", "error": str(e)}
    return result


def run_drift_detection(region: str = "ap-south-1") -> dict:
    """
    Compare live AWS state against saved baseline.
    Returns all detected drifts grouped by resource type.
    """
    all_drifts = []
    summary = {"critical": 0, "high": 0, "medium": 0, "low": 0}

    for rtype, fetcher in FETCHERS.items():
        baseline = load_baseline(rtype)
        if baseline is None:
            all_drifts.append({
                "resource_type": rtype.upper(),
                "severity": "Medium",
                "reason": f"No baseline found for {rtype.upper()}. Run 'Set Baseline' first.",
                "detected_at": datetime.now(timezone.utc).isoformat(),
            })
            continue

        try:
            live = fetcher(region)
        except Exception as e:
            all_drifts.append({
                "resource_type": rtype.upper(),
                "severity": "Low",
                "reason": f"Failed to fetch live {rtype.upper()} state: {e}",
                "detected_at": datetime.now(timezone.utc).isoformat(),
            })
            continue

        drifts = detect_all_drifts(rtype, baseline, live)
        all_drifts.extend(drifts)

    for d in all_drifts:
        sev = d.get("severity", "Low").lower()
        if sev in summary:
            summary[sev] += 1

    return {
        "drifts": all_drifts,
        "summary": summary,
        "total": len(all_drifts),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "baseline":
        print("Snapshotting baseline...")
        result = snapshot_baseline()
        print(json.dumps(result, indent=2))
    else:
        print("Running drift detection...")
        result = run_drift_detection()
        print(json.dumps(result, indent=2, default=str))
        print(f"\nTotal drifts: {result['total']}")
        print(f"Summary: {result['summary']}")