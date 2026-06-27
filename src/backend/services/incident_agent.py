"""
Incident analysis agent — uses the existing Gemini LLM client (get_llm_client / generate).

Given a correlated incident (the cluster of alerts produced by correlation.py),
sends a structured prompt to the Gemini proxy and parses the response into the
UI shape the frontend already renders:

  rootCause:
    primaryCause / contributingFactors / immediateActions / confidence
  checklist: [{id, task, completed}]

The result is cached on the Incident row so re-opening the page is free.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from connections.db import (
    get_alerts_for_incident,
    get_incident,
    get_resource_from_db,
    upsert_incident,
)
from agent.llm.llm_client import get_llm_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_prompt(
    incident: Dict[str, Any],
    alerts: List[Dict[str, Any]],
) -> str:
    incident_id = incident.get("incident_id", "unknown")
    severity    = incident.get("severity", "unknown")
    resources   = incident.get("resources_affected", [])
    topology    = incident.get("service_topology") or {}

    # Format alerts block
    alert_lines = []
    for a in alerts:
        ts  = a.get("timestamp", "")
        src = a.get("source", a.get("resource_id", "?"))
        sev = a.get("severity", "")
        msg = a.get("message") or a.get("title") or ""
        alert_lines.append(f"  [{ts}] [{sev}] {src}: {msg}")
    alerts_block = "\n".join(alert_lines) if alert_lines else "  (no alerts)"

    # Format topology block
    topo_lines = []
    root_services = []
    for svc, meta in topology.items():
        deps = meta.get("depends_on") or []
        is_root = meta.get("is_root_cause", False)
        marker = " ← ROOT CAUSE" if is_root else ""
        dep_str = f"depends on [{', '.join(deps)}]" if deps else "no dependencies"
        topo_lines.append(f"  {svc} ({meta.get('type', 'service')}) — {dep_str}{marker}")
        if is_root:
            root_services.append(svc)
    topo_block = "\n".join(topo_lines) if topo_lines else "  (no topology available)"

    return f"""You are a senior cloud operations engineer conducting incident root cause analysis.

INCIDENT: {incident_id}
SEVERITY: {severity}
AFFECTED SERVICES: {', '.join(resources)}

SERVICE DEPENDENCY TOPOLOGY:
{topo_block}

ALERTS (chronological):
{alerts_block}

Analyse the cascade of failures shown above. The topology tells you which services depend on which — failures propagate downstream. Identify the root service and explain the full failure chain.

Respond ONLY in this exact format (no markdown, no extra text):

PRIMARY_CAUSE: <one concise sentence identifying the root service and what failed>
CONTRIBUTING_FACTORS:
- <specific factor 1 with evidence from alerts>
- <specific factor 2 with evidence from alerts>
- <specific factor 3>
- <specific factor 4 (optional)>
IMMEDIATE_ACTIONS:
- <containment step 1>
- <fix step 2>
- <fix step 3>
- <verification step 4>
CONFIDENCE: <integer 0-100>
CHECKLIST:
- <short imperative task 1>
- <short imperative task 2>
- <short imperative task 3>
- <short imperative task 4>
- <short imperative task 5>"""


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_response(text: str) -> Dict[str, Any]:
    """Parse the structured LLM response into the UI shape."""
    result: Dict[str, Any] = {
        "primaryCause": "",
        "contributingFactors": [],
        "immediateActions": [],
        "confidence": 70,
        "checklist": [],
    }

    current_section: Optional[str] = None
    current_list: List[str] = []

    def _flush():
        nonlocal current_list
        if current_section == "CONTRIBUTING_FACTORS":
            result["contributingFactors"] = current_list[:]
        elif current_section == "IMMEDIATE_ACTIONS":
            result["immediateActions"] = current_list[:]
        elif current_section == "CHECKLIST":
            result["checklist"] = current_list[:]
        current_list = []

    for raw_line in text.strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("PRIMARY_CAUSE:"):
            _flush()
            current_section = None
            result["primaryCause"] = line[len("PRIMARY_CAUSE:"):].strip()

        elif line.startswith("CONTRIBUTING_FACTORS:"):
            _flush()
            current_section = "CONTRIBUTING_FACTORS"
            current_list = []

        elif line.startswith("IMMEDIATE_ACTIONS:"):
            _flush()
            current_section = "IMMEDIATE_ACTIONS"
            current_list = []

        elif line.startswith("CONFIDENCE:"):
            _flush()
            current_section = None
            raw = line[len("CONFIDENCE:"):].strip()
            m = re.search(r"\d+", raw)
            if m:
                result["confidence"] = max(0, min(100, int(m.group())))

        elif line.startswith("CHECKLIST:"):
            _flush()
            current_section = "CHECKLIST"
            current_list = []

        elif line.startswith("- ") and current_section:
            current_list.append(line[2:].strip())

    _flush()

    # Ensure we always have something in each list
    if not result["contributingFactors"]:
        result["contributingFactors"] = ["Unable to determine contributing factors from available data"]
    if not result["immediateActions"]:
        result["immediateActions"] = ["Investigate root service logs", "Check downstream service health"]
    if not result["checklist"]:
        result["checklist"] = ["Review alerts", "Identify root service", "Apply mitigation", "Verify recovery"]

    return result


def _to_ui_shape(parsed: Dict[str, Any], incident_id: str) -> Dict[str, Any]:
    return {
        "rootCause": {
            "primaryCause": parsed["primaryCause"],
            "contributingFactors": parsed["contributingFactors"],
            "immediateActions": parsed["immediateActions"],
            "confidence": parsed["confidence"],
        },
        "checklist": [
            {"id": str(i + 1), "task": task, "completed": False}
            for i, task in enumerate(parsed["checklist"])
        ],
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def analyze_incident(incident_id: str, force: bool = False) -> Dict[str, Any]:
    """
    Run (or return cached) LLM analysis for an incident using the Gemini client.

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

    prompt = _build_prompt(incident, alerts)

    llm = get_llm_client()
    try:
        raw = llm.generate(prompt)
    except Exception as e:
        logger.error(f"LLM generate failed for {incident_id}: {e}")
        raise RuntimeError(f"LLM error: {e}") from e

    if not raw:
        raise RuntimeError("LLM returned empty response")

    parsed  = _parse_response(raw)
    analysis = _to_ui_shape(parsed, incident_id)

    # Cache on the incident row so the page re-loads instantly.
    incident["analysis"] = analysis
    upsert_incident(incident)

    return analysis
