from os import name

from agent.analyzer_agent.main import generateRecommendations
from connections.db import get_resource_from_db, save_resource_in_db
from datetime import datetime, timedelta
from aws.util import replace_placeholders, get_resource_cost, should_run_agent
from connections.aws import get_client, get_region
from agent.analyzer_agent.main import generateRecommendations


dynamodb = get_client("dynamodb")
cloudwatch = get_client("cloudwatch")

dynamodb_recommendations = [
    # {
    #     "title": "Remove Public Access from DynamoDB Table",
    #     "description": (
    #         "The table is accessible via overly permissive IAM policies. "
    #         "Public access exposes sensitive data and violates SOC2, PCI-DSS, and ISO 27001 guidelines."
    #     ),
    #     "type": "security",
    #     "severity": "critical",
    #     "saving": "N/A",
    #     "issue": "IAM policy allows public or wildcard (*) access",
    #     "impact": "high",
    #     "solution_steps": [
    #         {
    #             "step": 1,
    #             "command": (
    #                 "aws iam list-policies --query \"Policies[?contains(PolicyName, '{TABLE_NAME}')].Arn\""
    #             ),
    #             "description": "Identify IAM policies attached to the DynamoDB table."
    #         },
    #         {
    #             "step": 2,
    #             "command": (
    #                 "aws iam detach-role-policy --role-name {ROLE_NAME} --policy-arn {POLICY_ARN}"
    #             ),
    #             "description": "Detach any overly permissive role policies."
    #         },
    #         {
    #             "step": 3,
    #             "command": (
    #                 "aws iam put-role-policy --role-name {ROLE_NAME} --policy-name SecureAccessPolicy "
    #                 "--policy-document file://restricted-ddb-policy.json"
    #             ),
    #             "description": "Attach a secure least-privilege policy that restricts access."
    #         }
    #     ]
    # },

    {
        "title": "Enable DynamoDB Server-Side Encryption",
        "description": (
            "The table is not encrypted at rest. Unencrypted DynamoDB tables can lead to compliance failures "
            "and data exposure risks."
        ),
        "type": "security",
        "severity": "high",
        "status": "active",
        "saving": "N/A",
        "issue": "Encryption at rest is disabled",
        "impact": "high",
        "solution_steps": [
            {
                "step": 1,
                "command": (
                    "aws dynamodb update-table --table-name {TABLE_NAME} "
                    "--sse-specification Enabled=true,SSEType=KMS"
                ),
                "description": "Enable AWS KMS-based server-side encryption."
            }
        ],
        "boto3_sequence": [
            {
                "service": "dynamodb",
                "operation": "update_table",
                "params": {
                "TableName": "{TABLE_NAME}",
                "SSESpecification": {
                    "Enabled": True,
                    "SSEType": "KMS"
                }
                }
            }
            ]
    },

    # {
    #     "title": "Right-Size DynamoDB Read/Write Capacity",
    #     "description": (
    #         "Provisioned capacity is significantly higher than actual usage. "
    #         "Downsizing capacity reduces monthly cost without performance impact."
    #     ),
    #     "type": "cost",
    #     "severity": "warning",
    #     "saving": 12.80,  # Example savings
    #     "issue": "Provisioned RCU/WCU far above actual traffic",
    #     "impact": "medium",
    #     "solution_steps": [
    #         {
    #             "step": 1,
    #             "command": (
    #                 "aws dynamodb describe-table --table-name {TABLE_NAME} "
    #                 "--query 'Table.ProvisionedThroughput'"
    #             ),
    #             "description": "Check current read/write capacity settings."
    #         },
    #         {
    #             "step": 2,
    #             "command": (
    #                 "aws dynamodb update-table --table-name {TABLE_NAME} "
    #                 "--provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5"
    #             ),
    #             "description": "Reduce RCU/WCU to match actual usage."
    #         }
    #     ]
    # },

    {
        "title": "Enable Point-in-Time Recovery (PITR)",
        "description": (
            "Point-in-Time Recovery is disabled. Enabling PITR protects your DynamoDB tables from "
            "accidental writes, deletes, or corruption."
        ),
        "type": "security",
        "severity": "medium",
        "saving": "N/A",
        "status": "active",
        "issue": "PITR disabled",
        "impact": "medium",
        "solution_steps": [
            {
                "step": 1,
                "command": (
                    "aws dynamodb update-continuous-backups --table-name {TABLE_NAME} "
                    "--point-in-time-recovery-specification PointInTimeRecoveryEnabled=true"
                ),
                "description": "Enable point-in-time recovery."
            }
        ],
        "boto3_sequence": [
        {
            "service": "dynamodb",
            "operation": "update_continuous_backups",
            "params": {
            "TableName": "{TABLE_NAME}",
            "PointInTimeRecoverySpecification": {
                "PointInTimeRecoveryEnabled": True
            }
            }
        }
        ]
    },

    # {
    #     "title": "Remove Unused Global Secondary Indexes (GSI)",
    #     "description": (
    #         "One or more GSIs have extremely low read/write activity. "
    #         "Maintaining idle GSIs creates unnecessary monthly costs."
    #     ),
    #     "type": "cost",
    #     "severity": "warning",
    #     "saving": 4.20,
    #     "issue": "Low-traffic or unused indexes detected",
    #     "impact": "low",
    #     "solution_steps": [
    #         {
    #             "step": 1,
    #             "command": (
    #                 "aws dynamodb describe-table --table-name {TABLE_NAME} "
    #                 "--query 'Table.GlobalSecondaryIndexes'"
    #             ),
    #             "description": "Check all GSIs and their usage metrics."
    #         },
    #         {
    #             "step": 2,
    #             "command": (
    #                 "aws dynamodb update-table --table-name {TABLE_NAME} "
    #                 "--global-secondary-index-updates '[{\"Delete\": {\"IndexName\": \"{GSI_NAME}\"}}]'"
    #             ),
    #             "description": "Delete unused GSI to eliminate wasted capacity."
    #         }
    #     ]
    # }
]

