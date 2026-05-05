import logging

# Initialize logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from typing import Dict, Any, List, Optional
from agent.llm.llm_client import get_llm_client

def generate_dynamodb_recommendations(resource):
    logger.info("Generating DynamoDB recommendations for resource: %s", resource)
    from datetime import datetime, timedelta

    recommendations = []

    # --- Extract values safely ---
    metrics = resource.get("metrics", {})
    config = resource.get("config", {})
    metadata = resource.get("metadata", {})

    read_usage = metrics.get("read_capacity_used", 0)
    write_usage = metrics.get("write_capacity_used", 0)

    pitr_enabled = config.get("pitr_enabled", True)
    encryption_enabled = config.get("encryption_enabled", True)
    billing_mode = config.get("billing_mode", "PAY_PER_REQUEST")

    table_name = "{TABLE_NAME}"
    monthly_cost = resource.get("monthly_cost", 0)

    # --- Safety: skip very new tables ---
    creation_date = metadata.get("creation_date")
    if creation_date:
        try:
            created = datetime.fromisoformat(creation_date.replace("Z", ""))
            if datetime.utcnow() - created < timedelta(days=2):
                return []
        except Exception:
            pass

    llm = get_llm_client()

    # --- RULE 1: PITR ---
    if not pitr_enabled:
        confidence = 0.9

        description = llm.generate(
            "Explain why enabling Point-in-Time Recovery (PITR) is critical for DynamoDB data protection."
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
                    "command": "aws dynamodb update-continuous-backups --table-name {TABLE_NAME} --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true",
                    "description": "Enable PITR for continuous backups."
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
                        }
                    }
                }
            ],
            "confidence": confidence,
            "reasoning": {
                "read_usage": read_usage,
                "write_usage": write_usage,
                "decision": "PITR disabled"
            }
        })

    # --- RULE 2: ENCRYPTION ---
    if not encryption_enabled:
        confidence = 0.8

        description = llm.generate(
            "Explain why enabling encryption at rest is important for DynamoDB security."
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
                    "command": "aws dynamodb update-table --table-name {TABLE_NAME} --sse-specification Enabled=true,SSEType=KMS",
                    "description": "Enable KMS encryption."
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
                            "SSEType": "KMS"
                        }
                    }
                }
            ],
            "confidence": confidence,
            "reasoning": {
                "read_usage": read_usage,
                "write_usage": write_usage,
                "decision": "Encryption disabled"
            }
        })

    # --- RULE 3: UNDERUTILIZED PROVISIONED ---
    if billing_mode == "PROVISIONED" and read_usage < 20 and write_usage < 20:
        confidence = min(1.0, 0.5 + 0.3 + 0.2)

        estimated_saving = round(monthly_cost * 0.4, 2)

        description = llm.generate(
            f"Explain why a DynamoDB table with low read ({read_usage}%) and write ({write_usage}%) usage should switch to on-demand billing."
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
                    "command": "aws dynamodb update-table --table-name {TABLE_NAME} --billing-mode PAY_PER_REQUEST",
                    "description": "Switch to on-demand billing mode."
                }
            ],
            "boto3_sequence": [
                {
                    "service": "dynamodb",
                    "operation": "update_table",
                    "params": {
                        "TableName": table_name,
                        "BillingMode": "PAY_PER_REQUEST"
                    }
                }
            ],
            "confidence": confidence,
            "reasoning": {
                "read_usage": read_usage,
                "write_usage": write_usage,
                "decision": "Underutilized provisioned table"
            }
        })

    # --- RULE 4: OVERUTILIZED ---
    if read_usage > 80 or write_usage > 80:
        confidence = min(1.0, 0.5 + 0.3)

        description = llm.generate(
            f"Explain why a DynamoDB table with high usage (read {read_usage}%, write {write_usage}%) needs scaling."
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
                    "command": "aws dynamodb update-table --table-name {TABLE_NAME} --provisioned-throughput ReadCapacityUnits=...,WriteCapacityUnits=...",
                    "description": "Increase provisioned capacity."
                }
            ],
            "boto3_sequence": [
                {
                    "service": "dynamodb",
                    "operation": "update_table",
                    "params": {
                        "TableName": table_name,
                        "ProvisionedThroughput": {
                            "ReadCapacityUnits": int(read_usage * 1.5) or 10,
                            "WriteCapacityUnits": int(write_usage * 1.5) or 10
                        }
                    }
                }
            ],
            "confidence": confidence,
            "reasoning": {
                "read_usage": read_usage,
                "write_usage": write_usage,
                "decision": "Overutilized table"
            }
        })

    # --- RULE 5: IDLE TABLE ---
    if read_usage < 1 and write_usage < 1:
        confidence = min(1.0, 0.6 + 0.3)

        description = llm.generate(
            "Explain why an idle DynamoDB table should be reviewed or removed to save cost."
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
            "solution_steps": [
                {
                    "step": 1,
                    "command": "Review table usage and consider deletion if not needed",
                    "description": "Manual validation required before deletion."
                }
            ],
            "boto3_sequence": [],
            "confidence": confidence,
            "reasoning": {
                "read_usage": read_usage,
                "write_usage": write_usage,
                "decision": "Idle table"
            }
        })

    logger.info("Finished generating DynamoDB recommendations")
    return recommendations