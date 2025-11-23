import boto3
from botocore.exceptions import ClientError

aws_clients = {
    "s3": boto3.client("s3"),
    "ec2": boto3.client("ec2"),
    "iam": boto3.client("iam"),
    "acm": boto3.client("acm"),
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
    commands = [
        {
            "service": "s3",
            "operation": "put_bucket_encryption",
            "params": { ... }
        },
        ...
    ]
    """
    print(f"Applying {len(commands)} AWS commands")
    results = []

    for cmd in commands:
        service = cmd.get("service")
        operation = cmd.get("operation")
        params = cmd.get("params", {})

        if service not in aws_clients:
            results.append({"success": False, "error": f"Unsupported AWS service '{service}'"})
            continue

        client = aws_clients[service]

        if not hasattr(client, operation):
            results.append({"success": False, "error": f"Invalid AWS operation '{operation}'"})
            continue

        try:
            print(f"Running AWS: {service}.{operation}({params})")
            fn = getattr(client, operation)
            response = fn(**params)

            results.append({
                "success": True,
                "operation": f"{service}.{operation}",
                "response": response
            })
            print(f"Success: {service}.{operation}")

        except ClientError as e:
            results.append({
                "success": False,
                "operation": f"{service}.{operation}",
                "error": str(e)
            })
            print(f"AWS ClientError: {service}.{operation} - {str(e)}")

        except Exception as e:
            results.append({
                "success": False,
                "operation": f"{service}.{operation}",
                "error": str(e)

            })
            print(f"Error: {service}.{operation} - {str(e)}")

    return results
