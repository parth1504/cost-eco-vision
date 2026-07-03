import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from agent.ec2_agent.complex_orchestrator import run_complex_agent
from agent.s3_agent.orchestrator import run_s3_agent
from agent.dynamodb_agent.orchestrator import run_dynamodb_agent


def generateRecommendations(resource):
    logger.info(
        "Generating recommendations for resource: %s (type=%s)",
        resource.get("resource_id"), resource.get("type"),
    )
    rtype = resource.get("type")

    if rtype == "EC2":
        return run_complex_agent(resource)
    elif rtype == "S3":
        return run_s3_agent(resource)
    elif rtype == "DynamoDB":
        return run_dynamodb_agent(resource)

    logger.warning("Unknown resource type: %s", rtype)
    return []
