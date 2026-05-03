from .ec2_logic import generate_ec2_recommendations
from .s3_logic import generate_s3_recommendations
from .dynamodb_logic import generate_dynamodb_recommendations

def generateRecommendations(resource):
    if resource["type"] == "EC2":
        return generate_ec2_recommendations(resource)
    elif resource["type"] == "S3":
        return generate_s3_recommendations(resource)
    elif resource["type"] == "DynamoDB":
        return generate_dynamodb_recommendations(resource)
    return []