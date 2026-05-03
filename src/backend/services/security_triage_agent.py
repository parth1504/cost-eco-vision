"""
Security findings triage agent — provider-agnostic Bedrock Converse API.

Takes the deterministic findings produced by services/security.py
(boto3-powered checks for unencrypted buckets, open SGs, admin IAM users,
etc.) and enriches each one with judgment that pure rules can't provide:

  - **Contextualised severity** — a public bucket holding logs is not the same
    as a public bucket holding customer PII. Raw severity is a coarse hint;
    the model adjusts based on tags, related findings, and resource role.
  - **Plain-language "why this matters"** — translates `0.0.0.0/0 ingress on
    port 22` into "anyone on the internet can SSH to this host".
  - **Tailored remediation** — the hardcoded boto3 sequences are one-size-
    fits-all; the model can call out caveats specific to *this* resource
    (e.g. "this bucket is referenced by 3 Lambdas — coordinate a deploy").
  - **Blast radius + correlations** — explicitly flags other findings that
    share the same blast surface (same bucket, same VPC, same IAM principal).

The agent runs once on the FULL findings list per request, calling
`submit_finding_triage` once per finding it triaged. Output is cached per
finding_id so re-running the security scan reuses prior triage instead of
paying for the LLM call again.

This is a near-clone of services/incident_agent.py — same Converse loop,
same model selection, same caching philosophy. Different prompt, different
tools, different output shape.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import boto3
from botocore.exceptions import ClientError

from connections.db import (
    get_resource_from_db,
    upsert_security_triage,
)

MODEL = os.getenv("BEDROCK_MODEL_ID", "global.anthropic.claude-opus-4-6-v1")
AWS_REGION = (
    os.getenv("BEDROCK_REGION")
    or os.getenv("AWS_REGION")
    or os.getenv("AWS_DEFAULT_REGION")
    or "us-east-1"
)

MAX_LOOP_TURNS = 16          # higher than incident agent — many findings = many tool calls
MAX_TOKENS = 4096

SYSTEM_PROMPT = """You are a senior AWS security engineer doing incident triage.

You will be given a batch of security findings detected in an AWS account by
deterministic boto3 checks (S3 bucket encryption, open Security Groups, IAM
users with admin-like permissions, etc.). The raw findings already include a
generic title, severity, description, and a one-size-fits-all remediation.

