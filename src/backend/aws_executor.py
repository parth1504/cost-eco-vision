import boto3
from botocore.exceptions import ClientError

aws_clients = {
    "s3": boto3.client("s3"),
    "ec2": boto3.client("ec2"),
    "iam": boto3.client("iam"),
    "acm": boto3.client("acm"),
    "dynamodb": boto3.client("dynamodb"),
}

CLI_TO_BOTO_MAPPINGS = {
    "instance-ids": "InstanceIds",
    "instance-id": "InstanceId",
    "instance-type": "InstanceType",
    "group-id": "GroupId",
    "volume-id": "VolumeId",
    "table-name": "TableName",
    "bucket": "Bucket",
}



async def apply_aws_commands(commands: list):
    """
    Executes boto3_sequence exactly as stored in DynamoDB.
    No placeholder replacement — assumes commands are already fully resolved.
    """

    print(f"Applying {len(commands)} AWS commands")
    results = []

    for cmd in commands:
        service = cmd.get("service")
        operation = cmd.get("operation")
        params = cmd.get("params", {})

        if service not in aws_clients:
            msg = f"Unsupported AWS service '{service}'"
            print(msg)
            results.append({"success": False, "error": msg})
            continue

        client = aws_clients[service]

        if not hasattr(client, operation):
            msg = f"Invalid AWS operation '{operation}'"
            print(msg)
            results.append({"success": False, "error": msg})
            continue

        try:
            print(f"Running AWS: {service}.{operation}({params})")
            
            fn = getattr(client, operation)
            response = fn(**params)

            print(f"Success: {service}.{operation}")

            results.append({
                "success": True,
                "operation": f"{service}.{operation}",
                "response": response
            })

        except ClientError as e:
            msg = str(e)
            print(f"AWS ClientError: {service}.{operation} - {msg}")
            results.append({
                "success": False,
                "operation": f"{service}.{operation}",
                "error": msg
            })

        except Exception as e:
            msg = str(e)
            print(f"Error: {service}.{operation} - {msg}")
            results.append({
                "success": False,
                "operation": f"{service}.{operation}",
                "error": msg
            })

    return results
