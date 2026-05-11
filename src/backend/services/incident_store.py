"""
In-memory incident + alert store.

Replaces the Alerts and Incidents DynamoDB tables. All data is derived from
the Recommendations table at runtime — this store just caches the computed
grouping and any user/agent state (lifecycle status, LLM analysis).

Same function signatures as the old db.py helpers so callers don't change.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from decimal import Decimal

_alerts: Dict[str, Dict[str, Any]] = {}
_incidents: Dict[str, Dict[str, Any]] = {}


def _convert_floats(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _convert_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_floats(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

def upsert_alert(alert: dict):
    aid = alert.get("alert_id") or alert.get("id")
    if not aid:
        return None
    item = _convert_floats({**alert, "alert_id": aid, "last_seen_time": datetime.utcnow().isoformat()})
    _alerts[aid] = item
    return item


def get_alerts_for_incident(incident_id: str) -> List[Dict[str, Any]]:
    return [a for a in _alerts.values() if a.get("incident_id") == incident_id]


def set_alert_incident(alert_id: str, incident_id: str):
    if alert_id in _alerts:
        _alerts[alert_id]["incident_id"] = incident_id


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------

def upsert_incident(incident: dict):
    iid = incident.get("incident_id")
    if not iid:
        return None
    item = _convert_floats({**incident, "updated_at": datetime.utcnow().isoformat()})
    _incidents[iid] = item
    return item


def get_incident(incident_id: str) -> Optional[Dict[str, Any]]:
    return _incidents.get(incident_id)


def list_incidents() -> List[Dict[str, Any]]:
    return list(_incidents.values())


def clear_all():
    _alerts.clear()
    _incidents.clear()
