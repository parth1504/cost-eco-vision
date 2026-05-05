import logging

# Initialize logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from .ec2_logic import generate_ec2_recommendations
from .s3_logic import generate_s3_recommendations
from .dynamodb_logic import generate_dynamodb_recommendations

def generateRecommendations(resource):
    logger.info("Generating recommendations for resource: %s", resource)
    rtype = resource.get("type")

    if rtype == "EC2":
        logger.info("Resource type is EC2")
        return generate_ec2_recommendations(resource)
    elif rtype == "S3":
        logger.info("Resource type is S3")
        return generate_s3_recommendations(resource)
    elif rtype == "DynamoDB":
        logger.info("Resource type is DynamoDB")
        return generate_dynamodb_recommendations(resource)

    logger.warning("Unknown resource type: %s", rtype)
    return []