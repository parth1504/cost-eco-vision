import logging
import os

# Initialize logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from .ec2_logic import generate_ec2_recommendations
from .s3_logic import generate_s3_recommendations
from .dynamodb_logic import generate_dynamodb_recommendations


def _use_sre_agent_for_ec2() -> bool:
    """
    Toggle: route EC2 through the new SRE agent (production-grade pipeline)
    or the legacy rule engine.

    Default: SRE agent ON. Set USE_SRE_AGENT=false in .env to fall back to
    the legacy ec2_logic.py path.
    """
    raw = os.getenv("USE_SRE_AGENT", "true").strip().lower()
    return raw in ("true", "1", "yes", "on")


def generateRecommendations(resource):
    logger.info("Generating recommendations for resource: %s", resource.get("resource_id"))
    rtype = resource.get("type")

    if rtype == "EC2":
        if _use_sre_agent_for_ec2():
            logger.info("EC2 → SRE agent pipeline")
            from agent.sre_agent import run_sre_agent
            return run_sre_agent(resource)
        logger.info("EC2 → legacy rule engine")
        return generate_ec2_recommendations(resource)
    elif rtype == "S3":
        return generate_s3_recommendations(resource)
    elif rtype == "DynamoDB":
        return generate_dynamodb_recommendations(resource)

    logger.warning("Unknown resource type: %s", rtype)
    return []