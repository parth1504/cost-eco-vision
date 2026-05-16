"""
Incident orchestration: fetch alerts -> persist -> correlate -> upsert incidents.

This is the bridge between the (currently dynamic) alert generation and the
persisted Incidents/Alerts tables. It's intentionally read-mostly so it can
be hit on every page load without harm — both writes are idempotent (stable
alert_id, deterministic incident_id from correlation.py).

Tier A — incident persistence + lifecycle:
  When re-correlating, Layer 1 produces a fresh dict per incident from raw
  alerts. We MERGE that into the existing DDB row instead of overwriting it,
  so user-set fields (status, lifecycle timestamps, LLM analysis cache, notes)
  survive across refreshes. Status follows a state machine:
      open → investigating → mitigated → resolved
  Lifecycle timestamps (`investigating_at`, `mitigated_at`, `resolved_at`)
  are set on transition and never cleared.

Layer-3 enrichment (LLM root-cause + mitigation checklist) lives in
services/incident_agent.py and only runs once per incident, on demand.
"""

from datetime import datetime
from typing import Any, Dict, List, Set

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


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

VALID_STATUSES = ("open", "investigating", "mitigated", "resolved")

# Forward-only state machine. Allowed transitions:
#   open → investigating, mitigated, resolved
#   investigating → mitigated, resolved
#   mitigated → resolved
# Going backwards (e.g. resolved → open) is intentional reopening; allow it
# but reset the resolved_at marker so timing is honest.
_FORWARD_ALLOWED: Dict[str, Set[str]] = {
    "open":          {"investigating", "mitigated", "resolved"},
    "investigating": {"mitigated", "resolved", "open"},
    "mitigated":     {"resolved", "investigating", "open"},
    "resolved":      {"open", "investigating"},
}

_TRANSITION_TIMESTAMP_FIELDS = {
    "investigating": "investigating_at",
    "mitigated":     "mitigated_at",
    "resolved":      "resolved_at",
}


def _is_valid_transition(current: str, new: str) -> bool:
    if new not in VALID_STATUSES:
        return False
    if current == new:
        return True  # idempotent no-op
    return new in _FORWARD_ALLOWED.get(current or "open", set())


# ---------------------------------------------------------------------------
# Merge logic — preserve user-set fields when re-correlating
# ---------------------------------------------------------------------------

# Fields the correlation engine OWNS — always recomputed on refresh.
_CORRELATION_OWNED_FIELDS = {
    "severity",          # max of current member severities
    "category",
    "title",              # leading alert's title
    "member_alert_ids",
    "resources_affected",
    "shared_tags",
    "source_count",
}

# Fields the user / agents own — preserved across refreshes if they exist.
_USER_OWNED_FIELDS = {
    "status",
    "investigating_at",
    "mitigated_at",
    "resolved_at",
    "analysis",          # LLM-generated root cause + checklist (expensive)
    "notes",
    "assigned_to",
    "dismissed_at",
}


def _merge_incident(existing: Dict[str, Any], fresh: Dict[str, Any]) -> Dict[str, Any]:
    """
    Combine a freshly-correlated incident dict with the previously-persisted
    DDB row. The correlation engine's fields win on every refresh; user-set
    state (status, analysis cache, etc.) is preserved verbatim.

    `created_at` is special: anchored to the FIRST time we ever saw this
    incident. Never overwritten on re-correlation.
    """
    if not existing:
        # First time seeing this incident — just default the lifecycle fields.
        return {**fresh, "status": "open"}

    merged = dict(existing)  # start from persisted state

    # Correlation-owned fields → take fresh.
    for k in _CORRELATION_OWNED_FIELDS:
        if k in fresh:
            merged[k] = fresh[k]

    # created_at: anchor to the existing value if we have one.
    merged["created_at"] = existing.get("created_at") or fresh.get("created_at")

    # Default status if missing (e.g. legacy rows from before this change).
    if not merged.get("status"):
        merged["status"] = "open"

    # User-owned fields are already preserved by starting from `existing`.
    return merged


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def refresh_incidents() -> List[Dict[str, Any]]:
    """
    Pull current alerts, group them, persist everything, return the incidents.

    Idempotent: same inputs → same incident_ids → in-place updates that
    PRESERVE user-set state (status, LLM analysis cache, lifecycle
    timestamps).
    """
    alerts = await generate_alerts_from_resources()

    # Deduplicate alerts by id before persisting
    seen_ids = set()
    unique_alerts = []
    for a in alerts:
        aid = a.get("id")
        if aid and aid not in seen_ids:
            seen_ids.add(aid)
            unique_alerts.append(a)
    alerts = unique_alerts

    # Persist each alert (idempotent on alert_id).
    for a in alerts:
        if a.get("id"):
            upsert_alert({**a, "alert_id": a["id"]})

    # Correlate fresh.
    fresh_incidents = correlate_alerts(alerts)

    # Merge into existing rows + persist.
    final_incidents: List[Dict[str, Any]] = []
    for fresh in fresh_incidents:
        existing = get_incident(fresh["incident_id"])
        merged = _merge_incident(existing, fresh)
        upsert_incident(merged)
        for alert_id in merged.get("member_alert_ids", []):
            set_alert_incident(alert_id, merged["incident_id"])
        final_incidents.append(merged)

    return final_incidents


async def list_incidents(include_resolved: bool = True) -> List[Dict[str, Any]]:
    """
    Read the Incidents table. By default returns everything; pass
    include_resolved=False to filter resolved incidents out of the response.
    """
    items = db_list_incidents()
    if not include_resolved:
        items = [i for i in items if (i.get("status") or "open") != "resolved"]
    items.sort(key=lambda i: i.get("created_at", ""), reverse=True)
    return items


async def get_incident_detail(incident_id: str) -> Dict[str, Any]:
    """
    Build the payload the Incident Room UI consumes:
      - timeline: member alerts ordered by timestamp
      - status + lifecycle timestamps
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

    incident = get_incident(incident_id) or {}
    analysis = incident.get("analysis") or {}

    return {
        "incident_id": incident_id,
        "status": incident.get("status") or "open",
        "investigating_at": incident.get("investigating_at"),
        "mitigated_at": incident.get("mitigated_at"),
        "resolved_at": incident.get("resolved_at"),
        "timeline": timeline,
        "rootCause": analysis.get("rootCause"),
        "checklist": analysis.get("checklist") or [],
        "service_topology": incident.get("service_topology"),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


async def update_incident_status(incident_id: str, new_status: str) -> Dict[str, Any]:
    """
    Transition an incident to a new lifecycle status. Sets the corresponding
    `<status>_at` timestamp on first entry into that state.

    Raises:
      ValueError if the transition isn't allowed.
    """
    incident = get_incident(incident_id)
    if not incident:
        raise ValueError(f"Incident not found: {incident_id}")

    current = incident.get("status") or "open"
    if not _is_valid_transition(current, new_status):
        raise ValueError(
            f"Invalid transition {current!r} → {new_status!r}. "
            f"Allowed next states: {sorted(_FORWARD_ALLOWED.get(current, set()))}"
        )

    incident["status"] = new_status

    # Stamp the lifecycle timestamp the first time we enter that state.
    ts_field = _TRANSITION_TIMESTAMP_FIELDS.get(new_status)
    if ts_field and not incident.get(ts_field):
        incident[ts_field] = datetime.utcnow().isoformat() + "Z"

    # Reopening → clear resolved_at so the elapsed-time math is honest if it
    # gets re-resolved later.
    if new_status == "open":
        incident.pop("resolved_at", None)

    upsert_incident(incident)
    return incident
