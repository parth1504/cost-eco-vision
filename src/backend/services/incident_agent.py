"""
Incident analysis agent — provider-agnostic Bedrock Converse API.

Given a correlated incident (the cluster of alerts produced by services/correlation.py),
ask an LLM to:
  1. Inspect each affected resource via the read-only `get_resource_recommendation` tool.
  2. Reason about a likely root cause and produce a mitigation checklist.
  3. End the loop by calling `submit_analysis` with a structured payload.

Uses Bedrock's Converse API (boto3), which is provider-agnostic — you can swap
between Claude / Nova / Llama / Mistral by changing BEDROCK_MODEL_ID.

The structured payload is the same shape the frontend already renders for
mocked incidents — primaryCause / contributingFactors / immediateActions /
confidence / checklist — so wiring this in requires no UI changes.

The result is cached on the Incident row so re-opening the page is free.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import boto3
from botocore.exceptions import ClientError

from connections.db import (
    get_alerts_for_incident,
    get_incident,
    get_resource_from_db,
    upsert_incident,
)

# Bedrock model ID. Override via env var. Must support tool use via Converse API.
# Known-good IDs that support tool use (as of late 2025 / early 2026):
#   us.amazon.nova-pro-v1:0                          (recommended default — generous quotas, cheap, good reasoning)
#   us.amazon.nova-lite-v1:0                         (even cheaper, weaker reasoning)
#   us.meta.llama3-3-70b-instruct-v1:0               (open-source alternative)
#   mistral.mistral-large-2407-v1:0                  (Mistral, no inference profile needed)
#   us.anthropic.claude-haiku-4-5-20251001-v1:0      (Claude — needs quota approval)
#   us.anthropic.claude-sonnet-4-6                   (Claude — needs quota approval)
#
# DOES NOT WORK (no tool use support on Bedrock):
#   us.deepseek.r1-v1:0                              (text-only)
#   meta.llama3-1-* and older                        (varies)
MODEL = os.getenv("BEDROCK_MODEL_ID", "global.anthropic.claude-opus-4-6-v1")
# Bedrock region can differ from DynamoDB region — quotas are per-region, so
# if us-east-1 is zeroed out, try us-west-2 or eu-central-1 by setting
# BEDROCK_REGION in .env. Falls back to AWS_REGION for the DDB-default case.
AWS_REGION = (
    os.getenv("BEDROCK_REGION")
    or os.getenv("AWS_REGION")
    or os.getenv("AWS_DEFAULT_REGION")
    or "us-east-1"
)

MAX_LOOP_TURNS = 8           # hard cap on tool-call iterations — prevents runaways
MAX_TOKENS = 4096            # plenty for a structured payload + a few tool calls

SYSTEM_PROMPT = """You are a senior AWS CloudOps engineer running incident response.

You will be given a correlated incident: a cluster of related alerts that fired
on the same or connected AWS resources within a short time window. Your job is to:

  1. Use the `get_resource_recommendation` tool to inspect each affected
     resource if you need more context (current config, prior recommendations,
     utilization, status). Call it once per (resource_id, resource_type) pair
     you want to examine. Skip resources whose alert message already gives
     you enough information.
  2. Reason about the most likely root cause, contributing factors, and the
     immediate actions a human operator should take.
  3. End by calling `submit_analysis` exactly once with your structured
     conclusion. Do NOT emit a final text answer — `submit_analysis` IS the
     answer.

Guidance:
  - Be specific. "Misconfigured access" is useless; "S3 bucket ACL grants
    READ to AllUsers, Block Public Access disabled" is useful.
  - Tie each contributing factor to evidence in the alerts or tool output.
  - Mitigation steps must be concrete and ordered (containment first, then
    fix, then verification). Avoid generic advice like "review your security
    posture".
  - Confidence is an integer 0-100. Be honest — if the alerts are sparse,
    say 50, not 95.
  - Keep contributing_factors and immediate_actions to 3-6 items each.
  - Checklist items are short imperative verbs ("Enable Block Public Access
    on bucket X"), not full sentences."""


# ---------------------------------------------------------------------------
# Tool schemas (Converse API format — note `toolSpec` wrapper, `inputSchema.json`)
# ---------------------------------------------------------------------------

TOOL_CONFIG: Dict[str, Any] = {
    "tools": [
        {
            "toolSpec": {
                "name": "get_resource_recommendation",
                "description": (
                    "Fetch the cached recommendation record for an AWS resource from "
                    "our Recommendations DynamoDB table. Returns current status, "
                    "monthly cost, utilization, region, and any prior recommendations "
                    "the system has already produced for it. Use this when an alert "
                    "message alone isn't enough to reason about root cause."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "resource_id": {
                                "type": "string",
                                "description": "The resource_id (e.g. 'backup-storage-0189', 'i-abc123').",
                            },
                            "resource_type": {
                                "type": "string",
                                "description": "Resource type (e.g. 'S3', 'EC2', 'RDS', 'DynamoDB', 'Lambda').",
                            },
                        },
                        "required": ["resource_id", "resource_type"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "submit_analysis",
                "description": (
                    "Submit your final structured incident analysis. Calling this "
                    "ENDS the analysis — do not produce any further text or tool "
                    "calls after invoking it."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "primary_cause": {
                                "type": "string",
                                "description": "One concise sentence naming the most likely root cause.",
                            },
                            "contributing_factors": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "3-6 specific factors that enabled or worsened the incident.",
                            },
                            "immediate_actions": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "3-6 concrete remediation steps in order (contain → fix → verify).",
                            },
                            "confidence": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 100,
                                "description": "Honest confidence in the diagnosis (0-100).",
                            },
                            "checklist": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Short imperative checklist items for the human operator.",
                            },
                        },
                        "required": [
                            "primary_cause",
                            "contributing_factors",
                            "immediate_actions",
                            "confidence",
                            "checklist",
                        ],
                    }
                },
            }
        },
    ]
}


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def _tool_get_resource_recommendation(resource_id: str, resource_type: str) -> Dict[str, Any]:
    item = get_resource_from_db(resource_id, resource_type)
    if not item:
        return {"found": False, "resource_id": resource_id, "resource_type": resource_type}
    safe = json.loads(json.dumps(item, default=str))
    return {"found": True, "resource": safe}


