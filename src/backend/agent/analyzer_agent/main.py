from .ec2_logic import generate_ec2_recommendations
from .s3_logic import generate_s3_recommendations
from .dynamodb_logic import generate_dynamodb_recommendations

def generateRecommendations(resource):
    rtype = resource.get("type")

    if rtype == "EC2":
        return generate_ec2_recommendations(resource)
    elif rtype == "S3":
        return generate_s3_recommendations(resource)
    elif rtype == "DynamoDB":
        return generate_dynamodb_recommendations(resource)

    return []