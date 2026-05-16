from fastapi import APIRouter
from typing import Dict, Any

from services.log_analyser import analyse_logs, list_log_groups

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/groups")
def get_log_groups():
    """List available CloudWatch log groups."""
    return list_log_groups()


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
