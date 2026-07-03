"""
Terraform Drift Detection Service
----------------------------------
Compares Terraform state against live AWS resources.
Generates PRs to sync in either direction (user's choice).

Flow:
1. Read terraform.tfstate (the expected state)
2. Fetch live AWS state via boto3
3. Compare and detect drifts
4. Offer two fix options per drift:
   - Update Terraform to match AWS
   - Update AWS to match Terraform (via terraform apply)
"""

import json
import os
import boto3
from datetime import datetime, timezone
from typing import Any
from pathlib import Path

# ---------------------------------------------------------------------------
# Terraform state parser
# ---------------------------------------------------------------------------

def load_terraform_state(state_file: str = "terraform.tfstate") -> dict:
    """Load and parse terraform.tfstate file."""
    print(f"Loading Terraform state from {state_file}...")
    if not os.path.exists(state_file):
        raise FileNotFoundError(
            f"Terraform state file not found: {state_file}. "
            "Run 'terraform refresh' first or check the path."
        )
    
    with open(state_file) as f:
        return json.load(f)


def extract_resources_from_state(state: dict) -> dict:
    """
    Extract EC2, S3, RDS, SG resources from Terraform state.
    Returns dict grouped by resource type.
    """
    resources = {
        "ec2": {},
        "s3": {},
        "rds": {},
        "sg": {},
    }
    
    for resource in state.get("resources", []):
        rtype = resource.get("type", "")
        instances = resource.get("instances", [])
        
        for inst in instances:
            attrs = inst.get("attributes", {})
            
            # EC2 instances
            if rtype == "aws_instance":
                iid = attrs.get("id")
                if iid:
                    resources["ec2"][iid] = {
                        "instance_type": attrs.get("instance_type"),
                        "ami": attrs.get("ami"),
                        "vpc_security_group_ids": sorted(attrs.get("vpc_security_group_ids", [])),
                        "subnet_id": attrs.get("subnet_id"),
                        "iam_instance_profile": attrs.get("iam_instance_profile"),
                        "monitoring": attrs.get("monitoring"),
                        "ebs_optimized": attrs.get("ebs_optimized"),
                        "tags": attrs.get("tags", {}),
                    }
            
            # S3 buckets
            elif rtype == "aws_s3_bucket":
                bucket = attrs.get("bucket") or attrs.get("id")
                if bucket:
                    resources["s3"][bucket] = {
                        "bucket": bucket,
                        "versioning": attrs.get("versioning", [{}])[0].get("enabled", False),
                        # Note: encryption and public access are separate resources in TF
                        # You may need to cross-reference aws_s3_bucket_server_side_encryption_configuration
                        # and aws_s3_bucket_public_access_block
                    }
            
            # RDS instances
            elif rtype == "aws_db_instance":
                dbid = attrs.get("id") or attrs.get("identifier")
                if dbid:
                    resources["rds"][dbid] = {
                        "instance_class": attrs.get("instance_class"),
                        "engine": attrs.get("engine"),
                        "engine_version": attrs.get("engine_version"),
                        "multi_az": attrs.get("multi_az"),
                        "storage_type": attrs.get("storage_type"),
                        "allocated_storage": attrs.get("allocated_storage"),
                        "storage_encrypted": attrs.get("storage_encrypted"),
                        "publicly_accessible": attrs.get("publicly_accessible"),
                        "backup_retention_period": attrs.get("backup_retention_period"),
                        "deletion_protection": attrs.get("deletion_protection"),
                        "vpc_security_group_ids": sorted(attrs.get("vpc_security_group_ids", [])),
                    }
            
            # Security Groups
            elif rtype == "aws_security_group":
                sgid = attrs.get("id")
                if sgid:
                    resources["sg"][sgid] = {
                        "name": attrs.get("name"),
                        "description": attrs.get("description"),
                        "vpc_id": attrs.get("vpc_id"),
                        "ingress": _normalize_tf_rules(attrs.get("ingress", [])),
                        "egress": _normalize_tf_rules(attrs.get("egress", [])),
                    }
    
    return resources


def _normalize_tf_rules(rules: list) -> list:
    """Normalize Terraform SG rules to match boto3 format for comparison."""
    normalized = []
    for rule in rules:
        base = {
            "protocol": rule.get("protocol", "-1"),
            "from_port": rule.get("from_port", 0),
            "to_port": rule.get("to_port", 0),
        }
        for cidr in rule.get("cidr_blocks", []):
            normalized.append({**base, "cidr": cidr})
        for cidr6 in rule.get("ipv6_cidr_blocks", []):
            normalized.append({**base, "cidr_v6": cidr6})
    return sorted(normalized, key=lambda x: json.dumps(x, sort_keys=True))


