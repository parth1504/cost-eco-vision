"""
Layer-1 alert correlation: deterministic, no LLM.

Groups a flat list of alerts into incidents using cheap rules:
  - **Time proximity** (alerts within TIME_WINDOW_MINUTES of each other)
  - **Same category** — cost / security / performance / drift never merge
    (different responders, different lifecycles, different blast surfaces)
  - **Shared blast surface** — at least one of:
      * same affected resource_id
      * shared business tag (Service, Owner, Environment, Application)

Output: a list of incident clusters. Each cluster carries a stable
`incident_id` derived from `(date + category + sorted resources_affected)` —
re-running on the same alerts (or a superset where new alerts join the same
resources) produces the same id, so upserts are idempotent and UIs can
bookmark incident URLs without breaking on the next scan.

Layer 2 (LLM-based semantic correlation across services) and Layer 3
(narrative + root cause) plug in on top of this — they consume incidents
this module produced and never touch raw alerts.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Set, Tuple

# Tuning knobs — keep at module level so they're easy to grep / override later.

# Default time window when the alert's category isn't in the per-category map.
DEFAULT_TIME_WINDOW_MINUTES = 15

# Per-category time windows. Different domains have different natural rhythms:
#   - security alerts: tight cause-effect chains, but slow-cause/fast-effect
#     means we should look back further than performance signals
#   - cost alerts: slow-moving (daily aggregates), so a wider window is
#     needed to group flare-ups of the same root cause
#   - performance alerts: should cluster tightly — fast incidents, fast
#     correlation
#   - drift: configuration changes propagate over tens of minutes
TIME_WINDOWS_BY_CATEGORY: dict[str, int] = {
    "security": 30,
    "cost": 60,
    "performance": 10,
    "drift": 30,
}

# Backward-compat constant — keep for `scripts/test_correlation.py` and any
# other code that reads it. Mirrors DEFAULT_TIME_WINDOW_MINUTES.
TIME_WINDOW_MINUTES = DEFAULT_TIME_WINDOW_MINUTES

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}

# Tags that signal "these resources are part of the same business surface".
# If two alerts share any of these (key + value), they're considered related
# regardless of differing resource_ids.
CORRELATION_TAGS = ("Service", "Owner", "Environment", "Application", "Team")


def _window_for_category(category: str) -> int:
    """Resolve the time window for a category, falling back to default."""
    return TIME_WINDOWS_BY_CATEGORY.get((category or "").lower(), DEFAULT_TIME_WINDOW_MINUTES)


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


def _alert_category(alert: Dict[str, Any]) -> str:
    """Best-effort category extraction. Prefers explicit `category`, falls
    back to `source` (lowercased), then "other"."""
    cat = (alert.get("category") or "").strip().lower()
    if cat:
        return cat
    src = (alert.get("source") or "other").strip().lower()
    return src


def _alert_tags(alert: Dict[str, Any]) -> Dict[str, str]:
    """Normalise tags to a {str: str} dict, ignoring empty values."""
    tags = alert.get("tags") or {}
    return {str(k): str(v) for k, v in tags.items() if k and v}


def _shared_correlation_tag(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """True if a and b share a value on any tag in CORRELATION_TAGS."""
    ta = _alert_tags(a)
    tb = _alert_tags(b)
    for key in CORRELATION_TAGS:
        va = ta.get(key)
        vb = tb.get(key)
        if va and vb and va == vb:
            return True
    return False


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


def _stable_incident_id(category: str, resources: List[str], earliest_ts: datetime) -> str:
    """
    Deterministic id derived from (category + sorted resources + date + time bucket).

    Inputs and why:
      - **Resources** instead of member ids: the same incident can pick up
        new alerts on the SAME resources without changing id.
      - **Category**: cost vs security incidents on overlapping resources
        are different incidents and must have different ids.
      - **Date**: a recurring misconfiguration on the same bucket on
        different days should be different incidents.
      - **Time bucket** (Tier S #C fix): two clusters with identical
        category + resources + date but separated in time (>1 window apart)
        used to collide on the same incident_id and overwrite each other in
        DDB. The bucket size matches the category's correlation window, so
        alerts that *can* cluster always land in the same bucket and alerts
        that *can't* cluster always land in different buckets.
    """
    window = _window_for_category(category)
    minutes_of_day = earliest_ts.hour * 60 + earliest_ts.minute
    time_bucket = minutes_of_day // window
    fingerprint = f"{category}|{time_bucket}|" + "|".join(sorted(resources))
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
    # 1. Category — allow cross-category if SAME resource
    cat_a = _alert_category(a)
    cat_b = _alert_category(b)
    
    same_category = (cat_a == cat_b)
    
    # If different categories, only allow merge if they share an exact resource
    if not same_category:
        shared_resources = _alert_resources(a) & _alert_resources(b)
        if not shared_resources:
            return False
        # Use the wider time window of the two categories
        window = max(_window_for_category(cat_a), _window_for_category(cat_b))
    else:
        window = _window_for_category(cat_a)

    # 2. Time window
    ts_a = _parse_ts(a.get("timestamp", ""))
    ts_b = _parse_ts(b.get("timestamp", ""))
    if abs((ts_a - ts_b).total_seconds()) > window * 60:
        return False

    # 3. Shared blast surface (only needed for same-category; cross-category already checked above)
    if same_category:
        if _alert_resources(a) & _alert_resources(b):
            return True
        if _shared_correlation_tag(a, b):
            return True
        return False

    return True  # Cross-category with shared resource already passed


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
          "category":             "security",
          "created_at":           "2024-..." (earliest member ts),
          "member_alert_ids":     [...],
          "resources_affected":   [...],
          "shared_tags":          {Service: "auth", ...},
          "title":                "<derived from highest-severity alert>",
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
    # gets hot, bucket by (category, resource_id) first then only compare
    # within buckets.
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
        earliest = min(
            (_parse_ts(m.get("timestamp", "")) for m in members),
            default=datetime.utcnow(),
        )

        all_resources: Set[str] = set()
        for m in members:
            all_resources |= _alert_resources(m)
        sorted_resources = sorted(all_resources)

        category = _alert_category(members[0])  # all members share this

        # Tags shared by ALL members of the cluster — surface for explainability.
        shared: Dict[str, str] = {}
        if members:
            first_tags = _alert_tags(members[0])
            for k, v in first_tags.items():
                if k in CORRELATION_TAGS and all(_alert_tags(m).get(k) == v for m in members):
                    shared[k] = v

        sources = {m.get("source") for m in members if m.get("source")}

        # Title: prefer the highest-severity alert's title.
        leading = max(
            members,
            key=lambda m: SEVERITY_RANK.get((m.get("severity") or "low").lower(), 0),
        )

        incidents.append({
            "incident_id": _stable_incident_id(category, sorted_resources, earliest),
            "status": "open",
            "severity": _max_severity(members),
            "category": category,
            "created_at": earliest.isoformat() + "Z",
            "member_alert_ids": member_ids,
            "resources_affected": sorted_resources,
            "shared_tags": shared,
            "title": leading.get("title") or "Untitled incident",
            "source_count": len(sources),
        })

    # Newest first — UI usually wants this order.
    incidents.sort(key=lambda i: i["created_at"], reverse=True)
    return incidents
