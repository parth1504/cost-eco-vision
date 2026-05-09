import logging
import os

# Initialize logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from .ec2_logic import generate_ec2_recommendations
from .s3_logic import generate_s3_recommendations
from .dynamodb_logic import generate_dynamodb_recommendations

from agent.ec2_agent import run_sre_agent





def generateRecommendations(resource):
    logger.info("Generating recommendations for resource: %s", resource.get("resource_id"))
    rtype = resource.get("type")

    if rtype == "EC2":
        return run_sre_agent(resource)
    elif rtype == "S3":
        return generate_s3_recommendations(resource)
    elif rtype == "DynamoDB":
        return generate_dynamodb_recommendations(resource)

    logger.warning("Unknown resource type: %s", rtype)
    return []