# ---------------------------------------------------------------------------
# AWS fetchers (reuse from previous implementation)
# ---------------------------------------------------------------------------

def fetch_ec2_state(region: str = "ap-south-1") -> dict:
    """Fetch live EC2 state."""
    ec2 = boto3.client("ec2", region_name=region)
    paginator = ec2.get_paginator("describe_instances")
    
    instances = {}
    for page in paginator.paginate():
        for reservation in page["Reservations"]:
            for inst in reservation["Instances"]:
                if inst["State"]["Name"] == "terminated":
                    continue
                    
                iid = inst["InstanceId"]
                instances[iid] = {
                    "instance_type": inst["InstanceType"],
                    "ami": inst.get("ImageId"),
                    "vpc_security_group_ids": sorted([sg["GroupId"] for sg in inst.get("SecurityGroups", [])]),
                    "subnet_id": inst.get("SubnetId"),
                    "iam_instance_profile": inst.get("IamInstanceProfile", {}).get("Arn", ""),
                    "monitoring": inst.get("Monitoring", {}).get("State") == "enabled",
                    "ebs_optimized": inst.get("EbsOptimized", False),
                    "tags": {t["Key"]: t["Value"] for t in inst.get("Tags", [])},
                }
    return instances


def fetch_sg_state(region: str = "ap-south-1") -> dict:
    """Fetch live Security Group state."""
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
                "ingress": _normalize_aws_rules(sg.get("IpPermissions", [])),
                "egress": _normalize_aws_rules(sg.get("IpPermissionsEgress", [])),
            }
    return groups


def _normalize_aws_rules(rules: list) -> list:
    """Normalize AWS SG rules for comparison."""
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
# Drift comparison
# ---------------------------------------------------------------------------

SEVERITY_RULES = {
    "ec2": {
        "instance_type": "High",
        "vpc_security_group_ids": "Critical",
        "iam_instance_profile": "Critical",
        "ami": "High",
        "subnet_id": "High",
        "monitoring": "Low",
    },
    "sg": {
        "ingress": "Critical",
        "egress": "High",
    },
}


def compare_terraform_vs_aws(
    resource_type: str,
    resource_id: str,
    tf_state: dict,
    aws_state: dict,
) -> list[dict]:
    """Compare one resource's Terraform state vs live AWS. Return drifts."""
    drifts = []
    rules = SEVERITY_RULES.get(resource_type, {})
    
    # Skip tags by default (too noisy)
    all_keys = (set(tf_state.keys()) | set(aws_state.keys())) - {"tags", "name"}
    
    for key in all_keys:
        expected = tf_state.get(key)
        actual = aws_state.get(key)
        
        if expected == actual:
            continue
        
        severity = rules.get(key, "Medium")
        
        drifts.append({
            "resource_id": resource_id,
            "resource_type": resource_type.upper(),
            "field": key,
            "terraform_value": str(expected),
            "aws_value": str(actual),
            "severity": severity,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        })
    
    return drifts


def detect_terraform_drifts(
    tf_state_file: str = "terraform.tfstate",
    region: str = "ap-south-1",
) -> dict:
    """
    Main drift detection function.
    Compares Terraform state against live AWS.
    """
    print(f"Starting drift detection with tf_state_file={tf_state_file} and region={region}")
    # Load Terraform state
    tf_state = load_terraform_state(tf_state_file)
    tf_resources = extract_resources_from_state(tf_state)
    print(f"Extracted {len(tf_resources['ec2'])} EC2, {len(tf_resources['sg'])} SG from Terraform state")
    all_drifts = []
    
    # EC2 drift detection
    tf_ec2 = tf_resources["ec2"]
    aws_ec2 = fetch_ec2_state(region)
    
    for iid in set(tf_ec2.keys()) & set(aws_ec2.keys()):
        drifts = compare_terraform_vs_aws("ec2", iid, tf_ec2[iid], aws_ec2[iid])
        all_drifts.extend(drifts)
    
    # SG drift detection
    tf_sg = tf_resources["sg"]
    aws_sg = fetch_sg_state(region)
    
    for sgid in set(tf_sg.keys()) & set(aws_sg.keys()):
        drifts = compare_terraform_vs_aws("sg", sgid, tf_sg[sgid], aws_sg[sgid])
        all_drifts.extend(drifts)
    
    # Count by severity
    summary = {"critical": 0, "high": 0, "medium": 0, "low": 0}
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
# Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    
    tf_file = sys.argv[1] if len(sys.argv) > 1 else "terraform.tfstate"
    result = detect_terraform_drifts(tf_file)
    
    print(json.dumps(result, indent=2))
    print(f"\nTotal drifts: {result['total']}")
    print(f"Summary: {result['summary']}")