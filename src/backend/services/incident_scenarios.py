"""
Microservice incident scenario seeder.

Creates realistic multi-service incidents with branching dependency graphs
that demonstrate how failures propagate through distributed systems.

Each scenario defines:
- services: the microservice topology (nodes + their dependencies)
- alerts: timestamped alerts placed on specific services
- root_cause: which service is the actual root cause

These are injected directly into the in-memory incident_store so the
IncidentCoordinator UI can render them immediately.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List
import uuid

from services.incident_store import upsert_alert, upsert_incident, set_alert_incident


def _ts(base: datetime, offset_seconds: int) -> str:
    return (base + timedelta(seconds=offset_seconds)).isoformat() + "Z"


SCENARIOS: List[Dict[str, Any]] = [
    # ── Scenario 1: Payment Gateway Cascade ──────────────────────────────
    # Root: Payment DB connection pool exhausted → Payment Service fails
    # → Order Service can't process → API Gateway returns 5xx
    # → Notification Service can't send confirmations
    # → Dashboard shows stale data
    {
        "id": "cascade-payment-db",
        "title": "Payment DB Connection Pool Exhaustion → Order Processing Failure",
        "severity": "critical",
        "services": {
            "Payment-DB": {
                "type": "database",
                "depends_on": [],
                "is_root_cause": True,
            },
            "Payment-Service": {
                "type": "service",
                "depends_on": ["Payment-DB"],
            },
            "Order-Service": {
                "type": "service",
                "depends_on": ["Payment-Service", "Inventory-Cache"],
            },
            "Inventory-Cache": {
                "type": "database",
                "depends_on": [],
            },
            "API-Gateway": {
                "type": "external",
                "depends_on": ["Order-Service", "Auth-Service"],
            },
            "Auth-Service": {
                "type": "service",
                "depends_on": [],
            },
            "Notification-Service": {
                "type": "service",
                "depends_on": ["Order-Service"],
            },
            "Dashboard-BFF": {
                "type": "service",
                "depends_on": ["Order-Service", "Analytics-Service"],
            },
            "Analytics-Service": {
                "type": "service",
                "depends_on": [],
            },
        },
        "alerts": [
            # T+0: Root cause — DB pool exhaustion
            {"service": "Payment-DB", "severity": "Critical", "offset": 0,
             "message": "Connection pool exhausted: 100/100 active connections, 47 queued requests waiting. ProvisionedThroughputExceededException on table Transactions."},
            {"service": "Payment-DB", "severity": "Critical", "offset": 15,
             "message": "Write latency spike: p99=4200ms (normal: 12ms). DynamoDB consumed WCU=890, provisioned=200."},
            # T+30s: Payment service starts failing
            {"service": "Payment-Service", "severity": "Critical", "offset": 30,
             "message": "Payment processing timeout: 34 requests failed in last 60s. Circuit breaker OPEN for downstream Payment-DB."},
            {"service": "Payment-Service", "severity": "High", "offset": 45,
             "message": "Retry storm detected: 200+ retries/min to Payment-DB. Exponential backoff not configured on legacy path."},
            # T+60s: Order service can't process
            {"service": "Order-Service", "severity": "Critical", "offset": 60,
             "message": "Order creation failing: POST /api/v1/orders returning 500. Payment charge step timing out after 30s."},
            {"service": "Order-Service", "severity": "High", "offset": 75,
             "message": "Order queue depth growing: 342 pending orders. Dead letter queue receiving 12 messages/min."},
            # T+90s: Upstream and sibling effects
            {"service": "API-Gateway", "severity": "High", "offset": 90,
             "message": "5xx error rate at 34.2% (threshold: 5%). Latency p99=8500ms. Auto-scaling triggered but ineffective — bottleneck is downstream."},
            {"service": "Notification-Service", "severity": "Warning", "offset": 100,
             "message": "Order confirmation emails delayed: 280 messages in backlog. Webhook delivery failing for partner integrations."},
            {"service": "Dashboard-BFF", "severity": "Warning", "offset": 110,
             "message": "Dashboard showing stale order data. Cache TTL expired but refresh failing due to Order-Service 503s."},
            # Inventory and Auth stay healthy
            {"service": "Inventory-Cache", "severity": "Medium", "offset": 120,
             "message": "Cache hit rate dropped to 67% (normal: 95%). Inventory reads succeeding but order writes failing downstream."},
        ],
    },

    # ── Scenario 2: Auth Service Token Expiry Cascade ────────────────────
    # Root: Auth Service JWT signing key rotation failed
    # → All services using Auth fail token validation
    # → User-Service, Product-Service, Cart-Service all degrade
    # → CDN starts serving stale content
    {
        "id": "cascade-auth-failure",
        "title": "Auth Service Key Rotation Failure → Platform-Wide Authentication Breakdown",
        "severity": "critical",
        "services": {
            "Auth-Service": {
                "type": "service",
                "depends_on": ["Auth-DB"],
                "is_root_cause": True,
            },
            "Auth-DB": {
                "type": "database",
                "depends_on": [],
            },
            "User-Service": {
                "type": "service",
                "depends_on": ["Auth-Service", "User-DB"],
            },
            "User-DB": {
                "type": "database",
                "depends_on": [],
            },
            "Product-Service": {
                "type": "service",
                "depends_on": ["Auth-Service", "Product-DB"],
            },
            "Product-DB": {
                "type": "database",
                "depends_on": [],
            },
            "Cart-Service": {
                "type": "service",
                "depends_on": ["Auth-Service", "Product-Service"],
            },
            "Checkout-Service": {
                "type": "service",
                "depends_on": ["Cart-Service", "Payment-Gateway"],
            },
            "Payment-Gateway": {
                "type": "external",
                "depends_on": [],
            },
            "CDN-Edge": {
                "type": "infra",
                "depends_on": ["Product-Service", "User-Service"],
            },
            "Mobile-BFF": {
                "type": "service",
                "depends_on": ["User-Service", "Product-Service", "Cart-Service"],
            },
        },
        "alerts": [
            # T+0: Root cause
            {"service": "Auth-Service", "severity": "Critical", "offset": 0,
             "message": "JWT signing key rotation failed: new key rejected by 3/5 replicas. Falling back to expired key — tokens issued in last 15min will fail validation."},
            {"service": "Auth-Service", "severity": "Critical", "offset": 20,
             "message": "Token validation error rate 78%. /auth/verify returning 401 for valid sessions. 12,000 affected users in last 5 minutes."},
            # T+40s: Services that depend on Auth start failing
            {"service": "User-Service", "severity": "High", "offset": 40,
             "message": "Authentication middleware rejecting requests: 401 Unauthorized on 72% of API calls. User profile reads failing."},
            {"service": "Product-Service", "severity": "High", "offset": 45,
             "message": "Authenticated product queries failing. Personalized pricing unavailable — falling back to guest pricing. Revenue impact estimated."},
            {"service": "Cart-Service", "severity": "Critical", "offset": 55,
             "message": "Cart operations failing: cannot verify user identity. 450 active shopping sessions interrupted. Cart persistence at risk."},
            # T+70s: Downstream cascade
            {"service": "Checkout-Service", "severity": "Critical", "offset": 70,
             "message": "Checkout flow blocked: Cart-Service returning 503. 89 in-flight purchases abandoned. Payment Gateway not reached."},
            {"service": "Mobile-BFF", "severity": "High", "offset": 80,
             "message": "Mobile app error rate 62%. All authenticated endpoints returning 401/503. App crash reports spiking from token refresh loops."},
            {"service": "CDN-Edge", "severity": "Warning", "offset": 90,
             "message": "CDN serving stale cached content. Origin (Product-Service, User-Service) returning errors — cache-on-error policy active."},
            # Databases and Payment Gateway are fine
            {"service": "Auth-DB", "severity": "Medium", "offset": 30,
             "message": "Elevated read latency on auth_keys table: p99=85ms (normal: 8ms). Connection count normal. DB itself healthy — issue is application-level."},
        ],
    },
]


def seed_scenario(scenario_id: str = None) -> Dict[str, Any]:
    """
    Seed one or all microservice incident scenarios into the in-memory store.
    Returns the created incident(s).
    """
    results = []
    scenarios = SCENARIOS if not scenario_id else [s for s in SCENARIOS if s["id"] == scenario_id]

    for scenario in scenarios:
        base_time = datetime.utcnow() - timedelta(minutes=10)
        incident_id = f"INC-MICRO-{scenario['id']}"

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
                "resource_type": "Microservice",
                "timestamp": _ts(base_time, alert_def["offset"]),
                "category": "reliability",
                "affected_resources": [alert_def["service"]],
                "incident_id": incident_id,
                "region": "us-east-1",
            }
            upsert_alert(alert)
            set_alert_incident(alert_id, incident_id)
            alert_ids.append(alert_id)

        # Build the service topology metadata
        services_meta = {}
        for svc_name, svc_def in scenario["services"].items():
            services_meta[svc_name] = {
                "type": svc_def["type"],
                "depends_on": svc_def["depends_on"],
                "is_root_cause": svc_def.get("is_root_cause", False),
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
            "source_count": len(set(a["service"] for a in scenario["alerts"])),
            "shared_tags": {},
            "service_topology": services_meta,
        }
        upsert_incident(incident)
        results.append(incident)

    return {"status": "ok", "incidents_created": len(results), "incidents": results}


def get_all_scenario_ids() -> List[str]:
    return [s["id"] for s in SCENARIOS]
