from fastapi import APIRouter
from typing import Dict, Any

from services.log_analyser import analyse_logs, list_log_groups

router = APIRouter(prefix="/logs", tags=["logs"])

DEMO_APP_LOG_GROUP = "/app/order-processing-api"


@router.get("/groups")
def get_log_groups():
    """List available CloudWatch log groups."""
    groups = list_log_groups()
    demo_exists = any(g["name"] == DEMO_APP_LOG_GROUP for g in groups)
    if not demo_exists:
        groups.insert(0, {
            "name": DEMO_APP_LOG_GROUP,
            "stored_bytes": 0,
            "retention_days": 14,
            "creation_time": None,
            "is_demo": True,
        })
    return groups


@router.post("/analyse")
def analyse(payload: Dict[str, Any]):
    """Analyse a log group for errors — diff against last healthy state."""
    log_group = payload.get("log_group")
    if not log_group:
        return {"status": "error", "error": "log_group is required"}

    error_window = payload.get("error_window_minutes", 30)
    lookback = payload.get("lookback_hours", 6)

    return analyse_logs(
        log_group=log_group,
        error_window_minutes=error_window,
        lookback_hours=lookback,
    )


@router.get("/demo/status")
def demo_app_status():
    """Check if the demo application (order-processing-api) is generating logs."""
    return {
        "log_group": DEMO_APP_LOG_GROUP,
        "github_repo": "https://github.com/parth1504/application_demo",
        "description": "Order Processing API — generates realistic CloudWatch log patterns",
        "incident_types": [
            "payment_cascade",
            "db_exhaustion",
            "shipping_outage",
            "load_spike",
        ],
    }
