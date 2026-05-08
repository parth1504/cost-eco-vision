import logging

# Initialize logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from typing import Dict, Any, List, Optional
from services.description_cache import get_description

# All current rules use static descriptions — they're boilerplate that
# doesn't depend on per-resource context. The LLM path remains available
# via `get_description(prompt=...)` for any future rule that needs it.
DESCRIPTIONS = {
    "dynamodb.pitr_disabled": (
        "Point-in-Time Recovery is disabled on this DynamoDB table. PITR lets "
        "you restore the table to any second in the last 35 days, protecting "
        "against accidental writes, deletes, or data corruption. It's a "
        "one-line fix and adds minimal cost."
    ),
    "dynamodb.encryption_disabled": (
        "This DynamoDB table doesn't have customer-managed KMS encryption "
        "enabled. While AWS-owned keys provide baseline encryption, KMS-based "
        "SSE gives you key rotation, audit logs, and compliance-friendly key "
        "management — a hard requirement for SOC2, PCI-DSS, and HIPAA."
    ),
    "dynamodb.underutilized": (
        "This provisioned-mode DynamoDB table is consistently using only a "
        "small fraction of its provisioned capacity. Switching to on-demand "
        "billing eliminates capacity planning entirely and charges only for "
        "what's actually consumed — almost always cheaper for tables with "
        "low or unpredictable traffic."
    ),
    "dynamodb.overutilized": (
        "This DynamoDB table is operating near its provisioned capacity "
        "ceiling. Sustained high utilization causes throttling, which "
        "manifests to users as failed requests. Increasing provisioned "
        "capacity (or switching to on-demand billing) restores headroom."
    ),
    "dynamodb.idle": (
        "This DynamoDB table has had effectively zero read/write activity. "
        "If it's no longer in use, deleting it eliminates ongoing cost. If "
        "it's a backup or seasonal table, document the intent so it doesn't "
        "get re-flagged on every scan."
    ),
}


