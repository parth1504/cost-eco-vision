"""
One-time setup script: creates the DynamoDB tables this backend needs.

Run from the backend dir:
    python -m scripts.setup_dynamodb

Safe to re-run — skips tables that already exist.
Uses the same AWS credentials/region as your boto3 default
(set via env vars AWS_REGION / AWS_PROFILE or ~/.aws/credentials).
"""

import os
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"

TABLES = [
    {
        "TableName": "Recommendations",
        "KeySchema": [
            {"AttributeName": "resource_id", "KeyType": "HASH"},
            {"AttributeName": "resource_type", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "resource_id", "AttributeType": "S"},
            {"AttributeName": "resource_type", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        # Persisted snapshot of every alert seen.
        # Partition: alert_id (stable, derived from resource + rec).
        # GSI on incident_id lets us list "all alerts in incident X" cheaply.
        "TableName": "Alerts",
        "KeySchema": [
            {"AttributeName": "alert_id", "KeyType": "HASH"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "alert_id", "AttributeType": "S"},
            {"AttributeName": "incident_id", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "incident_id-index",
                "KeySchema": [
                    {"AttributeName": "incident_id", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        # An incident = a cluster of correlated alerts, built by services/correlation.py.
        # Status lifecycle: open -> investigating -> mitigated -> resolved.
        "TableName": "Incidents",
        "KeySchema": [
            {"AttributeName": "incident_id", "KeyType": "HASH"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "incident_id", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        # Cached AI triage for security findings — keyed by the finding's stable id
        # (resource id / bucket name / sg id / etc.) so re-running the security
        # scan doesn't lose previously-generated triage context.
        "TableName": "SecurityTriage",
        "KeySchema": [
            {"AttributeName": "finding_id", "KeyType": "HASH"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "finding_id", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        # Cached recommendation descriptions, keyed by (rule_id + hash of inputs).
        # Persists forever — the analyzer's per-rule descriptions are mostly
        # boilerplate, so paying the LLM cost on every refresh is wasted spend
        # against a tight free-tier daily quota.
        "TableName": "Descriptions",
        "KeySchema": [
            {"AttributeName": "cache_key", "KeyType": "HASH"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "cache_key", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
]


def ensure_table(client, spec):
    name = spec["TableName"]
    try:
        client.describe_table(TableName=name)
        print(f"[skip] table '{name}' already exists")
        return
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise

    print(f"[create] creating table '{name}'...")
    client.create_table(**spec)
    waiter = client.get_waiter("table_exists")
    waiter.wait(TableName=name)
    print(f"[ok] table '{name}' is ACTIVE")


def main():
    print(f"Using AWS region: {REGION}")
    sts = boto3.client("sts", region_name=REGION)
    ident = sts.get_caller_identity()
    print(f"AWS account: {ident['Account']}  ARN: {ident['Arn']}")

    client = boto3.client("dynamodb", region_name=REGION)
    for spec in TABLES:
        ensure_table(client, spec)

    print("\nDone.")


if __name__ == "__main__":
    main()
