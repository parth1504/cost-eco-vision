"""
Log Analyser service — CloudWatch log diff analysis.

When a production error is detected, this service:
1. Fetches recent error logs from CloudWatch
2. Finds the last known working state (before errors started)
3. Computes log diffs between working and broken states
4. Optionally checks infra/config changes in the same timeframe
5. Uses LLM to explain what went wrong

Output: side-by-side view data for the frontend.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from connections.aws import get_client
from agent.llm.llm_client import get_llm_client
from services.codebase_index import get_codebase_index

logger = logging.getLogger(__name__)


def analyse_logs(
    log_group: str,
    error_window_minutes: int = 30,
    lookback_hours: int = 6,
) -> Dict[str, Any]:
    """
    Main entry point: analyse a log group for recent errors,
    find the diff against the last healthy state, and explain what broke.
    """
    try:
        logs_client = get_client("logs")

        now = datetime.utcnow()
        error_start = now - timedelta(minutes=error_window_minutes)
        healthy_end = error_start
        healthy_start = healthy_end - timedelta(hours=lookback_hours)

        error_filter = (
            "?ERROR ?Exception ?FATAL ?error ?exception "
            "?\"status=5\" ?\"status=4\" ?timeout ?circuit ?CRITICAL ?WARNING "
            "?failed ?failure ?retry ?exhausted ?refused ?unreachable"
        )

        # Fetch error-window logs
        error_logs = _query_logs(
            logs_client, log_group,
            start_time=error_start, end_time=now,
            filter_pattern=error_filter,
        )

        # Fetch healthy-window logs (same pattern to see if errors existed before)
        healthy_logs = _query_logs(
            logs_client, log_group,
            start_time=healthy_start, end_time=healthy_end,
            filter_pattern=error_filter,
        )

        # Also get recent logs for baseline (show something even if no errors)
        baseline_logs = _query_logs(
            logs_client, log_group,
            start_time=error_start, end_time=now,
            filter_pattern=None,
            limit=100,
        )

        # Compute diff
        diff = _compute_log_diff(healthy_logs, error_logs)

        # Check for infra changes in the timeframe
        infra_changes = _check_infra_changes(error_start, now)

        # Correlate with code changes
        code_correlation = _correlate_with_code(error_logs, diff)

        # LLM analysis
        analysis = _llm_analyse_diff(
            log_group, error_logs, healthy_logs, diff, infra_changes
        )

        return {
            "status": "complete",
            "log_group": log_group,
            "time_range": {
                "error_window": {
                    "start": error_start.isoformat(),
                    "end": now.isoformat(),
                },
                "healthy_window": {
                    "start": healthy_start.isoformat(),
                    "end": healthy_end.isoformat(),
                },
            },
            "error_logs": _format_log_entries(error_logs),
            "healthy_logs": _format_log_entries(healthy_logs),
            "baseline_sample": _format_log_entries(baseline_logs[:20]),
            "diff": diff,
            "infra_changes": infra_changes,
            "code_correlation": code_correlation,
            "analysis": analysis,
        }

    except Exception as e:
        logger.error(f"Log analysis failed for {log_group}: {e}")
        return {
            "status": "error",
            "log_group": log_group,
            "error": str(e),
            "analysis": None,
        }


def list_log_groups() -> List[Dict[str, Any]]:
    """List available CloudWatch log groups."""
    try:
        logs_client = get_client("logs")
        response = logs_client.describe_log_groups(limit=50)
        groups = []
        for g in response.get("logGroups", []):
            groups.append({
                "name": g["logGroupName"],
                "stored_bytes": g.get("storedBytes", 0),
                "retention_days": g.get("retentionInDays"),
                "creation_time": g.get("creationTime"),
            })
        return groups
    except Exception as e:
        logger.error(f"Failed to list log groups: {e}")
        return []


def _query_logs(
    client,
    log_group: str,
    start_time: datetime,
    end_time: datetime,
    filter_pattern: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Query CloudWatch Logs Insights or filter_log_events."""
    try:
        params = {
            "logGroupName": log_group,
            "startTime": int(start_time.timestamp() * 1000),
            "endTime": int(end_time.timestamp() * 1000),
            "limit": limit,
        }
        if filter_pattern:
            params["filterPattern"] = filter_pattern

        response = client.filter_log_events(**params)
        return response.get("events", [])

    except Exception as e:
        logger.warning(f"Log query failed for {log_group}: {e}")
        return []


