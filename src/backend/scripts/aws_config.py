import boto3

from backend.connections.aws import get_client, get_region
AWS_REGION = get_region()

ec2 = get_client("ec2")
s3 = get_client("s3")
dynamodb = get_client("dynamodb")

# -------------------------------------------------------
# REAL IaC — this is the file PR will modify during autofix
# -------------------------------------------------------

def create_ec2_instance():
  
    response = ec2.run_instances(
        ImageId="ami-08d2d8b00f334313",
        InstanceType="t3.micro",  
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [{"Key": "Name", "Value": "web-server-1"}]
            }
        ]
    )
    return response["Instances"][0]["InstanceId"]


def create_s3_bucket():
  
    bucket_name = "backup-storage-0809"

    s3.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={"LocationConstraint": AWS_REGION}
    )


    return bucket_name


def create_dynamodb_table():
 
    table_name = "UserTable"
    dynamodb.create_table(
        TableName=table_name,
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST"
    )

    return table_name


if __name__ == "__main__":
    print("Creating AWS infra...")
    ec2_id = create_ec2_instance()
    bucket = create_s3_bucket()
    table = create_dynamodb_table()
    print("Done.")
