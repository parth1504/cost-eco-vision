"""
Layer-1 alert correlation: deterministic, no LLM.

Groups a flat list of alerts into incidents using cheap rules:
  - time proximity  (alerts within TIME_WINDOW_MINUTES of each other)
  - resource overlap (same affected resource)
  - resource-type + region overlap (same blast surface)

Output: a list of incident clusters. Each cluster is a dict with
member alert ids, the resources involved, severity (max of members),
and a stable incident_id derived from the cluster's earliest alert
+ resource fingerprint (so re-running on the same alerts is idempotent).

Layer 2 (LLM-based semantic correlation across services) and Layer 3
(narrative + root cause) plug in on top of this — they consume incidents
this module produced and never touch raw alerts.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Set, Tuple

# Tuning knobs — keep at module level so they're easy to grep / override later.
TIME_WINDOW_MINUTES = 15

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_ts(ts: str) -> datetime:
    """Tolerate trailing 'Z' and missing tz."""
    if not ts:
        return datetime.utcnow()
    cleaned = ts.rstrip("Z")
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return datetime.utcnow()


def _alert_resources(alert: Dict[str, Any]) -> Set[str]:
    """All resource identifiers an alert touches, normalised to strings."""
    res = set(alert.get("affected_resources") or [])
    if alert.get("resource_id"):
        res.add(alert["resource_id"])
    return {str(r) for r in res if r}


def _max_severity(alerts: Iterable[Dict[str, Any]]) -> str:
    best = "low"
    best_rank = 0
    for a in alerts:
        sev = (a.get("severity") or "low").lower()
        rank = SEVERITY_RANK.get(sev, 0)
        if rank > best_rank:
            best_rank = rank
            best = sev
    return best


def _stable_incident_id(member_alert_ids: List[str], earliest_ts: datetime) -> str:
    """
    Deterministic id so re-running correlation on the same alerts produces
    the same incident_id (lets us upsert instead of duplicating).
    """
    fingerprint = "|".join(sorted(member_alert_ids))
    digest = hashlib.sha1(fingerprint.encode()).hexdigest()[:10]
    return f"INC-{earliest_ts.strftime('%Y%m%d')}-{digest}"


# ---------------------------------------------------------------------------
# Union-Find (cheap connected-components for clustering)
# ---------------------------------------------------------------------------

class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


# ---------------------------------------------------------------------------
# The correlation rule
# ---------------------------------------------------------------------------

def _are_related(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """
    Two alerts are 'related' (belong in the same incident) when:
      * they fired within TIME_WINDOW_MINUTES of each other, AND
      * they share at least one affected resource
        OR they share resource_type + region (same blast surface).
    """
    ts_a = _parse_ts(a.get("timestamp", ""))
    ts_b = _parse_ts(b.get("timestamp", ""))
    if abs((ts_a - ts_b).total_seconds()) > TIME_WINDOW_MINUTES * 60:
        return False

    if _alert_resources(a) & _alert_resources(b):
        return True

    same_type = a.get("resource_type") and a.get("resource_type") == b.get("resource_type")
    same_region = a.get("region") and a.get("region") == b.get("region")
    if same_type and same_region:
        return True

    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def correlate_alerts(alerts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Group alerts into incidents.

    Returns a list of incidents, each shaped like:
        {
          "incident_id":          "INC-YYYYMMDD-<hash>",
          "status":               "open",
          "severity":             "critical",
          "created_at":           "2024-..." (earliest member ts),
          "member_alert_ids":     [...],
          "resources_affected":   [...],
          "title":                "<derived from first alert>",
          "source_count":         <distinct sources represented>,
        }

    Frontend's "Incident Timeline" panel can be built directly from
    member_alert_ids ordered by timestamp.
    """
    if not alerts:
        return []

    n = len(alerts)
    uf = _UnionFind(n)

    # O(n^2) is fine here — alert volumes are small. If this ever
    # gets hot, bucket by resource_id first then only compare within buckets.
    for i in range(n):
        for j in range(i + 1, n):
            if _are_related(alerts[i], alerts[j]):
                uf.union(i, j)

    # Group indices by their root.
    clusters: Dict[int, List[int]] = {}
    for idx in range(n):
        clusters.setdefault(uf.find(idx), []).append(idx)

    incidents: List[Dict[str, Any]] = []
    for member_idxs in clusters.values():
        members = [alerts[i] for i in member_idxs]
        member_ids = [m["id"] for m in members if m.get("id")]
        earliest = min((_parse_ts(m.get("timestamp", "")) for m in members), default=datetime.utcnow())

        all_resources: Set[str] = set()
        for m in members:
            all_resources |= _alert_resources(m)

        sources = {m.get("source") for m in members if m.get("source")}

        # Title: prefer the highest-severity alert's title.
        leading = max(
            members,
            key=lambda m: SEVERITY_RANK.get((m.get("severity") or "low").lower(), 0),
        )

        incidents.append({
            "incident_id": _stable_incident_id(member_ids, earliest),
            "status": "open",
            "severity": _max_severity(members),
            "created_at": earliest.isoformat() + "Z",
            "member_alert_ids": member_ids,
            "resources_affected": sorted(all_resources),
            "title": leading.get("title") or "Untitled incident",
            "source_count": len(sources),
        })

    # Newest first — UI usually wants this order.
    incidents.sort(key=lambda i: i["created_at"], reverse=True)
    return incidents
