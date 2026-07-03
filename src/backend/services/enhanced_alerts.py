"""
Enhanced Alert Generation
--------------------------
Two modes:
1. REAL: Richer alerts from actual AWS resources (more checks per resource)
2. DEMO: Inject realistic incident cascades for hackathon demos

The demo scenarios are designed to showcase correlation — each scenario
produces 3-6 alerts that share a resource/tag/time window, so the
correlation engine groups them into one multi-alert incident with a
meaningful timeline.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import boto3
import random
import string


# ---------------------------------------------------------------------------
# Demo Scenario Definitions
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _offset_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


DEMO_SCENARIOS = {
    "iam_breach": {
        "name": "IAM Policy Change → Service Cascade",
        "description": "An IAM policy change breaks Lambda permissions, causing a cascade of failures across dependent services.",
        "alerts": [
            {
                "title": "IAM Policy Modified — Permissions Removed",
                "message": "Policy 'lambda-exec-policy' was modified. Actions s3:GetObject, dynamodb:Query were removed from role 'payment-service-role'.",
                "severity": "Critical",
                "category": "security",
                "source": "Security",
                "resource_type": "IAM",
                "affected_resources": ["payment-service-role"],
                "tags": {"Service": "payment-api", "Environment": "production", "Team": "backend"},
                "timestamp_offset_seconds": 300,
            },
            {
                "title": "Lambda Invocation Errors Spiked 500%",
                "message": "Function 'payment-processor' error rate jumped from 0.1% to 45% in the last 5 minutes. Primary error: AccessDeniedException when calling DynamoDB.",
                "severity": "Critical",
                "category": "performance",
                "source": "Performance",
                "resource_type": "Lambda",
                "affected_resources": ["payment-processor"],
                "tags": {"Service": "payment-api", "Environment": "production", "Team": "backend"},
                "timestamp_offset_seconds": 270,
            },
            {
                "title": "Lambda Duration P99 Exceeded Threshold",
                "message": "Function 'payment-processor' P99 latency is 28s (threshold: 5s). Retries are consuming concurrency.",
                "severity": "High",
                "category": "performance",
                "source": "Performance",
                "resource_type": "Lambda",
                "affected_resources": ["payment-processor"],
                "tags": {"Service": "payment-api", "Environment": "production", "Team": "backend"},
                "timestamp_offset_seconds": 240,
            },
            {
                "title": "DynamoDB Read Throttling Detected",
                "message": "Table 'payments' experiencing throttled reads — 150 throttled requests in 5 minutes. Likely caused by Lambda retry storm.",
                "severity": "High",
                "category": "performance",
                "source": "Performance",
                "resource_type": "DynamoDB",
                "affected_resources": ["payments"],
                "tags": {"Service": "payment-api", "Environment": "production", "Team": "backend"},
                "timestamp_offset_seconds": 180,
            },
            {
                "title": "CloudWatch Alarm Triggered — Payment API Error Rate",
                "message": "Alarm 'payment-api-errors' entered ALARM state. Threshold: >5% error rate over 5 minutes. Current: 43%.",
                "severity": "Critical",
                "category": "performance",
                "source": "Performance",
                "resource_type": "CloudWatch",
                "affected_resources": ["payment-api-errors"],
                "tags": {"Service": "payment-api", "Environment": "production", "Team": "backend"},
                "timestamp_offset_seconds": 120,
            },
            {
                "title": "S3 Access Denied Errors on Payment Logs",
                "message": "Bucket 'payment-audit-logs' returning 403 AccessDenied for PutObject from role 'payment-service-role'. 230 failed writes in 5 minutes.",
                "severity": "High",
                "category": "security",
                "source": "Security",
                "resource_type": "S3",
                "affected_resources": ["payment-audit-logs"],
                "tags": {"Service": "payment-api", "Environment": "production", "Team": "backend"},
                "timestamp_offset_seconds": 60,
            },
        ]
    },

    "cost_anomaly": {
        "name": "Cost Anomaly — Runaway Resources",
        "description": "A forgotten auto-scaling group scaled up aggressively, combined with undeleted snapshots and oversized RDS, creating a cost spike.",
        "alerts": [
            {
                "title": "EC2 Instance Count Anomaly Detected",
                "message": "Auto Scaling Group 'web-asg-prod' scaled from 2 to 18 instances in the last hour. Triggered by CPU alarm but CPU is only at 8% — possible alarm misconfiguration.",
                "severity": "High",
                "category": "cost",
                "source": "Cost",
                "resource_type": "EC2",
                "affected_resources": ["web-asg-prod"],
                "tags": {"Service": "web-app", "Environment": "production", "Owner": "devops"},
                "timestamp_offset_seconds": 600,
            },
            {
                "title": "Estimated Daily Spend Exceeded Budget",
                "message": "Current daily run rate: $847/day (budget: $200/day). Primary driver: EC2 on-demand instances in us-east-1. 16 extra m5.xlarge instances running.",
                "severity": "Critical",
                "category": "cost",
                "source": "Cost",
                "resource_type": "EC2",
                "affected_resources": ["web-asg-prod"],
                "tags": {"Service": "web-app", "Environment": "production", "Owner": "devops"},
                "timestamp_offset_seconds": 540,
            },
            {
                "title": "EBS Snapshot Accumulation — 340 Orphaned Snapshots",
                "message": "340 EBS snapshots found with no associated AMI or volume. Total size: 2.1 TB. Estimated waste: $105/month.",
                "severity": "Medium",
                "category": "cost",
                "source": "Cost",
                "resource_type": "EBS",
                "affected_resources": ["ebs-snapshots-orphaned"],
                "tags": {"Service": "web-app", "Environment": "production", "Owner": "devops"},
                "timestamp_offset_seconds": 480,
            },
            {
                "title": "RDS Instance Oversized for Workload",
                "message": "RDS 'web-db-prod' (db.r5.2xlarge, $780/month) averaged 6% CPU and 4GB of 64GB RAM used over 30 days. Recommend db.r5.large (saves $520/month).",
                "severity": "Medium",
                "category": "cost",
                "source": "Cost",
                "resource_type": "RDS",
                "affected_resources": ["web-db-prod"],
                "tags": {"Service": "web-app", "Environment": "production", "Owner": "devops"},
                "timestamp_offset_seconds": 420,
            },
            {
                "title": "NAT Gateway Data Transfer Spike",
                "message": "NAT Gateway 'nat-0abc123' processed 890GB outbound in the last 24 hours (normal: 50GB). Investigate potential data exfiltration or misconfigured S3 endpoint.",
                "severity": "High",
                "category": "cost",
                "source": "Cost",
                "resource_type": "VPC",
                "affected_resources": ["nat-0abc123"],
                "tags": {"Service": "web-app", "Environment": "production", "Owner": "devops"},
                "timestamp_offset_seconds": 360,
            },
        ]
    },

    "security_exposure": {
        "name": "S3 Data Exposure Incident",
        "description": "Public S3 bucket with sensitive data detected, combined with missing encryption, logging gaps, and overprivileged access.",
        "alerts": [
            {
                "title": "S3 Bucket Publicly Accessible",
                "message": "Bucket 'customer-data-export' has Block Public Access disabled and bucket policy allows s3:GetObject from principal '*'. Contains 12,400 objects.",
                "severity": "Critical",
                "category": "security",
                "source": "Security",
                "resource_type": "S3",
                "affected_resources": ["customer-data-export"],
                "tags": {"Service": "data-pipeline", "Environment": "production", "Owner": "data-team"},
                "timestamp_offset_seconds": 240,
            },
            {
                "title": "S3 Bucket Missing Server-Side Encryption",
                "message": "Bucket 'customer-data-export' has no default encryption configured. Objects may be stored unencrypted at rest.",
                "severity": "High",
                "category": "security",
                "source": "Security",
                "resource_type": "S3",
                "affected_resources": ["customer-data-export"],
                "tags": {"Service": "data-pipeline", "Environment": "production", "Owner": "data-team"},
                "timestamp_offset_seconds": 230,
            },
            {
                "title": "S3 Access Logging Not Enabled",
                "message": "Bucket 'customer-data-export' does not have server access logging enabled. Cannot audit who accessed the data during exposure window.",
                "severity": "High",
                "category": "security",
                "source": "Security",
                "resource_type": "S3",
                "affected_resources": ["customer-data-export"],
                "tags": {"Service": "data-pipeline", "Environment": "production", "Owner": "data-team"},
                "timestamp_offset_seconds": 220,
            },
            {
                "title": "IAM Role with Overly Broad S3 Permissions",
                "message": "Role 'data-pipeline-role' has s3:* on resource '*'. Should be scoped to specific buckets.",
                "severity": "High",
                "category": "security",
                "source": "Security",
                "resource_type": "IAM",
                "affected_resources": ["data-pipeline-role"],
                "tags": {"Service": "data-pipeline", "Environment": "production", "Owner": "data-team"},
                "timestamp_offset_seconds": 210,
            },
        ]
    },
}


def generate_demo_scenario_alerts(scenario_key: str) -> List[Dict[str, Any]]:
    """
    Generate alerts for a specific demo scenario.
    Returns alerts with realistic timestamps offset from now.
    """
    scenario = DEMO_SCENARIOS.get(scenario_key)
    if not scenario:
        return []

    alerts = []
    run_id = ''.join(random.choices(string.ascii_lowercase, k=4))

    for i, alert_def in enumerate(scenario["alerts"]):
        ts = _offset_iso(alert_def.get("timestamp_offset_seconds", 0))
        resource_id = alert_def["affected_resources"][0] if alert_def["affected_resources"] else "unknown"

        alert = {
            "id": f"demo-{scenario_key}-{resource_id}:{alert_def['title'].replace(' ', '~')}-{run_id}",
            "title": alert_def["title"],
            "message": alert_def["message"],
            "severity": alert_def["severity"],
            "source": alert_def["source"],
            "category": alert_def["category"],
            "affected_resources": alert_def["affected_resources"],
            "resource_type": alert_def["resource_type"],
            "region": "us-east-1",
            "tags": alert_def.get("tags", {}),
            "timestamp": ts,
            "status": "open",
            "impact": "high",
            "saving": "N/A",
            "manual_only": False,
            "solution_steps": [],
        }
        alerts.append(alert)

    return alerts


def get_available_scenarios() -> List[Dict[str, str]]:
    """Return list of available demo scenarios for the UI."""
    return [
        {
            "key": key,
            "name": scenario["name"],
            "description": scenario["description"],
            "alert_count": len(scenario["alerts"]),
        }
        for key, scenario in DEMO_SCENARIOS.items()
    ]


# ---------------------------------------------------------------------------
# Richer real-resource checks (Option A)
# ---------------------------------------------------------------------------

def generate_ec2_deep_alerts(instance: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Generate richer alerts for an EC2 instance beyond just 'idle'.
    These run against real CloudWatch data when available.
    """
    alerts = []
    resource_id = instance.get("resource_id")
    tags = instance.get("tags", {})
    region = instance.get("region", "us-east-1")
    now = _now_iso()

    metrics = instance.get("metrics", {})
    cpu_avg = metrics.get("cpu_avg", 0)
    network_in = metrics.get("network_in_avg", 0)
    config = instance.get("configuration", {})
    instance_type = config.get("instance_type", "unknown")
    monitoring = config.get("monitoring", "disabled")

    base = {
        "affected_resources": [resource_id],
        "resource_type": "EC2",
        "region": region,
        "tags": tags,
        "timestamp": now,
        "status": "open",
        "manual_only": False,
        "solution_steps": [],
    }

    # Check 1: Low CPU
    if cpu_avg < 10:
        alerts.append({
            **base,
            "id": f"{resource_id}:Low~CPU~Utilization~Detected",
            "title": "Low CPU Utilization Detected",
            "message": f"Instance {resource_id} ({instance_type}) averaged {cpu_avg:.1f}% CPU over the last 30 days. Consider downsizing or stopping.",
            "severity": "High",
            "source": "Cost",
            "category": "cost",
            "impact": "high",
            "saving": "30-60%",
        })

    # Check 2: Low network traffic (potential unused instance)
    if network_in < 1000:  # bytes/sec
        alerts.append({
            **base,
            "id": f"{resource_id}:Minimal~Network~Traffic",
            "title": "Minimal Network Traffic",
            "message": f"Instance {resource_id} has near-zero network traffic ({network_in:.0f} bytes/s avg). May be abandoned or misconfigured.",
            "severity": "Medium",
            "source": "Cost",
            "category": "cost",
            "impact": "medium",
            "saving": "100% if stopped",
        })

    # Check 3: Missing detailed monitoring
    if monitoring != "enabled":
        alerts.append({
            **base,
            "id": f"{resource_id}:Detailed~Monitoring~Not~Enabled",
            "title": "Detailed Monitoring Not Enabled",
            "message": f"Instance {resource_id} uses basic monitoring (5-min intervals). Enable detailed monitoring for 1-min metrics.",
            "severity": "Low",
            "source": "Performance",
            "category": "performance",
            "impact": "low",
            "saving": "N/A",
        })

    # Check 4: Old generation instance type
    old_gen_prefixes = ("t2.", "m4.", "c4.", "r4.", "m3.", "c3.")
    if any(instance_type.startswith(p) for p in old_gen_prefixes):
        alerts.append({
            **base,
            "id": f"{resource_id}:Old~Generation~Instance~Type",
            "title": "Old Generation Instance Type",
            "message": f"Instance {resource_id} runs {instance_type}. Migrating to current generation (t3/m5/c5) can save 10-40% with better performance.",
            "severity": "Medium",
            "source": "Cost",
            "category": "cost",
            "impact": "medium",
            "saving": "10-40%",
        })

    return alerts