def _compute_log_diff(
    healthy_logs: List[Dict],
    error_logs: List[Dict],
) -> Dict[str, Any]:
    """Compute meaningful differences between healthy and error log windows."""
    healthy_messages = set()
    for log in healthy_logs:
        msg = log.get("message", "").strip()
        key = _normalize_log_message(msg)
        if key:
            healthy_messages.add(key)

    error_messages = set()
    new_errors = []
    for log in error_logs:
        msg = log.get("message", "").strip()
        key = _normalize_log_message(msg)
        if key:
            error_messages.add(key)
            if key not in healthy_messages:
                new_errors.append(msg)

    disappeared = []
    for key in healthy_messages:
        if key not in error_messages:
            disappeared.append(key)

    return {
        "new_error_patterns": new_errors[:20],
        "disappeared_patterns": disappeared[:10],
        "error_count_before": len(healthy_logs),
        "error_count_after": len(error_logs),
        "count_increase": len(error_logs) - len(healthy_logs),
        "new_pattern_count": len(new_errors),
    }


def _normalize_log_message(msg: str) -> str:
    """Normalize a log message for comparison (strip timestamps, IDs)."""
    import re
    msg = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*Z?', '<TIMESTAMP>', msg)
    msg = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '<UUID>', msg)
    msg = re.sub(r'\b\d{10,13}\b', '<ID>', msg)
    return msg.strip()[:200]


def _check_infra_changes(start: datetime, end: datetime) -> List[Dict[str, str]]:
    """Check CloudTrail for infra changes in the timeframe."""
    changes = []
    try:
        ct_client = get_client("cloudtrail")
        response = ct_client.lookup_events(
            StartTime=start,
            EndTime=end,
            MaxResults=20,
            LookupAttributes=[{
                "AttributeKey": "EventName",
                "AttributeValue": "RunInstances"
            }]
        )
        # Also check for relevant events
        for event in response.get("Events", []):
            changes.append({
                "event": event.get("EventName", ""),
                "time": event.get("EventTime", "").isoformat() if hasattr(event.get("EventTime", ""), "isoformat") else str(event.get("EventTime", "")),
                "source": event.get("EventSource", ""),
                "user": event.get("Username", "unknown"),
            })
    except Exception as e:
        logger.warning(f"CloudTrail lookup failed: {e}")

    # Also check for recent deployments via EC2 events
    try:
        ct_client = get_client("cloudtrail")
        for event_name in ["UpdateService", "UpdateFunctionCode", "ModifyDBInstance", "PutScalingPolicy"]:
            try:
                resp = ct_client.lookup_events(
                    StartTime=start,
                    EndTime=end,
                    MaxResults=5,
                    LookupAttributes=[{
                        "AttributeKey": "EventName",
                        "AttributeValue": event_name
                    }]
                )
                for event in resp.get("Events", []):
                    changes.append({
                        "event": event.get("EventName", ""),
                        "time": str(event.get("EventTime", "")),
                        "source": event.get("EventSource", ""),
                        "user": event.get("Username", "unknown"),
                    })
            except Exception:
                pass
    except Exception:
        pass

    return changes


def _correlate_with_code(error_logs: List[Dict], diff: Dict) -> List[Dict[str, Any]]:
    """Use the codebase index to find code related to error patterns."""
    index = get_codebase_index()
    if index.get_stats()["indexed_files"] == 0:
        index.index_repository()

    correlations = []
    seen_files = set()

    for pattern in diff.get("new_error_patterns", [])[:5]:
        keywords = _extract_keywords_from_error(pattern)
        if not keywords:
            continue
        hits = index.search(keywords, n_results=3)
        for hit in hits:
            if hit["file"] not in seen_files:
                seen_files.add(hit["file"])
                correlations.append({
                    "error_pattern": pattern[:150],
                    "related_file": hit["file"],
                    "code_snippet": hit["content"][:200],
                    "relevance": round(1.0 - (hit.get("distance") or 0.5), 2),
                })

    return correlations[:10]


