import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from connections.db import get_resource_from_db, save_resource_in_db
from aws.ec2 import list_ec2_instances
from aws.s3 import list_s3_buckets
from aws.dynamodb import list_dynamodb_tables

logger = logging.getLogger(__name__)

running_resources = 0
idle_resources = 0


async def get_all_resources(force: bool = False):
    """
    Fetch live AWS resources, then run the unified LangGraph multi-agent
    pipeline for telemetry, signals, sub-agent analysis, safety, ranking,
    critique, refinement, cross-resource correlation, verification, and
    quality evaluation.
    """
    logger.info("Fetching all resources from AWS... (force=%s)", force)
    ec2_resources = await list_ec2_instances(force=force)
    s3_resources = await list_s3_buckets(force=force)
    dynamo_resources = await list_dynamodb_tables(force=force)
    resources = ec2_resources + s3_resources + dynamo_resources

    for res in resources:
        if res.get("status") == "running":
            global running_resources
            running_resources += 1
        else:
            global idle_resources
            idle_resources += 1

        if not res.get("last_activity"):
            res["last_activity"] = (
                res.get("last_agent_run")
                or res.get("metadata", {}).get("creation_date")
                or res.get("creation_date")
            )

    resources = _run_langgraph_pipeline(resources)
    return resources


def _run_langgraph_pipeline(resources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Run the unified LangGraph multi-agent pipeline on all resources.

    Resources marked with needs_analysis=True (cooldown expired or first
    seen) go through the full pipeline: telemetry → signals → sub-agents →
    safety → rank → critique → refine → correlate → verify → evaluate.

    Cached resources (with existing recommendations) skip telemetry and
    sub-agents but still participate in cross-resource correlation.
    """
    from agent.core.orchestrator import MultiAgentOrchestrator

    needs_analysis = [r for r in resources if r.get("needs_analysis")]
    has_cached = [r for r in resources if r.get("recommendations") and not r.get("needs_analysis")]

    if not needs_analysis and not has_cached:
        return resources

    pipeline_resources = needs_analysis + has_cached

    try:
        orchestrator = MultiAgentOrchestrator()
        result = orchestrator.run(pipeline_resources)

        verified_recs = result.get("recommendations", [])
        correlations = result.get("correlations", [])

        rec_by_resource: Dict[str, List[Dict[str, Any]]] = {}
        for rec in verified_recs:
            rid = rec.get("resource_id", "")
            rec_by_resource.setdefault(rid, []).append(rec)

        for res in resources:
            rid = res.get("resource_id", "")

            if rid in rec_by_resource:
                res["recommendations"] = rec_by_resource[rid]

            if correlations:
                involved = [
                    c for c in correlations
                    if rid in c.get("resources_involved", [])
                    or not c.get("resources_involved")
                ]
                if involved:
                    res["correlations"] = involved

            if res.get("needs_analysis"):
                res.pop("needs_analysis", None)
                res["last_agent_run"] = datetime.utcnow().isoformat()
                save_resource_in_db(rid, res.get("type", ""), res)

        logger.info(
            "LangGraph pipeline complete — %d verified recs, %d correlations",
            len(verified_recs), len(correlations),
        )

    except Exception as e:
        logger.warning("LangGraph pipeline failed, returning raw resources: %s", e)

    return resources


def get_resource_by_id(resource_id: str, resource_type: str):
    return get_resource_from_db(resource_id)


def get_running_resource() -> int:
    return running_resources


def get_idle_resource() -> int:
    return idle_resources
