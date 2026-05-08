"""
Synthetic test scenarios for services/correlation.py.

Run from src/backend/:
    python -m scripts.test_correlation

Each scenario is a list of alerts + an expected outcome ("should group as one
incident" or "should be N separate incidents"). The script runs correlation
and prints PASS / FAIL plus the actual cluster structure so you can see the
new Tier S rules at work.

Useful for:
  - Validating Tier S behavior (no cross-domain merging, no
    "same type+region" false positives, stable ids on rerun).
  - Future regression checks if you tune TIME_WINDOW_MINUTES or add new
    correlation rules.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from services.correlation import correlate_alerts


def _ts(minutes_offset: int) -> str:
    return (datetime.utcnow() + timedelta(minutes=minutes_offset)).isoformat() + "Z"


def alert(
    aid: str,
    *,
    resource: str,
    rtype: str,
    region: str,
    severity: str,
    category: str,
    minutes: int = 0,
    tags: Dict[str, str] | None = None,
    title: str | None = None,
) -> Dict[str, Any]:
    return {
        "id": aid,
        "title": title or f"{category} alert on {resource}",
        "message": f"{category} issue detected on {resource}",
        "severity": severity,
        "source": category.capitalize(),
        "category": category,
        "affected_resources": [resource],
        "resource_type": rtype,
        "region": region,
        "timestamp": _ts(minutes),
        "tags": tags or {},
    }


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

SCENARIOS: List[Dict[str, Any]] = [
    {
        "name": "Same bucket, multiple security alerts within window",
        "expected_incidents": 1,
        "alerts": [
            alert("s1", resource="bucket-A", rtype="S3", region="us-east-1",
                  severity="Critical", category="security", minutes=0,
                  title="Public access detected"),
            alert("s2", resource="bucket-A", rtype="S3", region="us-east-1",
                  severity="High", category="security", minutes=2,
                  title="ACL allows AllUsers"),
            alert("s3", resource="bucket-A", rtype="S3", region="us-east-1",
                  severity="High", category="security", minutes=5,
                  title="Encryption disabled"),
        ],
    },
    {
        "name": "Same bucket, security + cost — must NOT merge (Tier S #3)",
        "expected_incidents": 2,
        "alerts": [
            alert("sc1", resource="bucket-A", rtype="S3", region="us-east-1",
                  severity="Critical", category="security", minutes=0),
            alert("co1", resource="bucket-A", rtype="S3", region="us-east-1",
                  severity="Medium", category="cost", minutes=1,
                  title="Storage cost spike"),
        ],
    },
    {
        "name": "Different S3 buckets, no shared tag — must NOT merge (Tier S #1)",
        "expected_incidents": 2,
        "alerts": [
            alert("d1", resource="bucket-A", rtype="S3", region="us-east-1",
                  severity="High", category="security", minutes=0),
            alert("d2", resource="bucket-B", rtype="S3", region="us-east-1",
                  severity="High", category="security", minutes=1),
        ],
    },
    {
        "name": "Different resources, shared Service tag — should merge",
        "expected_incidents": 1,
        "alerts": [
            alert("t1", resource="bucket-X", rtype="S3", region="us-east-1",
                  severity="High", category="security", minutes=0,
                  tags={"Service": "auth", "Environment": "prod"}),
            alert("t2", resource="i-xyz", rtype="EC2", region="us-east-1",
                  severity="Medium", category="security", minutes=2,
                  tags={"Service": "auth", "Environment": "prod"}),
            alert("t3", resource="rds-1", rtype="RDS", region="us-east-1",
                  severity="High", category="security", minutes=4,
                  tags={"Service": "auth", "Environment": "prod"}),
        ],
    },
    {
        "name": "Same Service tag but different category — must NOT merge",
        "expected_incidents": 2,
        "alerts": [
            alert("ts1", resource="bucket-X", rtype="S3", region="us-east-1",
                  severity="High", category="security", minutes=0,
                  tags={"Service": "auth"}),
            alert("ts2", resource="i-xyz", rtype="EC2", region="us-east-1",
                  severity="Medium", category="cost", minutes=1,
                  tags={"Service": "auth"}),
        ],
    },
    {
        # Security window is 30 min — 20 min apart still merges.
        "name": "Same bucket, 20min apart, security category — should merge (security window=30)",
        "expected_incidents": 1,
        "alerts": [
            alert("tw1", resource="bucket-Y", rtype="S3", region="us-east-1",
                  severity="High", category="security", minutes=0),
            alert("tw2", resource="bucket-Y", rtype="S3", region="us-east-1",
                  severity="High", category="security", minutes=20),
        ],
    },
    {
        # Performance window is 10 min — 20 min apart should NOT merge.
        "name": "Same instance, 20min apart, performance category — must NOT merge (perf window=10)",
        "expected_incidents": 2,
        "alerts": [
            alert("pw1", resource="i-perf", rtype="EC2", region="us-east-1",
                  severity="High", category="performance", minutes=0),
            alert("pw2", resource="i-perf", rtype="EC2", region="us-east-1",
                  severity="High", category="performance", minutes=20),
        ],
    },
    {
        # Tier S #C: same resources, same category, same day, but 60+ min
        # apart used to collide on incident_id and overwrite in DDB.
        "name": "Same bucket, 60min apart, security — must produce DIFFERENT incident_ids",
        "expected_incidents": 2,
        "expect_distinct_ids": True,
        "alerts": [
            alert("ci1", resource="bucket-collision", rtype="S3", region="us-east-1",
                  severity="High", category="security", minutes=0),
            alert("ci2", resource="bucket-collision", rtype="S3", region="us-east-1",
                  severity="High", category="security", minutes=70),
        ],
    },
    {
        "name": "Mixed: two real clusters + isolated alerts",
        "expected_incidents": 4,
        "alerts": [
            # Cluster 1 — bucket-A security
            alert("m1", resource="bucket-A", rtype="S3", region="us-east-1",
                  severity="Critical", category="security", minutes=0),
            alert("m2", resource="bucket-A", rtype="S3", region="us-east-1",
                  severity="High", category="security", minutes=3),
            # Cluster 2 — auth service via shared tag
            alert("m3", resource="bucket-Z", rtype="S3", region="us-west-2",
                  severity="High", category="security", minutes=2,
                  tags={"Service": "auth"}),
            alert("m4", resource="i-aaa", rtype="EC2", region="us-west-2",
                  severity="Medium", category="security", minutes=5,
                  tags={"Service": "auth"}),
            # Isolated alerts
            alert("m5", resource="rds-orphan", rtype="RDS", region="eu-west-1",
                  severity="Low", category="performance", minutes=1),
            alert("m6", resource="bucket-cost", rtype="S3", region="us-east-1",
                  severity="Medium", category="cost", minutes=4),
        ],
    },
]


# ---------------------------------------------------------------------------
# Stability checks (Tier S #2)
# ---------------------------------------------------------------------------

def stability_checks() -> List[str]:
    """
    Verify that re-running correlation produces the same incident_id, even
    when new alerts on the SAME resources join (Tier S #2 fix).
    """
    notes: List[str] = []

    base = [
        alert("st1", resource="bucket-S", rtype="S3", region="us-east-1",
              severity="Critical", category="security", minutes=0),
        alert("st2", resource="bucket-S", rtype="S3", region="us-east-1",
              severity="High", category="security", minutes=2),
    ]
    incidents_a = correlate_alerts(base)
    incidents_b = correlate_alerts(base)
    if incidents_a[0]["incident_id"] == incidents_b[0]["incident_id"]:
        notes.append("PASS  same input -> same incident_id")
    else:
        notes.append(f"FAIL  same input produced different ids: "
                     f"{incidents_a[0]['incident_id']} vs {incidents_b[0]['incident_id']}")

    # Add a new alert on the SAME resource — id should remain stable.
    extended = base + [
        alert("st3", resource="bucket-S", rtype="S3", region="us-east-1",
              severity="High", category="security", minutes=5),
    ]
    incidents_c = correlate_alerts(extended)
    if incidents_c[0]["incident_id"] == incidents_a[0]["incident_id"]:
        notes.append("PASS  new alert on same resource -> id unchanged")
    else:
        notes.append(f"FAIL  new alert on same resource changed id: "
                     f"{incidents_a[0]['incident_id']} -> {incidents_c[0]['incident_id']}")

    # Add an alert on a NEW resource that shares the cluster (via tag) — id
    # WILL change because resources_affected scope changed. That's intentional
    # — a wider blast radius is arguably a different incident.
    return notes


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run() -> None:
    print("=" * 72)
    print("Correlation scenarios")
    print("=" * 72)

    passed = failed = 0
    for sc in SCENARIOS:
        incidents = correlate_alerts(sc["alerts"])
        ok = len(incidents) == sc["expected_incidents"]
        # Optional check: incidents must have distinct ids (used for the
        # same-day-collision regression case).
        if sc.get("expect_distinct_ids"):
            ids = {inc["incident_id"] for inc in incidents}
            if len(ids) != len(incidents):
                ok = False

        tag = "PASS" if ok else "FAIL"
        print(f"\n[{tag}]  {sc['name']}")
        print(f"  expected {sc['expected_incidents']} incident(s), got {len(incidents)}")
        for inc in incidents:
            print(f"  - {inc['incident_id']}  "
                  f"sev={inc['severity']:<8} cat={inc['category']:<10} "
                  f"members={inc['member_alert_ids']}  "
                  f"resources={inc['resources_affected']}"
                  + (f"  shared_tags={inc['shared_tags']}" if inc['shared_tags'] else ""))
        if ok:
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 72)
    print("Stability checks (Tier S #2)")
    print("=" * 72)
    for note in stability_checks():
        print(f"  {note}")
        if note.startswith("PASS"):
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 72)
    print(f"TOTAL: {passed} passed, {failed} failed")
    print("=" * 72)


if __name__ == "__main__":
    run()