def generate_s3_deep_alerts(bucket: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate richer alerts for an S3 bucket."""
    alerts = []
    resource_id = bucket.get("resource_id")
    tags = bucket.get("tags", {})
    region = bucket.get("region", "us-east-1")
    now = _now_iso()
    config = bucket.get("configuration", {})

    base = {
        "affected_resources": [resource_id],
        "resource_type": "S3",
        "region": region,
        "tags": tags,
        "timestamp": now,
        "status": "open",
        "manual_only": False,
        "solution_steps": [],
    }

    # Check: versioning
    if not config.get("versioning_enabled"):
        alerts.append({
            **base,
            "id": f"{resource_id}:Versioning~Not~Enabled",
            "title": "S3 Versioning Not Enabled",
            "message": f"Bucket '{resource_id}' does not have versioning enabled. Data cannot be recovered if accidentally deleted.",
            "severity": "Medium",
            "source": "Security",
            "category": "resilience",
            "impact": "medium",
            "saving": "N/A",
        })

    # Check: encryption
    if not config.get("encryption_enabled"):
        alerts.append({
            **base,
            "id": f"{resource_id}:Encryption~Not~Configured",
            "title": "S3 Encryption Not Configured",
            "message": f"Bucket '{resource_id}' has no default server-side encryption. Objects may be stored unencrypted.",
            "severity": "High",
            "source": "Security",
            "category": "security",
            "impact": "high",
            "saving": "N/A",
        })

    # Check: public access
    if not config.get("public_access_blocked"):
        alerts.append({
            **base,
            "id": f"{resource_id}:Public~Access~Not~Blocked",
            "title": "S3 Public Access Not Fully Blocked",
            "message": f"Bucket '{resource_id}' does not have all Block Public Access settings enabled.",
            "severity": "Critical",
            "source": "Security",
            "category": "security",
            "impact": "critical",
            "saving": "N/A",
        })

    # Check: lifecycle policy
    if not config.get("lifecycle_rules"):
        alerts.append({
            **base,
            "id": f"{resource_id}:No~Lifecycle~Policy",
            "title": "No S3 Lifecycle Policy",
            "message": f"Bucket '{resource_id}' has no lifecycle policy. Old objects never transition to cheaper storage classes.",
            "severity": "Low",
            "source": "Cost",
            "category": "cost",
            "impact": "low",
            "saving": "10-30% on storage",
        })

    return alerts