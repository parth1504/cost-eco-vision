# Mock data for Security features
import boto3
import json
from datetime import datetime, timezone

from botocore.exceptions import ClientError
from aws_executor import apply_aws_commands

s3 = boto3.client("s3")
ec2 = boto3.client("ec2")
iam = boto3.client("iam")
dynamodb = boto3.client("dynamodb")
acm = boto3.client("acm")


def replace_placeholders(obj, mapping):
    """
    Recursively replace placeholders like {INSTANCE_ID} in strings,
    lists, and nested dictionaries.
    """
    if isinstance(obj, str):
        for key, value in mapping.items():
            obj = obj.replace(f"{{{key}}}", value)
        return obj

    elif isinstance(obj, list):
        return [replace_placeholders(item, mapping) for item in obj]

    elif isinstance(obj, dict):
        return {k: replace_placeholders(v, mapping) for k, v in obj.items()}

    else:
        return obj

async def fetch_iam_access_keys():
    all_keys = []

    users_resp = iam.list_users()

    for user in users_resp["Users"]:
        user_name = user["UserName"]

        # Get access keys for user
        access_keys = iam.list_access_keys(UserName=user_name)["AccessKeyMetadata"]

        for k in access_keys:
            key_id = k["AccessKeyId"]

            # ---- GET LAST USED ----
            last_used_info = iam.get_access_key_last_used(AccessKeyId=key_id)
            last_used = last_used_info["AccessKeyLastUsed"].get("LastUsedDate")

            if last_used:
                last_used_utc = last_used.replace(tzinfo=timezone.utc)
                days_since_last_used = (datetime.now(timezone.utc) - last_used_utc).days
                last_used_str = last_used_utc.isoformat()
            else:
                # Key has NEVER been used → should be treated as UNUSED (NOT expired)
                days_since_last_used = 999
                last_used_str = "Never"

            # ---- STATUS LOGIC ----
            if last_used_str == "Never":
                status = "Unused"
            elif days_since_last_used > 90:
                status = "Unused"        # NOT expired
            elif days_since_last_used > 30:
                status = "Unused"
            else:
                status = "Active"

            # ---- EXPIRES IN (only for UI) ----
            expires_in = max(0, 90 - days_since_last_used)
            if last_used_str == "Never":
                expires_in = 90

            all_keys.append({
                "id": key_id,
                "name": f"AWS IAM Access Key ({user_name})",
                "type": "Access Key",
                "lastUsed": last_used_str,
                "expiresIn": expires_in,
                "status": status
            })

    return all_keys


async def get_security_keys_dynamic():
    iam_keys = await fetch_iam_access_keys()
    
    return iam_keys 

mock_security_score = {
    "trend": [
        {"week": "Week 1", "score": 72},
        {"week": "Week 2", "score": 74},
        {"week": "Week 3", "score": 71},
        {"week": "Week 4", "score": 76},
        {"week": "Week 5", "score": 75},
        {"week": "Week 6", "score": 78}
    ],
    "weeklyData": [
        {"day": "Mon", "score": 75},
        {"day": "Tue", "score": 76},
        {"day": "Wed", "score": 74},
        {"day": "Thu", "score": 77},
        {"day": "Fri", "score": 78},
        {"day": "Sat", "score": 78},
        {"day": "Sun", "score": 78}
    ]
}

async def _safe_get_bucket_encryption(bucket_name):
    try:
        resp = await s3.get_bucket_encryption(Bucket=bucket_name)
        # If call succeeds, encryption exists
        return True
    except s3.exceptions.ClientError as e:
        # If no encryption present, AWS raises an error with Code 'ServerSideEncryptionConfigurationNotFoundError'
        return False
    except Exception:
        return False

async def _is_sg_open_to_world(sg):
    """
    Return True if any inbound rule allows 0.0.0.0/0 (or ::/0)
    sg: security group dict from describe_security_groups()
    """
    for perm in sg.get("IpPermissions", []):
        for ip in perm.get("IpRanges", []):
            cidr = ip.get("CidrIp", "")
            if cidr == "0.0.0.0/0":
                return True
        for ip6 in perm.get("Ipv6Ranges", []):
            if ip6.get("CidrIpv6", "") == "::/0":
                return True
    return False