def _extract_keywords_from_error(error_msg: str) -> str:
    """Extract searchable keywords from an error message."""
    import re
    msg = re.sub(r'[<>\[\]{}()\d]+', ' ', error_msg)
    msg = re.sub(r'(TIMESTAMP|UUID|ID)', '', msg)
    words = [w for w in msg.split() if len(w) > 3 and not w.startswith('/')]
    return " ".join(words[:8])


def _format_log_entries(logs: List[Dict]) -> List[Dict[str, str]]:
    """Format log entries for frontend display."""
    formatted = []
    for log in logs[:50]:
        formatted.append({
            "timestamp": datetime.fromtimestamp(
                log.get("timestamp", 0) / 1000
            ).isoformat() if log.get("timestamp") else "",
            "message": log.get("message", "").strip()[:500],
            "stream": log.get("logStreamName", ""),
        })
    return formatted


def _llm_analyse_diff(
    log_group: str,
    error_logs: List[Dict],
    healthy_logs: List[Dict],
    diff: Dict,
    infra_changes: List[Dict],
) -> Optional[Dict[str, str]]:
    """Use LLM to generate human-readable analysis of the log diff."""
    try:
        llm = get_llm_client()

        error_sample = "\n".join(
            log.get("message", "")[:200] for log in error_logs[:10]
        )
        healthy_sample = "\n".join(
            log.get("message", "")[:200] for log in healthy_logs[:5]
        )
        new_patterns = "\n".join(diff.get("new_error_patterns", [])[:5])
        infra_text = "\n".join(
            f"- {c['event']} by {c['user']} at {c['time']}"
            for c in infra_changes[:5]
        ) if infra_changes else "No infra changes detected in timeframe"

        prompt = f"""You are a production incident analyser. Analyze this CloudWatch log diff and explain what went wrong.

Log Group: {log_group}
Error count before: {diff['error_count_before']}
Error count after: {diff['error_count_after']} (increase of {diff['count_increase']})
New error patterns found: {diff['new_pattern_count']}

Sample error logs (current):
{error_sample[:800]}

Sample healthy logs (before):
{healthy_sample[:400]}

New patterns not seen before:
{new_patterns[:500]}

Infrastructure changes in timeframe:
{infra_text}

Provide your analysis in this JSON-like format (use plain text, no actual JSON):
SUMMARY: (one sentence - what broke)
ROOT_CAUSE: (what likely caused it)
EVIDENCE: (2-3 specific signals from the logs/infra)
RECOMMENDATION: (what to do next)"""

        result = llm.generate(prompt)
        if not result:
            return None

        return _parse_analysis(result)

    except Exception as e:
        logger.warning(f"LLM analysis failed: {e}")
        return {
            "summary": f"Error rate increased by {diff['count_increase']} events with {diff['new_pattern_count']} new patterns",
            "root_cause": "Unable to determine — LLM analysis unavailable",
            "evidence": "New error patterns detected that were not present in the healthy window",
            "recommendation": "Review the new error patterns and recent infrastructure changes",
        }


def _parse_analysis(text: str) -> Dict[str, str]:
    """Parse LLM response into structured fields."""
    result = {
        "summary": "",
        "root_cause": "",
        "evidence": "",
        "recommendation": "",
    }

    current_key = None
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("SUMMARY:"):
            current_key = "summary"
            result[current_key] = line[len("SUMMARY:"):].strip()
        elif line.startswith("ROOT_CAUSE:"):
            current_key = "root_cause"
            result[current_key] = line[len("ROOT_CAUSE:"):].strip()
        elif line.startswith("EVIDENCE:"):
            current_key = "evidence"
            result[current_key] = line[len("EVIDENCE:"):].strip()
        elif line.startswith("RECOMMENDATION:"):
            current_key = "recommendation"
            result[current_key] = line[len("RECOMMENDATION:"):].strip()
        elif current_key and line:
            result[current_key] += " " + line

    return result
