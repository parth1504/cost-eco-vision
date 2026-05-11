"""
Compliance scoring via AWS Security Hub.

Replaces the naive "fixed/open ratio of locally-tagged findings" with real,
auditable scores: each enabled Security Hub standard (CIS, AWS FSBP, PCI,
NIST, etc.) has its own catalog of controls, and Security Hub continuously
evaluates them against your AWS account. We aggregate the latest finding per
control to produce per-framework pass rates.

If Security Hub isn't enabled in the account, returns a structured "not
enabled" response so the UI can prompt the user with the one-line CLI to
enable it. We do NOT fall back to fake scores — fake compliance is worse
than no compliance.
"""

from collections import defaultdict
from typing import Any, Dict, List

import boto3
from botocore.exceptions import ClientError

# Friendly labels for the noisy ARNs Security Hub returns. Add more as needed.
_STANDARD_FRIENDLY_NAMES = {
    "ruleset/cis-aws-foundations-benchmark/v/1.2.0": "CIS AWS Foundations 1.2",
    "standard/cis-aws-foundations-benchmark/v/1.4.0": "CIS AWS Foundations 1.4",
    "standard/aws-foundational-security-best-practices/v/1.0.0": "AWS Foundational Security Best Practices",
    "standard/pci-dss/v/3.2.1": "PCI DSS 3.2.1",
    "standard/nist-800-53/v/5.0.0": "NIST 800-53 Rev. 5",
    "standard/service-managed-aws-control-tower/v/1.0.0": "AWS Control Tower",
}

# FAILED is worse than WARNING is worse than PASSED is worse than missing data.
_STATUS_RANK = {"FAILED": 3, "WARNING": 2, "PASSED": 1, "NOT_AVAILABLE": 0}


def _friendly_name(standards_arn: str) -> str:
    """Pull a readable name out of a Security Hub standards ARN."""
    if not standards_arn:
        return "Unknown standard"
    for suffix, label in _STANDARD_FRIENDLY_NAMES.items():
        if standards_arn.endswith(suffix):
            return label
    # Fallback: use the last two ARN segments.
    parts = standards_arn.rstrip("/").split("/")
    return "/".join(parts[-3:-1]) if len(parts) >= 3 else parts[-1]


def _is_worse(new: str, current: str) -> bool:
    return _STATUS_RANK.get(new, 0) > _STATUS_RANK.get(current, 0)


def _client(region: str | None = None):
    return boto3.client("securityhub", region_name=region) if region else boto3.client("securityhub")


def get_compliance_summary(region: str | None = None) -> Dict[str, Any]:
    """
    Return per-standard compliance scores from AWS Security Hub.

    Shape:
        {
          "enabled": True,
          "standards": [
            {"framework": "CIS AWS Foundations 1.4", "score": 78,
             "passed": 39, "failed": 11, "total_controls": 50,
             "standards_arn": "arn:aws:..."},
            ...
          ]
        }

    Or, if Security Hub isn't enabled:
        {
          "enabled": False,
          "message": "...",
          "enable_command": "aws securityhub enable-security-hub"
        }
    """
    sh = _client(region)

    # 1. Which standards are enabled?
    try:
        subs = sh.get_enabled_standards().get("StandardsSubscriptions", [])
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        print(f"Error checking Security Hub standards: {e}")
        return {
            "enabled": False,
            "message": (
                "AWS Security Hub is not enabled in this account/region. "
                "Enable it once and Security Hub will start evaluating your "
                "AWS resources against compliance standards (takes ~24h to "
                "fully populate)."
            ),
            "enable_command": (
                "aws securityhub enable-security-hub "
                "--enable-default-standards"
            ),
            "standards": [],
        }

    if not subs:
        return {
            "enabled": True,
            "message": (
                "Security Hub is enabled but no standards are subscribed. "
                "Subscribe to a standard (e.g. AWS Foundational Security Best "
                "Practices) to get compliance scores."
            ),
            "standards": [],
        }

    # 2. Walk findings, take the worst-status finding per (standard, control).
    # This collapses many findings (one per resource, per control) into one
    # status per control, which is what determines whether the control "passes".
    control_status: Dict[str, Dict[str, str]] = defaultdict(dict)

    paginator = sh.get_paginator("get_findings")
    page_count = 0
    for page in paginator.paginate(
        Filters={
            "WorkflowStatus": [
                {"Value": "NEW", "Comparison": "EQUALS"},
                {"Value": "NOTIFIED", "Comparison": "EQUALS"},
                {"Value": "RESOLVED", "Comparison": "EQUALS"},
            ],
            "RecordState": [{"Value": "ACTIVE", "Comparison": "EQUALS"}],
        },
        PaginationConfig={"MaxItems": 5000, "PageSize": 100},
    ):
        for f in page.get("Findings", []):
            pf = f.get("ProductFields", {})
            # Different SH versions populate different ProductFields keys —
            # try a few in priority order.
            standards_arn = (
                pf.get("StandardsArn")
                or pf.get("aws/securityhub/StandardsArn")
                or _standards_arn_from_control(pf.get("StandardsControlArn", ""))
            )
            control_id = (
                pf.get("ControlId")
                or pf.get("aws/securityhub/ControlId")
                or pf.get("StandardsControlArn", "").rsplit("/", 1)[-1]
            )
            comp_status = f.get("Compliance", {}).get("Status")

            if not (standards_arn and control_id and comp_status):
                continue
            existing = control_status[standards_arn].get(control_id)
            if existing is None or _is_worse(comp_status, existing):
                control_status[standards_arn][control_id] = comp_status

        page_count += 1
        if page_count > 50:  # belt-and-suspenders cap
            break

    # 3. Score each enabled standard.
    results: List[Dict[str, Any]] = []
    for sub in subs:
        standards_arn = sub.get("StandardsArn", "")
        controls = control_status.get(standards_arn, {})

        passed = sum(1 for v in controls.values() if v == "PASSED")
        failed = sum(1 for v in controls.values() if v in ("FAILED", "WARNING"))
        total = passed + failed
        score = round((passed / total) * 100) if total else None

        results.append({
            "framework": _friendly_name(standards_arn),
            "standards_arn": standards_arn,
            "subscription_arn": sub.get("StandardsSubscriptionArn"),
            "subscription_status": sub.get("StandardsStatus"),  # READY / PENDING / etc.
            "score": score,
            "passed": passed,
            "failed": failed,
            "total_controls": total,
        })

    # Sort by score desc; standards still warming up (score=None) at the bottom.
    results.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))
    return {"enabled": True, "standards": results}


def _standards_arn_from_control(control_arn: str) -> str:
    """
    StandardsControlArn looks like:
      arn:aws:securityhub:us-east-1:123:control/cis-aws-foundations-benchmark/v/1.4.0/CloudTrail.1
    The standards ARN has the same prefix without the trailing control id.
    """
    if not control_arn:
        return ""
    parts = control_arn.rsplit("/", 1)
    return parts[0] if len(parts) == 2 else ""