async def _iam_user_is_over_permissive(user_name):
    """
    Simple heuristic:
      - If user has managed policy named 'AdministratorAccess' (attached)
      - OR if any inline policy document contains Action: "*" or Resource: "*" with Effect: "Allow"
    This is conservative and easy to compute.
    """
    try:
        # 1) check attached managed policies
        attached = iam.list_attached_user_policies(UserName=user_name).get("AttachedPolicies", [])
        for p in attached:
            pname = p.get("PolicyName", "").lower()
            if "administratoraccess" in pname or "admin" == pname:
                return True

        # 2) check inline policies
        inline_names = await iam.list_user_policies(UserName=user_name).get("PolicyNames", [])
        for pname in inline_names:
            doc = await iam.get_user_policy(UserName=user_name, PolicyName=pname).get("PolicyDocument", {})
            # policy document structure: {"Statement": [...]}
            statements = doc.get("Statement", [])
            if isinstance(statements, dict):
                statements = [statements]
            for st in statements:
                effect = st.get("Effect", "")
                actions = st.get("Action", [])
                resources = st.get("Resource", [])
                if isinstance(actions, str):
                    actions = [actions]
                if isinstance(resources, str):
                    resources = [resources]
                # check wildcards
                if effect.lower() == "allow":
                    for a in actions:
                        if a == "*" or a.endswith(":*") or a == "iam:*":
                            return True
                    for r in resources:
                        if r == "*" or r == "arn:aws:iam::*:role/*":
                            return True
        # 3) as extra check, inspect attached policies' default versions for wildcard statements (optional / expensive)
        # skipping deeper policy inspection for speed; the above is often sufficient for demos
    except Exception:
        # on any failure, do not mark over-permissive (safer)
        return False
    return False

