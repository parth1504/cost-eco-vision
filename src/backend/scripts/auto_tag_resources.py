"""
Auto-Tag EC2, S3, and DynamoDB Resources
Tags:
- EC2:        InstanceId = <instance-id>
- S3 Bucket:  BucketName = <bucket-name>
- DynamoDB:   TableName  = <table-name>
"""

from botocore.exceptions import ClientError
from connections.aws import get_client, get_region

# Initialize clients
AWS_REGION = get_region()
ec2 = get_client("ec2")
s3 = get_client("s3")
dynamodb = get_client("dynamodb")


# ------------------------------------------
# Tag EC2 Instances
# ------------------------------------------
def tag_ec2_instances():
    print("\n🔍 Tagging EC2 Instances...")

    try:
        response = ec2.describe_instances()
        tagged_count = 0

        for reservation in response.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                instance_id = instance["InstanceId"]

                # Check existing tags
                existing_tags = {t["Key"]: t["Value"] for t in instance.get("Tags", [])}

                if existing_tags.get("InstanceId") == instance_id:
                    print(f"   ✔ EC2 {instance_id} already tagged. Skipping...")
                    continue

                # Apply tag
                ec2.create_tags(
                    Resources=[instance_id],
                    Tags=[{"Key": "InstanceId", "Value": instance_id}]
                )
                print(f"   ➕ Tagged EC2 instance: {instance_id}")
                tagged_count += 1

        print(f"✨ EC2 tagging complete. Tagged {tagged_count} instances.")

    except ClientError as e:
        print(f"❌ EC2 tagging error: {e}")


# ------------------------------------------
# Tag S3 Buckets
# ------------------------------------------
def tag_s3_buckets():
    print("\n🔍 Tagging S3 Buckets...")

    try:
        buckets = s3.list_buckets().get("Buckets", [])
        tagged_count = 0

        for bucket in buckets:
            bucket_name = bucket["Name"]

            # Fetch existing bucket tags
            try:
                tagset = s3.get_bucket_tagging(Bucket=bucket_name).get("TagSet", [])
                existing_tags = {t["Key"]: t["Value"] for t in tagset}
            except ClientError:
                existing_tags = {}

            if existing_tags.get("BucketName") == bucket_name:
                print(f"   ✔ S3 {bucket_name} already tagged. Skipping...")
                continue

            # Apply tag
            try:
                s3.put_bucket_tagging(
                    Bucket=bucket_name,
                    Tagging={
                        "TagSet": [
                            {"Key": "BucketName", "Value": bucket_name}
                        ]
                    }
                )
                print(f"   ➕ Tagged S3 bucket: {bucket_name}")
                tagged_count += 1

            except ClientError as e:
                print(f"❌ Failed tagging S3 bucket {bucket_name}: {e}")

        print(f"✨ S3 tagging complete. Tagged {tagged_count} buckets.")

    except ClientError as e:
        print(f"❌ S3 tagging error: {e}")


# ------------------------------------------
# Tag DynamoDB Tables
# ------------------------------------------
def tag_dynamodb_tables():
    print("\n🔍 Tagging DynamoDB Tables...")

    try:
        tables = dynamodb.list_tables().get("TableNames", [])
        tagged_count = 0

        for table_name in tables:

            # Get ARN to tag DynamoDB
            desc = dynamodb.describe_table(TableName=table_name)["Table"]
            arn = desc["TableArn"]

            # Get existing tags
            try:
                current_tags = dynamodb.list_tags_of_resource(ResourceArn=arn).get("Tags", [])
                existing_tags = {t["Key"]: t["Value"] for t in current_tags}
            except:
                existing_tags = {}

            if existing_tags.get("TableName") == table_name:
                print(f"   ✔ DynamoDB {table_name} already tagged. Skipping...")
                continue

            # Apply tag
            dynamodb.tag_resource(
                ResourceArn=arn,
                Tags=[{"Key": "TableName", "Value": table_name}]
            )
            print(f"   ➕ Tagged DynamoDB table: {table_name}")
            tagged_count += 1

        print(f"✨ DynamoDB tagging complete. Tagged {tagged_count} tables.")

    except ClientError as e:
        print(f"❌ DynamoDB tagging error: {e}")


# ------------------------------------------
# Main Entry
# ------------------------------------------
if __name__ == "__main__":
    print("\n🚀 Starting Auto-Tag Script...")
    tag_ec2_instances()
    tag_s3_buckets()
    tag_dynamodb_tables()
    print("\n🎉 Auto-Tagging Complete!")
