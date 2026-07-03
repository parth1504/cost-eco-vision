"""
Layer-2 alert correlation: LLM-assisted semantic merging across services.

Layer 1 (services/correlation.py) groups alerts using cheap deterministic
rules — same category, time window, shared resource OR shared business tag.
That misses cross-service incidents that don't share a tag and don't share
a resource id (e.g. a Lambda error storm that's actually caused by an IAM
permission change on a role the Lambda assumes).

Layer 2 takes the SINGLETONS that Layer 1 left behind and asks the model:
"are any of these singletons actually the same incident as each other, or
should they join an existing multi-alert incident?"

It's an OPT-IN step — never auto-runs on every page load. Triggered by
POST /incident/correlate-l2 once the user has already done a Layer-1 pass.

Cost shape: ONE Gemini call per invocation. Output is a structured set of
merge instructions that we apply to the persisted incidents.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Set

from connections.db import (
    get_alerts_for_incident,
    get_incident,
    list_incidents as db_list_incidents,
    set_alert_incident,
    upsert_incident,
)
from services.correlation import (
    SEVERITY_RANK,
    _alert_category,
    _alert_resources,
    _stable_incident_id,
    _parse_ts,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a Layer-2 correlation engine for an AWS incident
response system. Layer-1 deterministic rules already grouped alerts that
share resources or business tags. Your job is to catch cross-service
incidents Layer-1 missed.

You'll see:
  - Existing incidents (each with their member alerts)
  - Singleton alerts that didn't cluster with anything

Decide whether any singletons should:
  (a) JOIN an existing incident — because of cause-effect across services
      (e.g. an IAM policy change AND Lambda errors on a function that uses
      the affected role)
  (b) MERGE with each other into a new incident — same root cause, different
      services, no shared tag
  (c) Stay independent — most singletons are independent

Be CONSERVATIVE. Only merge when you have a clear story tying the alerts
together (cause-effect, shared blast surface, same time window). If you're
uncertain, leave them alone — false merges produce confusing incidents that
mix unrelated symptoms.

Cost / security / performance alerts NEVER merge across categories.

Output ONLY valid JSON in this exact shape:

{
  "merges": [
    {
      "type": "join_existing",
      "alert_ids": ["alert_id_1", "alert_id_2"],
      "incident_id": "INC-...",
      "reasoning": "one sentence on why these belong"
    },
    {
      "type": "create_new",
      "alert_ids": ["alert_id_3", "alert_id_4"],
      "title": "short descriptive title",
      "reasoning": "one sentence"
    }
  ]
}

If no merges are warranted, return: {"merges": []}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _alert_summary(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Compact representation for the prompt (avoid sending raw payloads)."""
    return {
        "id": alert.get("alert_id") or alert.get("id"),
        "title": alert.get("title"),
        "message": alert.get("message"),
        "severity": alert.get("severity"),
        "source": alert.get("source"),
        "category": alert.get("category"),
        "resource_id": (alert.get("affected_resources") or [None])[0],
        "resource_type": alert.get("resource_type"),
        "region": alert.get("region"),
        "timestamp": alert.get("timestamp"),
        "tags": alert.get("tags") or {},
    }


def _incident_summary(incident: Dict[str, Any], alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "incident_id": incident["incident_id"],
        "category": incident.get("category"),
        "severity": incident.get("severity"),
        "title": incident.get("title"),
        "resources_affected": incident.get("resources_affected", []),
        "shared_tags": incident.get("shared_tags") or {},
        "members": [_alert_summary(a) for a in alerts],
    }


def _extract_json(text: str) -> Dict[str, Any]:
    """Tolerate Gemini wrapping JSON in markdown fences or prose."""
    if not text:
        return {"merges": []}
    # Strip ```json ... ``` fences if present
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        # Find the first {...} block
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    try:
        return json.loads(text)
    except Exception as e:
        logger.warning("Layer 2: couldn't parse model output as JSON: %s", e)
        return {"merges": []}


# ---------------------------------------------------------------------------
# Apply merges
# ---------------------------------------------------------------------------

def _apply_join_existing(
    alert_ids: List[str],
    target_incident_id: str,
    all_alerts: Dict[str, Dict[str, Any]],
    reasoning: str,
) -> bool:
    """
    Move `alert_ids` into `target_incident_id`. Updates the target
    incident's member list, resources, severity, and re-points the alerts'
    incident_id back-reference.
    """
    target = get_incident(target_incident_id)
    if not target:
        logger.info("Layer 2: target incident %s not found, skipping join", target_incident_id)
        return False

    members = set(target.get("member_alert_ids") or [])
    members.update(alert_ids)
    target["member_alert_ids"] = sorted(members)

    # Recompute severity + resources from the union of alerts.
    members_alerts = [all_alerts[aid] for aid in members if aid in all_alerts]
    if members_alerts:
        sev_rank = max(
            SEVERITY_RANK.get((a.get("severity") or "low").lower(), 0)
            for a in members_alerts
        )
        target["severity"] = next(
            (k for k, v in SEVERITY_RANK.items() if v == sev_rank), target.get("severity")
        )
        all_resources: Set[str] = set(target.get("resources_affected") or [])
        for a in members_alerts:
            all_resources |= _alert_resources(a)
        target["resources_affected"] = sorted(all_resources)

    # Note the layer-2 merge so it's auditable.
    target["layer2_merges"] = (target.get("layer2_merges") or []) + [{
        "type": "join_existing",
        "joined_alert_ids": list(alert_ids),
        "reasoning": reasoning,
    }]

    upsert_incident(target)
    for aid in alert_ids:
        set_alert_incident(aid, target_incident_id)
    return True


