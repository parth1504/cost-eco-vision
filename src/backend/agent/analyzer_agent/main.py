import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from .s3_logic import generate_s3_recommendations
from .dynamodb_logic import generate_dynamodb_recommendations

# EC2 now uses the dynamic multi-agent orchestrator instead of the fixed-sequence
# run_sre_agent.  The complex orchestrator uses an LLM router to decide which
# specialist agent (metric, cost, reliability, security, root-cause) to invoke
# at each step — based on signals and accumulated findings — rather than
# running every agent in a predetermined order.
from agent.ec2_agent.complex_orchestrator import run_complex_agent


def generateRecommendations(resource):
    logger.info(
        "Generating recommendations for resource: %s (type=%s)",
        resource.get("resource_id"), resource.get("type"),
    )
    rtype = resource.get("type")

    if rtype == "EC2":
        # Dynamic orchestrator: LLM router decides agent order at runtime
        return run_complex_agent(resource)
    elif rtype == "S3":
        return generate_s3_recommendations(resource)
    elif rtype == "DynamoDB":
        return generate_dynamodb_recommendations(resource)

    logger.warning("Unknown resource type: %s", rtype)
    return []
