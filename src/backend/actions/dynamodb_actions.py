from typing import Dict, Any


def enable_point_in_time_recovery(table_name: str, dynamodb_client) -> Dict[str, Any]:
    """Enables PITR for data recovery."""
    try:
        response = dynamodb_client.update_continuous_backups(
            TableName=table_name,
            PointInTimeRecoverySpecification={"PointInTimeRecoveryEnabled": True},
        )
        return {"status": "success", "message": "PITR enabled", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


def update_read_write_capacity(
    table_name: str, read_units: int, write_units: int, dynamodb_client
) -> Dict[str, Any]:
    """Updates provisioned capacity."""
    try:
        response = dynamodb_client.update_table(
            TableName=table_name,
            ProvisionedThroughput={
                "ReadCapacityUnits": read_units,
                "WriteCapacityUnits": write_units,
            },
        )
        return {"status": "success", "message": "Capacity updated", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


def enable_encryption(table_name: str, dynamodb_client) -> Dict[str, Any]:
    """Enables KMS encryption."""
    try:
        response = dynamodb_client.update_table(
            TableName=table_name,
            SSESpecification={"Enabled": True, "SSEType": "KMS"},
        )
        return {"status": "success", "message": "Encryption enabled", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


def delete_table(table_name: str, dynamodb_client) -> Dict[str, Any]:
    """Deletes a DynamoDB table (destructive)."""
    try:
        response = dynamodb_client.delete_table(TableName=table_name)
        return {"status": "success", "message": "Table deleted", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


def tag_table(table_name: str, tags: list, dynamodb_client) -> Dict[str, Any]:
    """Adds tags to DynamoDB table."""
    try:
        arn = dynamodb_client.describe_table(TableName=table_name)["Table"]["TableArn"]
        response = dynamodb_client.tag_resource(ResourceArn=arn, Tags=tags)
        return {"status": "success", "message": "Tags added", "data": response}
    except Exception as e:
        return {"status": "error", "message": str(e), "data": None}


ACTION_REGISTRY = {
    "enable_point_in_time_recovery": enable_point_in_time_recovery,
    "update_read_write_capacity": update_read_write_capacity,
    "enable_encryption": enable_encryption,
    "delete_table": delete_table,
    "tag_table": tag_table,
}