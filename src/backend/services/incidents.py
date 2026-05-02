"""
Incident orchestration: fetch alerts -> persist -> correlate -> upsert incidents.

This is the bridge between the (currently dynamic) alert generation and the
new persisted Incidents/Alerts tables. It's intentionally read-mostly so it
can be hit on every page load without harm — both writes are idempotent
(stable alert_id, deterministic incident_id from correlation.py).

Layer-3 enrichment (LLM root-cause + mitigation checklist) lives in a
separate module and only runs once per incident, on demand.
"""

from datetime import datetime
from typing import Any, Dict, List

from connections.db import (
    get_alerts_for_incident,
    get_incident,
    list_incidents as db_list_incidents,
    set_alert_incident,
    upsert_alert,
    upsert_incident,
)
from services.alerts import generate_alerts_from_resources
from services.correlation import correlate_alerts


async def refresh_incidents() -> List[Dict[str, Any]]:
    """
    Pull current alerts, group them, persist everything, return the incidents.

    Idempotent: same inputs -> same incident_ids -> in-place updates.
    """
    alerts = await generate_alerts_from_resources()

    # Persist each alert (idempotent on alert_id).
    for a in alerts:
        if a.get("id"):
            upsert_alert({**a, "alert_id": a["id"]})

    # Correlate.
    incidents = correlate_alerts(alerts)

    # Persist each incident + back-reference each member alert to its incident.
    for inc in incidents:
        upsert_incident(inc)
        for alert_id in inc.get("member_alert_ids", []):
            set_alert_incident(alert_id, inc["incident_id"])

    return incidents


async def list_incidents() -> List[Dict[str, Any]]:
    """Cheap read: returns whatever's currently in the Incidents table."""
    items = db_list_incidents()
    items.sort(key=lambda i: i.get("created_at", ""), reverse=True)
    return items


async def get_incident_detail(incident_id: str) -> Dict[str, Any]:
    """
    Build the payload the Incident Room UI consumes:
      - timeline: member alerts ordered by timestamp
      - rootCause / checklist: from cached LLM analysis if present
        (call POST /incident/{id}/analyze to generate them)
    """
    alerts = get_alerts_for_incident(incident_id)
    alerts.sort(key=lambda a: a.get("timestamp", ""))

    timeline = [
        {
            "id": a.get("alert_id") or a.get("id"),
            "timestamp": a.get("timestamp"),
            "type": a.get("source", "Alert"),
            "source": a.get("source"),
            "message": a.get("message") or a.get("title"),
            "severity": a.get("severity"),
        }
        for a in alerts
    ]

    # Pull cached LLM analysis if it exists.
    incident = get_incident(incident_id) or {}
    analysis = incident.get("analysis") or {}

    return {
        "incident_id": incident_id,
        "timeline": timeline,
        "rootCause": analysis.get("rootCause"),
        "checklist": analysis.get("checklist") or [],
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