async def list_dynamodb_tables(force: bool = False):
    """
    Fetch all DynamoDB tables and enrich with DynamoDB-backed state.

    Pass force=True to bypass the cooldown and force a fresh agent re-run.
    On re-run we now re-fetch live metrics+config from AWS rather than
    feeding stale cached fields to the agent.
    """
    try:
        response = dynamodb.list_tables()
        table_names = response.get("TableNames", [])
        tables = []

        for name in table_names:
            db_item = get_resource_from_db(name, "DynamoDB")

            if db_item:
                last_run = db_item.get("last_agent_run")
                print(f"DynamoDB Table {name} last agent run: {last_run}, force={force}")

                if should_run_agent(last_run, force=force):
                    desc = dynamodb.describe_table(TableName=name)["Table"]
                    table_data = build_dynamodb_resource(desc, name)
                    table_data["is_optimized"] = db_item.get("is_optimized", False)
                    recommendations = generateRecommendations(table_data)
                    table_data["recommendations"] = recommendations
                    table_data["last_agent_run"] = datetime.utcnow().isoformat()
                    save_resource_in_db(name, "DynamoDB", table_data)
                else:
                    table_data = db_item
                    table_data["resource_id"] = name
            else:
                desc = dynamodb.describe_table(TableName=name)["Table"]
                table_data = build_dynamodb_resource(desc, name)
                recommendations = generateRecommendations(table_data)
                table_data["recommendations"] = recommendations
                save_resource_in_db(name, "DynamoDB", table_data)

            tables.append(table_data)

        return tables

    except Exception as e:
        print(f"Error in list_dynamodb_tables: {e}")
        return []

