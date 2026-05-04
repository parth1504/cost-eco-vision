from os import name

from backend.agent.analyzer_agent.main import generateRecommendations
from connections.db import get_resource_from_db, save_resource_in_db
from datetime import datetime, timedelta
from aws.util import replace_placeholders, get_resource_cost, should_run_agent
from connections.aws import get_client, get_region
from backend.agent.analyzer_agent.main import generateRecommendations


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

async def list_dynamodb_tables():
    """Fetch all DynamoDB tables and enrich with DynamoDB-backed state."""
    try:
        response = dynamodb.list_tables()
        table_names = response.get("TableNames", [])
        tables = []

        for name in table_names:
            

            db_item = get_resource_from_db(name, "DynamoDB")

            if db_item:
                table_data=db_item
                table_data["resource_id"] = name
                last_run= table_data.get("last_agent_run")
                print(f"DynamoDB Table {name} last agent run: {last_run}")
                if should_run_agent(last_run):
                    recommendations = generateRecommendations(table_data)
                    table_data["recommendations"] = recommendations
                    table_data["last_agent_run"] = datetime.utcnow().isoformat()

                    save_resource_in_db(name, "DynamoDB", table_data)
            else:
                

                desc= dynamodb.describe_table(TableName=name)["Table"]
                table_data=build_dynamodb_resource(desc,name)
                print(f"Built DynamoDB resource data for {name}: {table_data}")
                print("-------------------------------------------------------------------------")
                recommendations=generateRecommendations(table_data)
                table_data["recommendations"]=recommendations
                saved=save_resource_in_db(name, "DynamoDB", table_data)

            tables.append(table_data)

        return tables

    except Exception as e:
        print(f"Error in list_dynamodb_tables: {e}")
        return []

def get_consumed_read_write_capacity(table_name, region="us-east-1"):
    """Return % DynamoDB capacity usage based on consumed RCUs/WCUs."""

    try:
        desc = dynamodb.describe_table(TableName=table_name)["Table"]
        rc = desc.get("ProvisionedThroughput", {}).get("ReadCapacityUnits", 0)
        wc = desc.get("ProvisionedThroughput", {}).get("WriteCapacityUnits", 0)

        # On-demand tables return NONE
        if rc == 0 and wc == 0:
            return 0

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

        rc_used = read_metrics.get("Datapoints", [])
        wc_used = write_metrics.get("Datapoints", [])

        read_percent = (rc_used[-1]["Average"] / rc) * 100 if rc_used and rc > 0 else 0
        write_percent = (wc_used[-1]["Average"] / wc) * 100 if wc_used and wc > 0 else 0

        return round(max(read_percent, write_percent), 2)

    except Exception as e:
        print(f"Failed to get DynamoDB capacity for {table_name}: {e}")
        return 0

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
    try:
        pitr = dynamodb.describe_continuous_backups(
            TableName=table_name
        )
        pitr_enabled = pitr["ContinuousBackupsDescription"] \
            .get("PointInTimeRecoveryDescription", {}) \
            .get("PointInTimeRecoveryStatus") == "ENABLED"
    except Exception:
        pitr_enabled = False

    # ------------------------
    # Encryption
    # ------------------------
    sse_desc = desc.get("SSEDescription", {})
    encryption_enabled = sse_desc.get("Status") == "ENABLED"

    # ------------------------
    # Billing mode
    # ------------------------
    billing_mode = desc.get("BillingModeSummary", {}).get("BillingMode", "PROVISIONED")

    return {
        "pitr_enabled": pitr_enabled,
        "encryption_enabled": encryption_enabled,
        "billing_mode": billing_mode
    }