def _execute_tool(name: str, args: Dict[str, Any]) -> Any:
    if name == "get_resource_recommendation":
        return _tool_get_resource_recommendation(
            resource_id=args["resource_id"],
            resource_type=args["resource_type"],
        )
    return {"error": f"Unknown tool: {name}"}


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_user_prompt(incident: Dict[str, Any], alerts: List[Dict[str, Any]]) -> str:
    alerts_compact = [
        {
            "id": a.get("alert_id") or a.get("id"),
            "title": a.get("title"),
            "message": a.get("message"),
            "severity": a.get("severity"),
            "source": a.get("source"),
            "resource_id": (a.get("affected_resources") or [None])[0],
            "resource_type": a.get("resource_type"),
            "region": a.get("region"),
            "timestamp": a.get("timestamp"),
        }
        for a in alerts
    ]
    return (
        f"Incident {incident.get('incident_id')} "
        f"(severity={incident.get('severity')}, "
        f"resources={incident.get('resources_affected')}).\n\n"
        f"Alerts in this incident (chronological):\n"
        f"{json.dumps(alerts_compact, indent=2, default=str)}\n\n"
        f"Investigate as needed via tools, then call `submit_analysis`."
    )


def _to_ui_shape(submitted: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "rootCause": {
            "primaryCause": submitted["primary_cause"],
            "contributingFactors": submitted["contributing_factors"],
            "immediateActions": submitted["immediate_actions"],
            "confidence": submitted["confidence"],
        },
        "checklist": [
            {"id": str(i + 1), "task": task, "completed": False}
            for i, task in enumerate(submitted["checklist"])
        ],
    }


# ---------------------------------------------------------------------------
# The agent loop (Converse API)
# ---------------------------------------------------------------------------

def _converse_content_blocks(content: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter out empty/null blocks; Converse rejects them."""
    return [b for b in content if b]


def _run_agent(incident: Dict[str, Any], alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
    client = boto3.client("bedrock-runtime", region_name=AWS_REGION)

    messages: List[Dict[str, Any]] = [
        {"role": "user", "content": [{"text": _build_user_prompt(incident, alerts)}]}
    ]

    for _ in range(MAX_LOOP_TURNS):
        response = client.converse(
            modelId=MODEL,
            messages=messages,
            system=[{"text": SYSTEM_PROMPT}],
            toolConfig=TOOL_CONFIG,
            inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": 0.2},
        )

        out_msg = response["output"]["message"]
        # Always append assistant turn so tool_use IDs stay paired with results.
        messages.append(out_msg)

        stop_reason = response.get("stopReason")
        content_blocks = out_msg.get("content", [])

        # Collect any tool calls in this turn.
        tool_uses = [b["toolUse"] for b in content_blocks if "toolUse" in b]

        if not tool_uses:
            # Model produced text without calling submit_analysis — nudge it.
            messages.append({
                "role": "user",
                "content": [{"text": "Please call `submit_analysis` now with your structured conclusion."}],
            })
            continue

        # If submit_analysis was called, we're done.
        for tu in tool_uses:
            if tu["name"] == "submit_analysis":
                return _to_ui_shape(tu["input"])

        # Otherwise execute every requested tool and feed results back.
        tool_results = []
        for tu in tool_uses:
            try:
                result = _execute_tool(tu["name"], tu["input"])
                tool_results.append({
                    "toolResult": {
                        "toolUseId": tu["toolUseId"],
                        "content": [{"json": result}],
                    }
                })
            except Exception as e:  # pragma: no cover — defensive
                tool_results.append({
                    "toolResult": {
                        "toolUseId": tu["toolUseId"],
                        "content": [{"text": f"Tool error: {e}"}],
                        "status": "error",
                    }
                })

        messages.append({"role": "user", "content": tool_results})

        # Some models return end_turn with no tool calls (handled above) or after
        # tool calls (we keep looping — model may chain).
        if stop_reason == "end_turn" and not tool_uses:
            break

    raise RuntimeError(f"Agent did not converge within {MAX_LOOP_TURNS} turns")


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

async def analyze_incident(incident_id: str, force: bool = False) -> Dict[str, Any]:
    """
    Run (or return cached) LLM analysis for an incident.

    Cached on the Incident row under `analysis`. Pass force=True to regenerate.
    """
    incident = get_incident(incident_id)
    if not incident:
        raise ValueError(f"Incident not found: {incident_id}")

    if not force and incident.get("analysis"):
        return incident["analysis"]

    alerts = get_alerts_for_incident(incident_id)
    if not alerts:
        raise ValueError(f"Incident {incident_id} has no member alerts")
    alerts.sort(key=lambda a: a.get("timestamp", ""))

    try:
        analysis = _run_agent(incident, alerts)
    except ClientError as e:
        raise RuntimeError(f"Bedrock error: {e}") from e

    # Cache on the incident row so the page re-loads instantly.
    incident["analysis"] = analysis
    upsert_incident(incident)

    return analysis
