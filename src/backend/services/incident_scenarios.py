"""
Banking / Financial microservice incident scenarios.

Two realistic cascading failures, each with exactly 5 services:
  - 1-2 healthy services (isolated from the failure path)
  - 3 failing/degraded services in a clear upstream->downstream chain
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List

from services.incident_store import upsert_alert, upsert_incident, set_alert_incident


def _ts(base: datetime, offset_seconds: int) -> str:
    return (base + timedelta(seconds=offset_seconds)).isoformat() + "Z"


SCENARIOS: List[Dict[str, Any]] = [

    # Scenario 1: Payment DB Outage
    # Payment-DB -> Transaction-Service -> Payment-Gateway + Notification-Service
    # Auth-Service stays healthy
    {
        "id": "banking-payment-db-outage",
        "title": "Payment DB Connection Exhaustion causing Transaction Processing Failure",
        "severity": "critical",
        "services": {
            "Payment-DB": {
                "type": "database",
                "depends_on": [],
                "is_root_cause": True,
            },
            "Transaction-Service": {
                "type": "service",
                "depends_on": ["Payment-DB"],
            },
            "Payment-Gateway": {
                "type": "external",
                "depends_on": ["Transaction-Service"],
            },
            "Notification-Service": {
                "type": "service",
                "depends_on": ["Transaction-Service"],
            },
            "Auth-Service": {
                "type": "service",
                "depends_on": [],
            },
        },
        "alerts": [
            {
                "service": "Payment-DB",
                "severity": "Critical",
                "offset": 0,
                "message": (
                    "Connection pool exhausted: 500/500 active connections, 248 queued. "
                    "RDS write IOPS at ceiling (3000/3000). "
                    "Deadlock rate 38/min on payment_transactions table."
                ),
            },
            {
                "service": "Payment-DB",
                "severity": "Critical",
                "offset": 18,
                "message": (
                    "Replication lag 47s on read replica (threshold: 5s). "
                    "Primary still accepting but dropping writes silently. "
                    "WAL archive queue 12 GB behind."
                ),
            },
            {
                "service": "Transaction-Service",
                "severity": "Critical",
                "offset": 30,
                "message": (
                    "Payment transaction timeout after 30s. "
                    "847 transactions in PENDING state with no DB acknowledgement. "
                    "Rollback queue depth: 1,204. Circuit breaker HALF-OPEN."
                ),
            },
            {
                "service": "Transaction-Service",
                "severity": "High",
                "offset": 52,
                "message": (
                    "Retry storm: 3,200 retries/min to Payment-DB. "
                    "Thread pool saturation 48/50. p99 latency 28,400ms (SLA: 500ms). "
                    "Partial debit risk on 312 accounts."
                ),
            },
            {
                "service": "Payment-Gateway",
                "severity": "Critical",
                "offset": 70,
                "message": (
                    "VISA/Mastercard settlement batch failed - 0 authorizations in 5 min. "
                    "Authorization failure rate: 94%. Chargeback accumulation: 12/min. "
                    "PCI compliance settlement window at risk."
                ),
            },
            {
                "service": "Notification-Service",
                "severity": "High",
                "offset": 85,
                "message": (
                    "Transaction confirmation SMS/email delivery stalled. "
                    "2,341 notifications queued (threshold: 100). "
                    "Webhook timeout to 14 partner banking systems. SLA breach in 8 min."
                ),
            },
        ],
    },

    # Scenario 2: Fraud Detection Timeout
    # Fraud-Detection -> Payment-Processor -> Mobile-API
    # Account-DB and Auth-Service stay healthy
    {
        "id": "banking-fraud-detection-timeout",
        "title": "Fraud Detection Model Timeout causing Payment Authorization Block",
        "severity": "critical",
        "services": {
            "Fraud-Detection": {
                "type": "service",
                "depends_on": [],
                "is_root_cause": True,
            },
            "Payment-Processor": {
                "type": "service",
                "depends_on": ["Fraud-Detection"],
            },
            "Mobile-API": {
                "type": "external",
                "depends_on": ["Payment-Processor"],
            },
            "Account-DB": {
                "type": "database",
                "depends_on": [],
            },
            "Auth-Service": {
                "type": "service",
                "depends_on": [],
            },
        },
        "alerts": [
            {
                "service": "Fraud-Detection",
                "severity": "Critical",
                "offset": 0,
                "message": (
                    "ML fraud scoring model OOM: GPU memory exhausted (16/16 GB). "
                    "Inference p99=45s (SLA: 2s). Scoring queue: 12,000 transactions. "
                    "Model reload failed - checkpoint corrupt after last hot-deploy."
                ),
            },
            {
                "service": "Fraud-Detection",
                "severity": "High",
                "offset": 22,
                "message": (
                    "Fallback rule-engine activated but scoring only 120 tx/s (normal: 4,000). "
                    "High-value transactions >$5,000 auto-declined per policy FR-117."
                ),
            },
            {
                "service": "Payment-Processor",
                "severity": "Critical",
                "offset": 35,
                "message": (
                    "Fraud check blocking all payments: 0 transactions approved in 3 min. "
                    "Worker thread pool full (200/200). "
                    "Circuit breaker OPEN after 500 consecutive Fraud-Detection timeouts."
                ),
            },
            {
                "service": "Payment-Processor",
                "severity": "High",
                "offset": 58,
                "message": (
                    "ACH and wire transfer queue paused (compliance requirement). "
                    "Card-not-present transactions suspended. "
                    "Estimated revenue impact: $42,000/min."
                ),
            },
            {
                "service": "Mobile-API",
                "severity": "Critical",
                "offset": 75,
                "message": (
                    "Mobile checkout returning HTTP 503 to 78% of users. "
                    "App crash reports: 1,240 in last 5 min. "
                    "In-app error: 'Payment service temporarily unavailable'."
                ),
            },
        ],
    },
]


def seed_scenario(scenario_id: str = None) -> Dict[str, Any]:
    """Seed one or all banking incident scenarios. Idempotent on incident ID."""
    results = []
    scenarios = (
        SCENARIOS if not scenario_id
        else [s for s in SCENARIOS if s["id"] == scenario_id]
    )

    for scenario in scenarios:
        base_time = datetime.utcnow() - timedelta(minutes=8)
        incident_id = f"INC-BANK-{scenario['id']}"

        alert_ids = []
        for i, alert_def in enumerate(scenario["alerts"]):
            alert_id = f"alert-{scenario['id']}-{i:03d}"
            alert = {
                "alert_id": alert_id,
                "id": alert_id,
                "title": alert_def["message"][:80],
                "message": alert_def["message"],
                "severity": alert_def["severity"],
                "source": alert_def["service"],
                "resource_type": "BankingService",
                "timestamp": _ts(base_time, alert_def["offset"]),
                "category": "reliability",
                "affected_resources": [alert_def["service"]],
                "incident_id": incident_id,
                "region": "us-east-1",
            }
            upsert_alert(alert)
            set_alert_incident(alert_id, incident_id)
            alert_ids.append(alert_id)

        services_meta = {
            svc_name: {
                "type": svc_def["type"],
                "depends_on": svc_def["depends_on"],
                "is_root_cause": svc_def.get("is_root_cause", False),
            }
            for svc_name, svc_def in scenario["services"].items()
        }

        incident = {
            "incident_id": incident_id,
            "title": scenario["title"],
            "severity": scenario["severity"],
            "status": "open",
            "category": "reliability",
            "created_at": _ts(base_time, 0),
            "member_alert_ids": alert_ids,
            "resources_affected": list(scenario["services"].keys()),
            "source_count": len({a["service"] for a in scenario["alerts"]}),
            "shared_tags": {},
            "service_topology": services_meta,
        }
        upsert_incident(incident)
        results.append(incident)

    return {"status": "ok", "incidents_created": len(results), "incidents": results}


def get_all_scenario_ids() -> List[str]:
    return [s["id"] for s in SCENARIOS]
