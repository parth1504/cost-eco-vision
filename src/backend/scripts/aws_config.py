import boto3

AWS_REGION = "eu-north-1"

ec2 = boto3.client("ec2", region_name=AWS_REGION)
s3 = boto3.client("s3", region_name=AWS_REGION)
dynamodb = boto3.client("dynamodb", region_name=AWS_REGION)

# -------------------------------------------------------
# REAL IaC — this is the file PR will modify during autofix
# -------------------------------------------------------

def create_ec2_instance():
  
    response = ec2.run_instances(
        ImageId="ami-08d2d8b00f334313",
        InstanceType="t3.small",  
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
