# Mock data for Security features
import boto3
import json
from datetime import datetime, timezone

from botocore.exceptions import ClientError
from aws.util import apply_aws_commands


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
    """Fetch all IAM access keys with permission analysis and rotation tracking"""
    all_keys = []
    print("Fetching IAM access keys...")
 
    users_resp = iam.list_users()
 
    for user in users_resp["Users"]:
        user_name = user["UserName"]
 
        # Get access keys for user
        access_keys = iam.list_access_keys(UserName=user_name)["AccessKeyMetadata"]
 
        # Get user's attached policies (for permission analysis)
        attached_policies = iam.list_attached_user_policies(UserName=user_name).get("AttachedPolicies", [])
        policy_names = [p["PolicyName"] for p in attached_policies]
        
        # Flag overprivileged users
        is_overprivileged = any(
            "admin" in p.lower() or p == "AdministratorAccess" 
            for p in policy_names
        )
 
        for k in access_keys:
            key_id = k["AccessKeyId"]
            created_date = k["CreateDate"].replace(tzinfo=timezone.utc)
            days_since_created = (datetime.now(timezone.utc) - created_date).days
 
            # ---- GET LAST USED ----
            last_used_info = iam.get_access_key_last_used(AccessKeyId=key_id)
            last_used = last_used_info["AccessKeyLastUsed"].get("LastUsedDate")
 
            if last_used:
                last_used_utc = last_used.replace(tzinfo=timezone.utc)
                days_since_last_used = (datetime.now(timezone.utc) - last_used_utc).days
                last_used_str = last_used_utc.isoformat()
            else:
                days_since_last_used = 999
                last_used_str = "Never"
 
            # ---- ROTATION STATUS ----
            if days_since_created > 90:
                rotation_status = "Overdue"
                severity = "High"
            elif days_since_created > 60:
                rotation_status = "Due Soon"
                severity = "Medium"
            elif days_since_created < 30:
                rotation_status = "Recently Rotated"
                severity = "Low"
            else:
                rotation_status = "OK"
                severity = "Low"
 
            # ---- STATUS LOGIC ----
            if last_used_str == "Never":
                status = "Unused"
                severity = "High"  # Unused keys are security risks
            elif days_since_last_used > 90:
                status = "Unused"
                severity = "High"
            elif days_since_created > 90:
                status = "Needs Rotation"
                severity = "High"
            else:
                status = "Active"
 
            # ---- ISSUES (list of specific problems) ----
            issues = []
            if days_since_created > 90:
                issues.append(f"Key is {days_since_created} days old (rotate every 90 days)")
            if days_since_last_used > 90 and last_used_str != "Never":
                issues.append(f"Not used in {days_since_last_used} days (consider deleting)")
            if last_used_str == "Never":
                issues.append("Key has never been used (delete if unnecessary)")
            if is_overprivileged:
                issues.append(f"User has admin-level permissions ({', '.join(policy_names[:2])})")
 
            # ---- RECOMMENDATIONS ----
            recommendations = []
            if days_since_created > 90:
                recommendations.append({
                    "action": "rotate",
                    "title": "Rotate Access Key",
                    "description": "Create new key, update applications, deactivate old key",
                    "priority": "High"
                })
            if last_used_str == "Never" or days_since_last_used > 90:
                recommendations.append({
                    "action": "delete",
                    "title": "Delete Unused Key",
                    "description": "This key hasn't been used recently and can likely be deleted",
                    "priority": "Medium"
                })
            if is_overprivileged:
                recommendations.append({
                    "action": "scope_down",
                    "title": "Reduce Permissions",
                    "description": f"User has {', '.join(policy_names)}. Review if admin access is necessary.",
                    "priority": "High"
                })
 
            all_keys.append({
                "id": key_id,
                "name": f"IAM Access Key",
                "user": user_name,
                "type": "Access Key",
                "provider": "AWS IAM",
                "createdDate": created_date.isoformat(),
                "ageInDays": days_since_created,
                "lastUsed": last_used_str,
                "daysSinceLastUsed": days_since_last_used if last_used_str != "Never" else None,
                "rotationStatus": rotation_status,
                "status": status,
                "severity": severity,
                "policies": policy_names,
                "isOverprivileged": is_overprivileged,
                "issues": issues,
                "recommendations": recommendations,
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
        "keys": await get_security_keys_and_certs(),  # Changed from get_security_keys_dynamic()
        "score": await compute_dynamic_security_score(),
    }

# ADD THESE FUNCTIONS TO YOUR EXISTING aws/security.py FILE
# They work alongside your existing get_security_keys_dynamic() function

async def fetch_acm_certificates(region="us-east-1"):
    """Fetch ACM SSL/TLS certificates with expiry tracking"""
    all_certs = []
    
    acm_client = boto3.client("acm", region_name=region)
    
    try:
        certs_resp = acm_client.list_certificates(CertificateStatuses=["ISSUED"])
        
        for cert_summary in certs_resp.get("CertificateSummaryList", []):
            cert_arn = cert_summary["CertificateArn"]
            
            # Get detailed cert info
            cert_detail = acm_client.describe_certificate(CertificateArn=cert_arn)["Certificate"]
            
            domain_name = cert_detail.get("DomainName", "Unknown")
            not_after = cert_detail.get("NotAfter")  # Expiry date
            not_before = cert_detail.get("NotBefore")  # Issue date
            
            if not_after:
                not_after_utc = not_after.replace(tzinfo=timezone.utc)
                days_until_expiry = (not_after_utc - datetime.now(timezone.utc)).days
            else:
                days_until_expiry = 999
            
            if not_before:
                not_before_utc = not_before.replace(tzinfo=timezone.utc)
                cert_age_days = (datetime.now(timezone.utc) - not_before_utc).days
            else:
                cert_age_days = 0
            
            # Determine status and severity
            if days_until_expiry < 0:
                status = "Expired"
                severity = "Critical"
            elif days_until_expiry < 30:
                status = "Expiring Soon"
                severity = "High"
            elif days_until_expiry < 60:
                status = "Nearing Expiry"
                severity = "Medium"
            else:
                status = "Valid"
                severity = "Low"
            
            # Check if auto-renew is enabled (for ACM-managed certs with validation)
            renewal_eligibility = cert_detail.get("RenewalEligibility", "INELIGIBLE")
            auto_renew_enabled = renewal_eligibility == "ELIGIBLE"
            
            # Build issues list
            issues = []
            if days_until_expiry < 60 and not auto_renew_enabled:
                issues.append(f"Certificate expires in {days_until_expiry} days and auto-renew is not enabled")
            if days_until_expiry < 0:
                issues.append("Certificate has expired")
            if cert_age_days > 365:
                issues.append(f"Certificate is {cert_age_days} days old (consider rotating)")
            
            # Recommendations
            recommendations = []
            if days_until_expiry < 60:
                recommendations.append({
                    "action": "renew",
                    "title": "Renew Certificate",
                    "description": "ACM certificates can be renewed automatically if DNS validation is configured",
                    "priority": "High" if days_until_expiry < 30 else "Medium"
                })
            if not auto_renew_enabled:
                recommendations.append({
                    "action": "enable_auto_renew",
                    "title": "Enable Auto-Renewal",
                    "description": "Configure DNS validation to enable automatic renewal",
                    "priority": "Medium"
                })
            
            all_certs.append({
                "id": cert_arn,
                "name": f"SSL Certificate: {domain_name}",
                "domain": domain_name,
                "type": "SSL/TLS Certificate",
                "provider": "AWS ACM",
                "issuedDate": not_before.isoformat() if not_before else None,
                "expiryDate": not_after.isoformat() if not_after else None,
                "daysUntilExpiry": days_until_expiry,
                "ageInDays": cert_age_days,
                "status": status,
                "severity": severity,
                "autoRenewEnabled": auto_renew_enabled,
                "issues": issues,
                "recommendations": recommendations,
            })
    
    except Exception as e:
        print(f"Error fetching ACM certificates: {e}")
    
    return all_certs


async def get_security_keys_and_certs(region="us-east-1"):
    """Fetch all security keys and certificates"""
    iam_keys = await fetch_iam_access_keys()
    acm_certs = await fetch_acm_certificates(region)
    
    all_items = iam_keys + acm_certs
    
    # Summary stats
    summary = {
        "total": len(all_items),
        "critical": sum(1 for item in all_items if item["severity"] == "Critical"),
        "high": sum(1 for item in all_items if item["severity"] == "High"),
        "medium": sum(1 for item in all_items if item["severity"] == "Medium"),
        "low": sum(1 for item in all_items if item["severity"] == "Low"),
        "needsRotation": sum(1 for item in all_items if item.get("rotationStatus") in ["Overdue", "Due Soon"]),
        "unused": sum(1 for item in all_items if item.get("status") == "Unused"),
        "overprivileged": sum(1 for item in all_items if item.get("isOverprivileged")),
    }
    
    return {
        "items": all_items,
        "summary": summary
    }


async def rotate_iam_access_key(key_id: str, user_name: str):
    """Create new key, return it to user, mark old key as inactive"""
    
    # Create new key
    new_key_resp = iam.create_access_key(UserName=user_name)
    new_key = new_key_resp["AccessKey"]
    
    # Mark old key as inactive (don't delete yet - give user time to update apps)
    iam.update_access_key(
        UserName=user_name,
        AccessKeyId=key_id,
        Status="Inactive"
    )
    
    return {
        "status": "rotated",
        "newKeyId": new_key["AccessKeyId"],
        "newSecretKey": new_key["SecretAccessKey"],
        "oldKeyId": key_id,
        "oldKeyStatus": "Inactive",
        "message": f"New key created. Update your applications with the new key, then delete the old key ({key_id}).",
        "nextSteps": [
            "Update applications/services with new access key",
            "Test that new key works",
            "Delete old key after 7 days"
        ]
    }


async def delete_iam_access_key(key_id: str, user_name: str):
    """Delete an IAM access key"""
    iam.delete_access_key(UserName=user_name, AccessKeyId=key_id)
    return {
        "status": "deleted",
        "message": f"Access key {key_id} deleted successfully"
    }