async def build_s3_bucket_finding(bucket_name):
    """Return finding dict if bucket lacks encryption, else None"""
    encrypted = await _safe_get_bucket_encryption(bucket_name)
    status = "Fixed" if encrypted else "Open"
        
    # remediation steps (AWS CLI)
    steps = [
        {
            "step": 1,
            "description": "Enable server-side encryption (AES-256) on the bucket.",
            "command": (
                f"aws s3api put-bucket-encryption --bucket {bucket_name} "
                "--server-side-encryption-configuration "
                "'{\"Rules\":[{\"ApplyServerSideEncryptionByDefault\":{\"SSEAlgorithm\":\"AES256\"}}]}'"
            ),
            "boto3_commands":[
                {
                    "service": "s3",
                    "operation": "put_bucket_encryption",
                    "params": {
                        "Bucket": "{bucket_name}",
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
                },
                {
                    "service": "s3",
                    "operation": "get_bucket_encryption",
                    "params": {
                        "Bucket": "{bucket_name}"
                    }
                },
                {
                    "service": "s3",
                    "operation": "put_public_access_block",
                    "params": {
                        "Bucket": "{bucket_name}",
                        "PublicAccessBlockConfiguration": {
                            "BlockPublicAcls": True,
                            "IgnorePublicAcls": True,
                            "BlockPublicPolicy": True,
                            "RestrictPublicBuckets": True
                        }
                    }
                },
                {
                    "service": "s3",
                    "operation": "put_bucket_acl",
                    "params": {
                        "Bucket": "{bucket_name}",
                        "ACL": "private"
                    }
                }
            ]

        },
        {
            "step": 2,
            "description": "Verify encryption configuration.",
            "command": f"aws s3api get-bucket-encryption --bucket {bucket_name}"
        }
    ]
    finding = {
        "id": bucket_name,
        "title": "S3 Bucket Not Encrypted",
        "severity": "High",
        "description": f"Bucket {bucket_name} does not have server-side encryption enabled.",
        "resource": bucket_name,
        "resource_type": "S3",
        "compliance": ["SOC 2", "ISO 27001", "HIPAA"],
        "remediation": {
            "title": "Enable server-side encryption",
            "steps": steps
        },
        "estimatedCost": 12,
        "status": status,
        "detected_at": datetime.utcnow().isoformat()
    }
    return finding

async def build_sg_finding(sg):
    """Return finding dict if sg open to world, else None"""
    status = "Open"
    if not await _is_sg_open_to_world(sg):
        status="Fixed"
    sg_id = sg.get("GroupId")
    sg_name = sg.get("GroupName")
    # build steps
    steps = [
        {
            "step": 1,
            "description": "Revoke the open inbound rule that allows 0.0.0.0/0",
            "command": (
                f"aws ec2 revoke-security-group-ingress --group-id {sg_id} "
                "--protocol tcp --port 22 --cidr 0.0.0.0/0"
            )
        },
        {
            "step": 2,
            "description": "Confirm updated rules",
            "command": f"aws ec2 describe-security-groups --group-ids {sg_id}"
        }
    ]
    finding = {
        "id": {sg_id},
        "title": "Overly Permissive Security Group",
        "severity": "Critical",
        "description": f"Security group {sg_name} ({sg_id}) allows inbound traffic from 0.0.0.0/0.",
        "resource": sg_id,
        "resource_type": "SecurityGroup",
        "compliance": ["CIS Benchmark", "ISO 27001"],
        "remediation": {
            "title": "Restrict inbound rules",
            "steps": steps
        },
        "estimatedCost": 0,
        "status": status,
        "detected_at": datetime.utcnow().isoformat()
    }
    return finding


async def build_iam_user_finding(user_name):
    """Return finding dict if user over-permissive, else None"""
    print("Building IAM user finding for:", user_name)
    over = await _iam_user_is_over_permissive(user_name)
    status = "Open" if over else "Fixed"
    # remediation steps to detach admin and attach readonly
    steps = [
        {
            "step": 1,
            "description": "Detach AdministratorAccess managed policy from the user.",
            "command": f"aws iam detach-user-policy --user-name {user_name} --policy-arn arn:aws:iam::aws:policy/AdministratorAccess",
            "boto3_commands": [{
            "service": "iam",
            "operation": "detach_user_policy",
            "params": {
                "UserName": "{user_name}",
                "PolicyArn": "arn:aws:iam::aws:policy/AdministratorAccess"
            }}],
        },

        
        {
            "step": 2,
            "description": "Attach ReadOnlyAccess managed policy to the user.",
            "command": f"aws iam attach-user-policy --user-name {user_name} --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess"
        },
        {
            "step": 3,
            "description": "Review and remove any inline policies that allow overly broad access.",
            "command": f"aws iam list-user-policies --user-name {user_name} && aws iam delete-user-policy --user-name {user_name} --policy-name <policy-name>"
        }
    ]
    finding = {
        "id": user_name,
        "title": "IAM User with Overly Permissive Permissions",
        "severity": "High",
        "description": f"IAM user {user_name} has admin-like or wildcard permissions.",
        "resource": user_name,
        "resource_type": "IAMUser",
        "compliance": ["SOC 2", "ISO 27001", "CIS Benchmark"],
        "remediation": {
            "title": "Apply principle of least privilege",
            "steps": steps
        },
        "estimatedCost": 0,
        "status": status,
        "detected_at": datetime.utcnow().isoformat()
    }
    return finding
findings = []
async def get_securiity_findings():    
    findings = []

    # 1) S3 buckets
    try:
        buckets =  s3.list_buckets().get("Buckets", [])
        for b in buckets:
            name = b.get("Name")
            # print("Checking S3 bucket:", name)
            f = await build_s3_bucket_finding(name)
            if f:
                findings.append(f)
    except Exception as e:
        print("S3 check failed:", e)

    # 2) Security groups
    try:
        sgs_resp = ec2.describe_security_groups()
        for sg in sgs_resp.get("SecurityGroups", []):
            f = await build_sg_finding(sg)
            if f:
                findings.append(f)
    except Exception as e:
        print("EC2 SG check failed:", e)

    # 3) IAM users
    try:
        users_resp = iam.list_users()
        for u in users_resp.get("Users", []):
            uname = u.get("UserName")
            print("Checking IAM user:", uname)
            f = await build_iam_user_finding(uname)
            if f:
                findings.append(f)
    except Exception as e:
        print("IAM check failed:", e)

    # Build summary counts
    summary = {
        "critical": sum(1 for f in findings if f["severity"].lower() == "critical"),
        "high": sum(1 for f in findings if f["severity"].lower() == "high"),
        "medium": sum(1 for f in findings if f["severity"].lower() == "medium"),
        "low": sum(1 for f in findings if f["severity"].lower() == "low"),
        "open": sum(1 for f in findings if f["status"].lower() == "open"),
        "in_progress": sum(1 for f in findings if f["status"].lower() == "in progress"),
        "fixed": sum(1 for f in findings if f["status"].lower() == "fixed")
    }

    return {"summary": summary, "findings": findings}

def get_finding_by_id(finding_id: str):
    """Return a specific finding by ID"""
    return next((f for f in mock_security_findings if f["id"] == finding_id), None)

## to update security finding status
async def update_finding(finding_id: str,new_status: str):
    """Update a finding with new data"""
    result = await get_securiity_findings()
    findings = result["findings"]
    for finding in findings:
        id=finding["id"]
        if id == finding_id:
            if finding["resource_type"]=="S3":
                bucket_name=finding["resource"]
                all_commands = []
                for step in finding["remediation"]["steps"]:
                    boto_cmds = step.get("boto3_commands", [])
                    resolved = replace_placeholders(boto_cmds, {"bucket_name": bucket_name})
                    all_commands.extend(resolved)
                
            if finding["resource_type"]=="SecurityGroup":
                sg_id=finding["resource"]
                all_commands = []
                for step in finding["remediation"]["steps"]:
                    boto_cmds = step.get("boto3_commands", [])
                    resolved = replace_placeholders(boto_cmds, {"sg_id": sg_id})
                    all_commands.extend(resolved)
            if finding["resource_type"]=="IAMUser":
                user_name=finding["resource"]
                print("Preparing to resolve IAM user remediation for:", user_name)
                all_commands = []
                for step in finding["remediation"]["steps"]:
                    boto_cmds = step.get("boto3_commands", [])
                    print("Boto3 commands for step:", boto_cmds)
                    resolved = replace_placeholders(boto_cmds, {"user_name": user_name})
                    all_commands.extend(resolved)
            print("Resolving AWS commands for remediation:", all_commands)
            await apply_aws_commands(all_commands)
            finding["status"]=new_status

            return finding
    return None

async def compute_dynamic_security_score():
    global findings

    # Fetch keys dynamically
    keys = await get_security_keys_dynamic()

    # 1) Count fixed findings
    fixed_findings = sum(1 for f in findings if f["status"] == "Fixed")
    open_findings = sum(1 for f in findings if f["status"] == "Open")

    # 2) Count fixed keys (Active = Fixed, Unused/Expired = Not fixed)
    fixed_keys = sum(1 for k in keys if k["status"] == "Active")

    # 3) Base score
    base_score = 60

    # +5 for each fixed finding
    score = base_score + (fixed_findings * 5)

    # +5 for each fixed (active) key
    score += fixed_keys * 5

    # -3 for each open critical issue
    critical_penalty = sum(
        1 for f in findings
        if f["severity"] == "Critical" and f["status"] == "Open"
    )
    score -= critical_penalty * 3

    # clamp 0–100
    score = max(0, min(100, score))

    print("Computed dynamic security score:", score)

    return {
        "current": score,
        "delta_week": score - 75,
        "industry_avg": 73,
        "weeklyData": mock_security_score["weeklyData"],
        "trend": mock_security_score["trend"]
    }

async def get_security_data():
    """Return comprehensive security data including keys, scores, and compliance"""
    return {
        "keys": await get_security_keys_dynamic(),
        "score":  await compute_dynamic_security_score(),
    }