def generate_dynamodb_recommendations(resource):
    """
    Rule-based DynamoDB recommendation generator.

    Conventions enforced here:
      - Config booleans default to None (unknown). Rules fire only on
        explicit `False`, so a missing/failed config check never produces a
        spurious recommendation.
      - Real table name is inlined into boto3_sequence params. The previous
        `"{TABLE_NAME}"` placeholder was never substituted on the alert-apply
        path → Apply Fix sent the literal string to AWS and 400'd.
      - Sizing rules have precedence: Idle suppresses Underutilized
        (subset of conditions). Overutilized is mutually-exclusive with the
        others by its threshold so no extra gating needed.
      - Recommendations whose boto3_sequence cannot be safely auto-applied
        (e.g. Idle = "review and consider deletion") carry `manual_only:
        True`; the alert handler refuses to execute them.
    """
    logger.info("Generating DynamoDB recommendations for resource: %s", resource)
    from datetime import datetime, timedelta

    recommendations: List[Dict[str, Any]] = []

    # --- Extract values safely ---
    metrics = resource.get("metrics", {}) or {}
    config = resource.get("config", {}) or {}
    metadata = resource.get("metadata", {}) or {}

    read_usage = metrics.get("read_capacity_used", 0) or 0
    write_usage = metrics.get("write_capacity_used", 0) or 0

    # None = unknown. Rules check `is False` so unknown never fires.
    pitr_enabled = config.get("pitr_enabled")
    encryption_enabled = config.get("encryption_enabled")
    billing_mode = config.get("billing_mode", "PAY_PER_REQUEST")
    provisioned_rcu = config.get("provisioned_rcu", 0) or 0
    provisioned_wcu = config.get("provisioned_wcu", 0) or 0

    # Use the real table name everywhere — the placeholder never got
    # substituted on the apply path.
    table_name = resource.get("name") or resource.get("resource_id") or ""
    monthly_cost = resource.get("monthly_cost", 0) or 0

    # NOTE: the "< 2 days old" safety guard has been removed so freshly-
    # imported tables surface recommendations immediately.


    # Track which "size" decision we've already produced so we don't emit
    # contradictory recommendations on the same table.
    size_decision_made = False

    # --- RULE 1: PITR (independent of sizing) ---
    if pitr_enabled is False:
        description = get_description(
            "dynamodb.pitr_disabled",
            prompt="Explain why enabling Point-in-Time Recovery (PITR) is critical for DynamoDB data protection.",
            static_text=DESCRIPTIONS["dynamodb.pitr_disabled"],
        )
        recommendations.append({
            "title": "Enable Point-in-Time Recovery (PITR)",
            "description": description,
            "type": "security",
            "severity": "critical",
            "saving": "N/A",
            "issue": "PITR disabled",
            "impact": "high",
            "status": "active",
            "solution_steps": [
                {
                    "step": 1,
                    "command": f"aws dynamodb update-continuous-backups --table-name {table_name} --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true",
                    "description": "Enable PITR for continuous backups.",
                }
            ],
            "boto3_sequence": [
                {
                    "service": "dynamodb",
                    "operation": "update_continuous_backups",
                    "params": {
                        "TableName": table_name,
                        "PointInTimeRecoverySpecification": {
                            "PointInTimeRecoveryEnabled": True
                        },
                    },
                }
            ],
            "confidence": 0.9,
            "reasoning": {
                "read_usage": read_usage,
                "write_usage": write_usage,
                "decision": "PITR disabled",
            },
        })

    # --- RULE 2: ENCRYPTION (independent of sizing) ---
    if encryption_enabled is False:
        description = get_description(
            "dynamodb.encryption_disabled",
            prompt="Explain why enabling encryption at rest is important for DynamoDB security.",
            static_text=DESCRIPTIONS["dynamodb.encryption_disabled"],
        )
        recommendations.append({
            "title": "Enable DynamoDB Encryption",
            "description": description,
            "type": "security",
            "severity": "high",
            "saving": "N/A",
            "issue": "Encryption disabled",
            "impact": "high",
            "status": "active",
            "solution_steps": [
                {
                    "step": 1,
                    "command": f"aws dynamodb update-table --table-name {table_name} --sse-specification Enabled=true,SSEType=KMS",
                    "description": "Enable KMS encryption.",
                }
            ],
            "boto3_sequence": [
                {
                    "service": "dynamodb",
                    "operation": "update_table",
                    "params": {
                        "TableName": table_name,
                        "SSESpecification": {
                            "Enabled": True,
                            "SSEType": "KMS",
                        },
                    },
                }
            ],
            "confidence": 0.8,
            "reasoning": {
                "read_usage": read_usage,
                "write_usage": write_usage,
                "decision": "Encryption disabled",
            },
        })

    # --- SIZING RULES (with precedence Idle > Underutilized) ---

    # RULE 5: IDLE TABLE — strongest signal, suppresses Underutilized.
    # Marked manual_only because deletion shouldn't be auto-executed.
    if read_usage < 1 and write_usage < 1:
        size_decision_made = True
        description = get_description(
            "dynamodb.idle",
            prompt="Explain why an idle DynamoDB table should be reviewed or removed to save cost.",
            static_text=DESCRIPTIONS["dynamodb.idle"],
        )
        recommendations.append({
            "title": "Idle Table Detected — Review or Remove",
            "description": description,
            "type": "cost",
            "severity": "medium",
            "saving": monthly_cost,
            "issue": "No meaningful usage detected",
            "impact": "medium",
            "status": "active",
            "manual_only": True,  # deletion = human decision
            "solution_steps": [
                {
                    "step": 1,
                    "command": "Review table usage and consider deletion if not needed",
                    "description": "Manual validation required before deletion.",
                }
            ],
            "boto3_sequence": [],
            "confidence": 0.9,
            "reasoning": {
                "read_usage": read_usage,
                "write_usage": write_usage,
                "decision": "Idle table",
            },
        })

    # RULE 3: UNDERUTILIZED — only if Idle didn't already fire.
    if (
        not size_decision_made
        and billing_mode == "PROVISIONED"
        and read_usage < 20
        and write_usage < 20
    ):
        size_decision_made = True
        estimated_saving = round(monthly_cost * 0.4, 2)
        description = get_description(
            "dynamodb.underutilized",
            prompt=(
                f"Explain why a DynamoDB table with low read ({read_usage}%) and "
                f"write ({write_usage}%) usage should switch to on-demand billing."
            ),
            static_text=DESCRIPTIONS["dynamodb.underutilized"],
        )
        recommendations.append({
            "title": "Underutilized Table — Switch to On-Demand",
            "description": description,
            "type": "cost",
            "severity": "warning",
            "saving": estimated_saving,
            "issue": "Low capacity usage",
            "impact": "medium",
            "status": "active",
            "solution_steps": [
                {
                    "step": 1,
                    "command": f"aws dynamodb update-table --table-name {table_name} --billing-mode PAY_PER_REQUEST",
                    "description": "Switch to on-demand billing mode.",
                }
            ],
            "boto3_sequence": [
                {
                    "service": "dynamodb",
                    "operation": "update_table",
                    "params": {
                        "TableName": table_name,
                        "BillingMode": "PAY_PER_REQUEST",
                    },
                }
            ],
            "confidence": 0.8,
            "reasoning": {
                "read_usage": read_usage,
                "write_usage": write_usage,
                "decision": "Underutilized provisioned table",
            },
        })

    # RULE 4: OVERUTILIZED — capacity targets computed from CURRENT
    # provisioned units, not from the percentage (the previous version's
    # bug treated 85% as 85 RCUs, producing nonsense scale targets).
    if billing_mode == "PROVISIONED" and (read_usage > 80 or write_usage > 80):
        # Use a sensible floor of 10 if we somehow have provisioned=0.
        new_rcu = max(int((provisioned_rcu or 5) * 1.5), 10)
        new_wcu = max(int((provisioned_wcu or 5) * 1.5), 10)

        description = get_description(
            "dynamodb.overutilized",
            prompt=(
                f"Explain why a DynamoDB table with high usage (read {read_usage}%, "
                f"write {write_usage}%) needs scaling."
            ),
            static_text=DESCRIPTIONS["dynamodb.overutilized"],
        )
        recommendations.append({
            "title": "Overutilized Table — Scale Capacity",
            "description": description,
            "type": "performance",
            "severity": "high",
            "saving": "N/A",
            "issue": "High capacity utilization",
            "impact": "high",
            "status": "active",
            "solution_steps": [
                {
                    "step": 1,
                    "command": f"aws dynamodb update-table --table-name {table_name} --provisioned-throughput ReadCapacityUnits={new_rcu},WriteCapacityUnits={new_wcu}",
                    "description": f"Increase provisioned capacity to RCU={new_rcu}, WCU={new_wcu} (1.5× current).",
                }
            ],
            "boto3_sequence": [
                {
                    "service": "dynamodb",
                    "operation": "update_table",
                    "params": {
                        "TableName": table_name,
                        "ProvisionedThroughput": {
                            "ReadCapacityUnits": new_rcu,
                            "WriteCapacityUnits": new_wcu,
                        },
                    },
                }
            ],
            "confidence": 0.8,
            "reasoning": {
                "read_usage": read_usage,
                "write_usage": write_usage,
                "current_rcu": provisioned_rcu,
                "current_wcu": provisioned_wcu,
                "decision": "Overutilized table",
            },
        })

    logger.info("Finished generating DynamoDB recommendations")
    return recommendations