def get_consumed_read_write_capacity(table_name, region="us-east-1"):
    """
    Return DynamoDB capacity usage as a dict:
      {"read_capacity": <pct 0-100>, "write_capacity": <pct 0-100>}
    Empty dict if the table is on-demand or metrics unavailable.
    """

    try:
        desc = dynamodb.describe_table(TableName=table_name)["Table"]
        rc = desc.get("ProvisionedThroughput", {}).get("ReadCapacityUnits", 0)
        wc = desc.get("ProvisionedThroughput", {}).get("WriteCapacityUnits", 0)

        # On-demand tables have no provisioned capacity to compare against.
        if rc == 0 and wc == 0:
            return {}

        end = datetime.utcnow()
        start = end - timedelta(hours=12)

        # Read consumed
        read_metrics = cloudwatch.get_metric_statistics(
            Namespace="AWS/DynamoDB",
            MetricName="ConsumedReadCapacityUnits",
            Dimensions=[{"Name": "TableName", "Value": table_name}],
            StartTime=start,
            EndTime=end,
            Period=3600,
            Statistics=["Average"]
        )

        # Write consumed
        write_metrics = cloudwatch.get_metric_statistics(
            Namespace="AWS/DynamoDB",
            MetricName="ConsumedWriteCapacityUnits",
            Dimensions=[{"Name": "TableName", "Value": table_name}],
            StartTime=start,
            EndTime=end,
            Period=3600,
            Statistics=["Average"]
        )

        # CloudWatch doesn't guarantee chronological order; sort to be safe.
        rc_used = sorted(read_metrics.get("Datapoints", []), key=lambda d: d["Timestamp"])
        wc_used = sorted(write_metrics.get("Datapoints", []), key=lambda d: d["Timestamp"])

        read_percent = (rc_used[-1]["Average"] / rc) * 100 if rc_used and rc > 0 else 0
        write_percent = (wc_used[-1]["Average"] / wc) * 100 if wc_used and wc > 0 else 0

        return {
            "read_capacity": round(read_percent, 2),
            "write_capacity": round(write_percent, 2),
        }

    except Exception as e:
        print(f"Failed to get DynamoDB capacity for {table_name}: {e}")
        return {}

from datetime import datetime

def build_dynamodb_resource(desc, name):
    region = get_region()

    return {
        "resource_id": name,
        "name": name,
        "type": "DynamoDB",
        "status": desc.get("TableStatus", "UNKNOWN").lower(),
        "region": region,
        "provider": "AWS",

        # 👇 structured for agent
        "metrics": get_dynamodb_metrics(name, region),
        "config": get_dynamodb_config(desc, name),

        "monthly_cost": get_resource_cost("TableName", name),

        "metadata": {
            "creation_date": desc.get("CreationDateTime").isoformat()
            if desc.get("CreationDateTime") else None,
            "item_count": desc.get("ItemCount"),
            "table_size_bytes": desc.get("TableSizeBytes")
        },

        "is_optimized": False,
        "last_agent_run": datetime.utcnow().isoformat()
    }

def get_dynamodb_metrics(table_name, region):
    utilization = get_consumed_read_write_capacity(table_name, region)

    if not utilization:
        return {}

    return {
        "read_capacity_used": utilization.get("read_capacity"),
        "write_capacity_used": utilization.get("write_capacity"),
    }

def get_dynamodb_config(desc, table_name):
    # ------------------------
    # PITR (Point-in-Time Recovery)
    # ------------------------
    # On API failure leave as None ("unknown") so the agent doesn't fire
    # a false-positive recommendation when we couldn't actually check.
    try:
        pitr = dynamodb.describe_continuous_backups(TableName=table_name)
        pitr_enabled = (
            pitr["ContinuousBackupsDescription"]
            .get("PointInTimeRecoveryDescription", {})
            .get("PointInTimeRecoveryStatus") == "ENABLED"
        )
    except Exception:
        pitr_enabled = None

    # ------------------------
    # Encryption
    # ------------------------
    # When SSEDescription is absent, the table uses the AWS-owned default
    # KMS key — which IS encrypted. So absence != disabled.
    sse_desc = desc.get("SSEDescription")
    if sse_desc is None:
        encryption_enabled = True  # AWS-managed default encryption
    else:
        encryption_enabled = sse_desc.get("Status") == "ENABLED"

    # ------------------------
    # Billing mode + provisioned capacity (used by the overutilized rule
    # to compute proper scale-up targets — needs current units, not %)
    # ------------------------
    billing_mode = desc.get("BillingModeSummary", {}).get("BillingMode", "PROVISIONED")
    pt = desc.get("ProvisionedThroughput", {}) or {}

    return {
        "pitr_enabled": pitr_enabled,
        "encryption_enabled": encryption_enabled,
        "billing_mode": billing_mode,
        "provisioned_rcu": pt.get("ReadCapacityUnits", 0),
        "provisioned_wcu": pt.get("WriteCapacityUnits", 0),
    }