def _apply_create_new(
    alert_ids: List[str],
    title: str,
    all_alerts: Dict[str, Dict[str, Any]],
    reasoning: str,
) -> str | None:
    """Create a new incident from a set of singleton alerts."""
    members_alerts = [all_alerts[aid] for aid in alert_ids if aid in all_alerts]
    if len(members_alerts) < 2:
        return None  # need at least 2 alerts to be a new "incident"

    # Use the first member's category — Layer 1 invariant: all members
    # of a Layer-2 cluster must share category. We enforce again here in
    # case the model violated it.
    categories = {_alert_category(a) for a in members_alerts}
    if len(categories) > 1:
        logger.info("Layer 2: refusing to create cross-category incident: %s", categories)
        return None

    earliest = min(_parse_ts(a.get("timestamp", "")) for a in members_alerts)
    all_resources: Set[str] = set()
    for a in members_alerts:
        all_resources |= _alert_resources(a)
    sorted_resources = sorted(all_resources)
    category = next(iter(categories))

    sev_rank = max(
        SEVERITY_RANK.get((a.get("severity") or "low").lower(), 0)
        for a in members_alerts
    )
    severity = next((k for k, v in SEVERITY_RANK.items() if v == sev_rank), "medium")

    new_incident = {
        "incident_id": _stable_incident_id(category, sorted_resources, earliest),
        "status": "open",
        "severity": severity,
        "category": category,
        "created_at": earliest.isoformat() + "Z",
        "member_alert_ids": sorted(alert_ids),
        "resources_affected": sorted_resources,
        "shared_tags": {},  # Layer-2 merges aren't required to share a tag
        "title": title or f"{category.capitalize()} incident across {len(sorted_resources)} resources",
        "source_count": len({a.get("source") for a in members_alerts if a.get("source")}),
        "layer2_merges": [{
            "type": "create_new",
            "alert_ids": sorted(alert_ids),
            "reasoning": reasoning,
        }],
    }
    upsert_incident(new_incident)
    for aid in alert_ids:
        set_alert_incident(aid, new_incident["incident_id"])
    return new_incident["incident_id"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_layer2_correlation() -> Dict[str, Any]:
    """
    Run a single Layer-2 pass over the current incidents.

    Returns a summary of what changed:
      {
        "joins_applied": N,
        "new_incidents_created": M,
        "model_output": {...},
      }
    """
    incidents = db_list_incidents()
    if not incidents:
        return {"joins_applied": 0, "new_incidents_created": 0, "model_output": {"merges": []}}

    # Bucket: existing multi-alert incidents vs singletons.
    existing: List[Dict[str, Any]] = []
    singletons: List[Dict[str, Any]] = []
    for inc in incidents:
        members = inc.get("member_alert_ids") or []
        if len(members) >= 2:
            existing.append(inc)
        elif len(members) == 1:
            singletons.append(inc)

    # Pull alert details for everything we'll send to the model.
    all_alerts: Dict[str, Dict[str, Any]] = {}
    existing_summaries = []
    for inc in existing:
        members = get_alerts_for_incident(inc["incident_id"])
        for a in members:
            aid = a.get("alert_id")
            if aid:
                all_alerts[aid] = a
        existing_summaries.append(_incident_summary(inc, members))

    singleton_alerts: List[Dict[str, Any]] = []
    for s in singletons:
        members = get_alerts_for_incident(s["incident_id"])
        for a in members:
            aid = a.get("alert_id")
            if aid:
                all_alerts[aid] = a
                singleton_alerts.append(a)

    if not singleton_alerts:
        return {"joins_applied": 0, "new_incidents_created": 0,
                "model_output": {"merges": []},
                "note": "No singleton alerts to consider."}

    # Build prompt.
    user_prompt = (
        f"Existing incidents (Layer-1 produced):\n"
        f"{json.dumps(existing_summaries, indent=2, default=str)}\n\n"
        f"Singleton alerts (didn't cluster with anything in Layer-1):\n"
        f"{json.dumps([_alert_summary(a) for a in singleton_alerts], indent=2, default=str)}\n\n"
        f"Decide which singletons should join existing incidents or merge "
        f"with each other into new incidents. Be conservative."
    )

    # Single-shot LLM call.
    from agent.llm.llm_client import get_llm_client
    llm = get_llm_client()
    raw = llm.generate(SYSTEM_PROMPT + "\n\n" + user_prompt)
    parsed = _extract_json(raw)
    merges = parsed.get("merges") or []

    # Apply merges.
    joins = 0
    creates = 0
    for m in merges:
        kind = m.get("type")
        if kind == "join_existing":
            ok = _apply_join_existing(
                alert_ids=m.get("alert_ids") or [],
                target_incident_id=m.get("incident_id", ""),
                all_alerts=all_alerts,
                reasoning=m.get("reasoning", ""),
            )
            if ok:
                joins += 1
        elif kind == "create_new":
            new_id = _apply_create_new(
                alert_ids=m.get("alert_ids") or [],
                title=m.get("title", ""),
                all_alerts=all_alerts,
                reasoning=m.get("reasoning", ""),
            )
            if new_id:
                creates += 1
        else:
            logger.info("Layer 2: ignoring unknown merge type %r", kind)

    return {
        "joins_applied": joins,
        "new_incidents_created": creates,
        "model_output": parsed,
    }