Your job is to add judgment that the deterministic checks can't:

  1. **Contextualise severity.** Use `get_resource_details` and inspect the
     finding metadata to decide whether the raw severity is right for THIS
     resource. A public bucket called `public-website-assets` is fine; a
     public bucket called `customer-pii-backups` is critical. Adjust up or
     down. If the raw severity is correct, keep it.
  2. **Identify correlations.** When multiple findings touch the same
     resource (same bucket, same SG, same IAM principal), or when one
     finding enables another (open SG + unencrypted EBS = much worse), call
     them out as `related_finding_ids`.
  3. **Write a plain-language explanation.** Translate "ingress 0.0.0.0/0 on
     port 22" into something a non-engineer stakeholder can understand:
     "anyone on the internet can attempt to SSH to this host".
  4. **Tailor the remediation.** Add caveats specific to THIS resource. If
     the hardcoded fix is "enable bucket encryption", note any downstream
     impact you can infer (e.g. "this bucket is referenced in DynamoDB
     recommendations — coordinate with the team using it").
  5. **End by calling `submit_finding_triage` exactly ONCE per finding** in
     the input batch. After triaging the last finding, stop.

Guidance:
  - Be specific. "Could be exploited" is useless; "An attacker could read
    customer PII from this bucket because it's tagged Environment=prod and
    has no encryption at rest or block-public-access" is useful.
  - If you adjust severity, explain why in `severity_rationale`.
  - `related_finding_ids` must reference IDs that appear in the input batch.
  - `confidence` is an integer 0-100. Be honest.
  - Keep `why_it_matters` to 1-2 sentences.
  - Keep `tailored_remediation_notes` short — these AUGMENT the existing
    hardcoded steps; they don't replace them."""


# ---------------------------------------------------------------------------
# Tool schemas (Converse API format)
# ---------------------------------------------------------------------------

TOOL_CONFIG: Dict[str, Any] = {
    "tools": [
        {
            "toolSpec": {
                "name": "get_resource_details",
                "description": (
                    "Fetch the cached recommendation/metadata record for an "
                    "AWS resource from our Recommendations DynamoDB table. "
                    "Returns tags, region, monthly cost, utilization, and any "
                    "prior recommendations. Use this to decide whether a "
                    "finding's raw severity is right for THIS resource — "
                    "tags often reveal whether it's prod/dev, what data it "
                    "holds, who owns it."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "resource_id": {
                                "type": "string",
                                "description": "Resource id from the finding (e.g. bucket name, sg-id, IAM user name).",
                            },
                            "resource_type": {
                                "type": "string",
                                "description": "Resource type (e.g. 'S3', 'SecurityGroup', 'IAMUser', 'EC2').",
                            },
                        },
                        "required": ["resource_id", "resource_type"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "submit_finding_triage",
                "description": (
                    "Submit your structured triage for ONE finding. Call this "
                    "exactly once per finding in the input batch. Do NOT call "
                    "it more than once for the same finding_id."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "finding_id": {
                                "type": "string",
                                "description": "The id from the input finding (must match exactly).",
                            },
                            "contextualised_severity": {
                                "type": "string",
                                "enum": ["Critical", "High", "Medium", "Low"],
                                "description": "Severity adjusted for context. May equal raw severity.",
                            },
                            "severity_rationale": {
                                "type": "string",
                                "description": "One sentence explaining why you kept or changed the severity.",
                            },
                            "why_it_matters": {
                                "type": "string",
                                "description": "Plain-language 1-2 sentence explanation of the actual risk.",
                            },
                            "blast_radius": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "1-3 short bullets on what's exposed/affected.",
                            },
                            "tailored_remediation_notes": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Caveats or context-specific notes ON TOP of the existing hardcoded remediation.",
                            },
                            "related_finding_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "IDs of other findings (from the input batch) that share blast radius or causally relate.",
                            },
                            "confidence": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 100,
                                "description": "Honest confidence 0-100.",
                            },
                        },
                        "required": [
                            "finding_id",
                            "contextualised_severity",
                            "severity_rationale",
                            "why_it_matters",
                            "blast_radius",
                            "confidence",
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

def _tool_get_resource_details(resource_id: str, resource_type: str) -> Dict[str, Any]:
    item = get_resource_from_db(resource_id, resource_type)
    if not item:
        return {"found": False, "resource_id": resource_id, "resource_type": resource_type}
    safe = json.loads(json.dumps(item, default=str))
    return {"found": True, "resource": safe}


def _execute_tool(name: str, args: Dict[str, Any]) -> Any:
    if name == "get_resource_details":
        return _tool_get_resource_details(args["resource_id"], args["resource_type"])
    return {"error": f"Unknown tool: {name}"}


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_user_prompt(findings: List[Dict[str, Any]]) -> str:
    """Compact representation of the full findings batch."""
    compact = [
        {
            "id": f.get("id"),
            "title": f.get("title"),
            "raw_severity": f.get("severity"),
            "description": f.get("description"),
            "resource": f.get("resource"),
            "resource_type": f.get("resource_type"),
            "compliance_tags": f.get("compliance"),
            "status": f.get("status"),
        }
        for f in findings
    ]
    return (
        f"There are {len(findings)} security findings in this AWS account that need triage.\n\n"
        f"Findings (raw, from deterministic boto3 checks):\n"
        f"{json.dumps(compact, indent=2, default=str)}\n\n"
        f"Use `get_resource_details` as needed to inspect specific resources, then call "
        f"`submit_finding_triage` exactly once per finding above (use the `id` field as "
        f"`finding_id`). After the last submission, stop — no further text needed."
    )


# ---------------------------------------------------------------------------
# Output normalisation (snake_case from tool → camelCase for the UI)
# ---------------------------------------------------------------------------

def _to_storage_shape(submitted: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "contextualisedSeverity": submitted["contextualised_severity"],
        "severityRationale": submitted["severity_rationale"],
        "whyItMatters": submitted["why_it_matters"],
        "blastRadius": submitted.get("blast_radius", []),
        "tailoredRemediationNotes": submitted.get("tailored_remediation_notes", []),
        "relatedFindingIds": submitted.get("related_finding_ids", []),
        "confidence": submitted["confidence"],
    }


# ---------------------------------------------------------------------------
# The agent loop (Converse API)
# ---------------------------------------------------------------------------

def _run_agent(findings: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Run one batch triage. Returns {finding_id: triage_payload} for every
    finding the model successfully triaged. Findings the model skipped are
    simply absent from the result.
    """
    client = boto3.client("bedrock-runtime", region_name=AWS_REGION)

    messages: List[Dict[str, Any]] = [
        {"role": "user", "content": [{"text": _build_user_prompt(findings)}]}
    ]
    triages: Dict[str, Dict[str, Any]] = {}
    expected_ids = {f.get("id") for f in findings if f.get("id")}

    for _ in range(MAX_LOOP_TURNS):
        response = client.converse(
            modelId=MODEL,
            messages=messages,
            system=[{"text": SYSTEM_PROMPT}],
            toolConfig=TOOL_CONFIG,
            inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": 0.2},
        )

        out_msg = response["output"]["message"]
        messages.append(out_msg)
        content_blocks = out_msg.get("content", [])
        tool_uses = [b["toolUse"] for b in content_blocks if "toolUse" in b]

        if not tool_uses:
            # Model produced text without any tool calls.
            # If we haven't covered all findings yet, nudge it; otherwise we're done.
            missing = expected_ids - set(triages.keys())
            if missing:
                messages.append({
                    "role": "user",
                    "content": [{
                        "text": (
                            f"You still haven't triaged these finding ids: "
                            f"{sorted(missing)}. Call `submit_finding_triage` "
                            f"for each one now."
                        )
                    }],
                })
                continue
            break

        # Process tool calls. submit_finding_triage results are recorded;
        # other tools get executed and fed back to the model.
        tool_results = []
        for tu in tool_uses:
            if tu["name"] == "submit_finding_triage":
                fid = tu["input"].get("finding_id")
                if fid in expected_ids:
                    triages[fid] = _to_storage_shape(tu["input"])
                # Always ack the call so the loop progresses cleanly.
                tool_results.append({
                    "toolResult": {
                        "toolUseId": tu["toolUseId"],
                        "content": [{"json": {"recorded": True, "finding_id": fid}}],
                    }
                })
            else:
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

        # Early exit if we already have triage for everything.
        if expected_ids and expected_ids.issubset(triages.keys()):
            break

    return triages


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def triage_findings(findings: List[Dict[str, Any]], force: bool = False) -> Dict[str, Dict[str, Any]]:
    """
    Triage a batch of findings. Caches per finding_id. Pass force=True to
    regenerate.

    Returns: {finding_id: triage_payload} — same keys as input findings (where
    triage succeeded), but also merges in cached entries for ones the model
    didn't process this run.
    """
    if not findings:
        return {}

    # Skip findings that already have cached triage (unless forcing).
    from connections.db import get_security_triage
    to_run: List[Dict[str, Any]] = []
    cached: Dict[str, Dict[str, Any]] = {}
    for f in findings:
        fid = f.get("id")
        if not fid:
            continue
        if not force:
            existing = get_security_triage(fid)
            if existing:
                # Strip storage metadata before returning to caller.
                triage = {k: v for k, v in existing.items() if k not in ("finding_id", "cached_at")}
                cached[fid] = triage
                continue
        to_run.append(f)

    if not to_run:
        return cached

    try:
        fresh = _run_agent(to_run)
    except ClientError as e:
        raise RuntimeError(f"Bedrock error: {e}") from e

    for fid, payload in fresh.items():
        upsert_security_triage(fid, payload)

    return {**cached, **fresh}
