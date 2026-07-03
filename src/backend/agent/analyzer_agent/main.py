"""
Legacy entry point — kept for backward compatibility.

The unified LangGraph orchestrator (agent.core) now handles all analysis.
This module is only used by routes that apply fixes on individual resources
and need a quick single-resource re-analysis outside the full pipeline.
"""

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def generateRecommendations(resource):
    """
    Single-resource recommendation generation via the LangGraph pipeline.

    Called only for ad-hoc re-analysis (e.g. after applying fixes).
    The main flow in services/resources.py uses the orchestrator directly.
    """
    from agent.core.orchestrator import MultiAgentOrchestrator

    logger.info(
        "Generating recommendations for resource: %s (type=%s)",
        resource.get("resource_id"), resource.get("type"),
    )

    orchestrator = MultiAgentOrchestrator()
    result = orchestrator.run([resource])
    return result.get("recommendations", [])
