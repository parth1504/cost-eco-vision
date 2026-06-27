"""
PR Intelligence Service — deep analysis of pull requests.

Goes beyond line diffs to understand:
- Functional impact of changes
- System-wide implications
- Infrastructure risk (latency, scaling, retries, stability)
- Dependency cascade analysis
- Production readiness assessment

Uses the codebase index for global context and LLM for reasoning.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from github import Github

from agent.llm.llm_client import get_llm_client
from services.codebase_index import get_codebase_index

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
_raw_repo = os.getenv("GITHUB_REPO", "")
if "github.com/" in _raw_repo:
    REPO_NAME = "/".join(_raw_repo.rstrip("/").split("github.com/")[1].split("/")[:2])
else:
    REPO_NAME = _raw_repo


def analyze_pr(pr_number: int) -> Dict[str, Any]:
    """
    Full PR intelligence analysis.
    Returns structured multi-layer output for the UI.
    """
    pr_data = _fetch_pr_data(pr_number)
    if not pr_data:
        return {"status": "error", "error": f"Could not fetch PR #{pr_number}"}

    index = get_codebase_index()
    if index.get_stats()["indexed_files"] == 0:
        index.index_repository()

    # Step 1: Understand what changed
    change_summary = _analyze_changes(pr_data, index)

    # Step 2: Map impact across the system
    impact_analysis = _analyze_impact(pr_data, change_summary, index)

    # Step 3: Infrastructure risk assessment
    infra_risk = _assess_infra_risk(pr_data, change_summary, impact_analysis)

    # Step 4: LLM-powered deep reasoning
    reasoning = _generate_reasoning(pr_data, change_summary, impact_analysis, infra_risk)

    return {
        "status": "complete",
        "pr": {
            "number": pr_number,
            "title": pr_data.get("title", ""),
            "author": pr_data.get("author", ""),
            "branch": pr_data.get("branch", ""),
            "files_changed": len(pr_data.get("files", [])),
            "additions": pr_data.get("additions", 0),
            "deletions": pr_data.get("deletions", 0),
        },
        "change_summary": change_summary,
        "impact_analysis": impact_analysis,
        "infra_risk": infra_risk,
        "reasoning": reasoning,
    }


def analyze_local_diff(diff_text: str) -> Dict[str, Any]:
    """Analyze a local git diff (for when no PR exists)."""
    index = get_codebase_index()
    if index.get_stats()["indexed_files"] == 0:
        index.index_repository()

    files_in_diff = _parse_diff_files(diff_text)

    pr_data = {
        "title": "Local Changes",
        "author": "local",
        "branch": "current",
        "files": files_in_diff,
        "additions": diff_text.count("\n+") - diff_text.count("\n+++"),
        "deletions": diff_text.count("\n-") - diff_text.count("\n---"),
        "diff": diff_text,
    }

    change_summary = _analyze_changes(pr_data, index)
    impact_analysis = _analyze_impact(pr_data, change_summary, index)
    infra_risk = _assess_infra_risk(pr_data, change_summary, impact_analysis)
    reasoning = _generate_reasoning(pr_data, change_summary, impact_analysis, infra_risk)

    return {
        "status": "complete",
        "pr": {
            "number": 0,
            "title": "Local Changes",
            "author": "local",
            "branch": "current",
            "files_changed": len(files_in_diff),
            "additions": pr_data["additions"],
            "deletions": pr_data["deletions"],
        },
        "change_summary": change_summary,
        "impact_analysis": impact_analysis,
        "infra_risk": infra_risk,
        "reasoning": reasoning,
    }


def _fetch_pr_data(pr_number: int) -> Optional[Dict[str, Any]]:
    """Fetch PR data from GitHub."""
    if not GITHUB_TOKEN or not REPO_NAME:
        logger.warning("GITHUB_TOKEN or GITHUB_REPO not set")
        return None
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        pr = repo.get_pull(pr_number)

        files = []
        for f in pr.get_files():
            files.append({
                "filename": f.filename,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "patch": f.patch or "",
            })

        return {
            "title": pr.title,
            "body": pr.body or "",
            "author": pr.user.login,
            "branch": pr.head.ref,
            "base_branch": pr.base.ref,
            "files": files,
            "additions": pr.additions,
            "deletions": pr.deletions,
            "diff": "\n".join(f.get("patch", "") for f in files),
        }
    except Exception as e:
        logger.error(f"Failed to fetch PR #{pr_number}: {e}")
        return None


def _parse_diff_files(diff_text: str) -> List[Dict[str, str]]:
    """Extract file info from a raw diff."""
    import re
    files = []
    for match in re.finditer(r'diff --git a/(.*?) b/(.*?)\n', diff_text):
        files.append({
            "filename": match.group(2),
            "status": "modified",
            "additions": 0,
            "deletions": 0,
            "patch": "",
        })
    return files


def _analyze_changes(pr_data: Dict, index) -> Dict[str, Any]:
    """Understand what changed at a functional level."""
    files = pr_data.get("files", [])
    categories = {
        "backend_logic": [],
        "frontend_ui": [],
        "infrastructure": [],
        "configuration": [],
        "tests": [],
    }

    functions_modified = []
    services_touched = set()

    for f in files:
        fname = f["filename"]
        patch = f.get("patch", "")

        if fname.endswith((".py",)):
            if "test" in fname.lower():
                categories["tests"].append(fname)
            else:
                categories["backend_logic"].append(fname)
                # Extract function names from diff
                import re
                for match in re.finditer(r'def (\w+)\(', patch):
                    functions_modified.append({"file": fname, "function": match.group(1)})
                # Identify service
                parts = fname.split("/")
                if "services" in parts:
                    idx = parts.index("services")
                    if idx + 1 < len(parts):
                        services_touched.add(parts[idx + 1].replace(".py", ""))
                elif "routes" in parts:
                    idx = parts.index("routes")
                    if idx + 1 < len(parts):
                        services_touched.add(parts[idx + 1].replace(".py", ""))

        elif fname.endswith((".tsx", ".ts", ".jsx", ".js")):
            categories["frontend_ui"].append(fname)
        elif fname.endswith((".tf", ".yaml", ".yml", "Dockerfile")):
            categories["infrastructure"].append(fname)
        elif fname.endswith((".json", ".env", ".toml")):
            categories["configuration"].append(fname)

    return {
        "categories": {k: v for k, v in categories.items() if v},
        "functions_modified": functions_modified[:20],
        "services_touched": list(services_touched),
        "total_files": len(files),
        "change_type": _classify_change_type(categories),
    }


def _classify_change_type(categories: Dict) -> str:
    """Classify the overall nature of the PR."""
    if categories.get("infrastructure"):
        return "infrastructure"
    elif categories.get("backend_logic") and categories.get("frontend_ui"):
        return "full_stack"
    elif categories.get("backend_logic"):
        return "backend"
    elif categories.get("frontend_ui"):
        return "frontend"
    elif categories.get("tests"):
        return "testing"
    else:
        return "configuration"


def _analyze_impact(pr_data: Dict, change_summary: Dict, index) -> Dict[str, Any]:
    """Map system-wide impact of the changes."""
    affected_files = set()
    dependency_chains = []

    for f in pr_data.get("files", []):
        fname = f["filename"]
        dependents = index.get_dependents(fname)
        if dependents:
            dependency_chains.append({
                "changed_file": fname,
                "affected_by": dependents[:10],
                "cascade_depth": len(dependents),
            })
            affected_files.update(dependents)

    # Search for related code using semantic search
    related_code = []
    for service in change_summary.get("services_touched", [])[:3]:
        hits = index.search(f"{service} usage integration", n_results=5)
        for hit in hits:
            if hit["file"] not in [f["filename"] for f in pr_data.get("files", [])]:
                related_code.append(hit)

    # Compute blast radius
    total_affected = len(affected_files) + len(related_code)
    blast_radius = "low" if total_affected < 5 else "medium" if total_affected < 15 else "high"

    return {
        "blast_radius": blast_radius,
        "affected_files_count": len(affected_files),
        "dependency_chains": dependency_chains[:10],
        "related_code": related_code[:10],
        "potentially_affected_services": list(set(
            chain["changed_file"].split("/")[1] if "/" in chain["changed_file"] else chain["changed_file"]
            for chain in dependency_chains
        ))[:10],
    }


def _assess_infra_risk(
    pr_data: Dict,
    change_summary: Dict,
    impact_analysis: Dict,
) -> Dict[str, Any]:
    """Assess infrastructure risk of the changes."""
    risk_signals = []
    overall_risk = "low"

    diff_text = pr_data.get("diff", "")
    files = [f["filename"] for f in pr_data.get("files", [])]

    # Check for database-related changes
    db_keywords = ["dynamodb", "table", "query", "scan", "put_item", "get_item", "rds", "sql"]
    if any(kw in diff_text.lower() for kw in db_keywords):
        risk_signals.append({
            "category": "database",
            "signal": "Database operation changes detected",
            "risk": "medium",
            "detail": "Changes to database calls may affect latency and throughput",
        })
        overall_risk = "medium"

    # Check for scaling/concurrency patterns
    scaling_keywords = ["async", "await", "threading", "concurrent", "batch", "queue", "lambda", "timeout"]
    if any(kw in diff_text.lower() for kw in scaling_keywords):
        risk_signals.append({
            "category": "concurrency",
            "signal": "Concurrency/async pattern changes",
            "risk": "medium",
            "detail": "May affect scaling behavior and error handling under load",
        })

    # Check for API/network changes
    network_keywords = ["requests", "http", "fetch", "api", "endpoint", "retry", "timeout"]
    if any(kw in diff_text.lower() for kw in network_keywords):
        risk_signals.append({
            "category": "network",
            "signal": "Network/API interaction changes",
            "risk": "medium",
            "detail": "Could introduce latency or retry amplification",
        })

    # Check for error handling changes
    if "except" in diff_text or "catch" in diff_text or "try" in diff_text:
        risk_signals.append({
            "category": "error_handling",
            "signal": "Error handling modifications",
            "risk": "low",
            "detail": "Changed error boundaries — verify failure modes",
        })

    # Check for config/env changes
    if any(f.endswith((".env", ".yaml", ".yml", ".json")) for f in files):
        risk_signals.append({
            "category": "configuration",
            "signal": "Configuration file changes",
            "risk": "medium",
            "detail": "Config changes can cause silent failures in production",
        })

    # Blast radius amplifies risk
    if impact_analysis.get("blast_radius") == "high":
        overall_risk = "high"
    elif impact_analysis.get("blast_radius") == "medium" and overall_risk != "high":
        overall_risk = "medium"

    # High-risk patterns
    danger_patterns = ["delete", "drop", "truncate", "force", "reset", "destroy"]
    if any(p in diff_text.lower() for p in danger_patterns):
        risk_signals.append({
            "category": "destructive",
            "signal": "Potentially destructive operations detected",
            "risk": "high",
            "detail": "Review carefully for unintended data loss or state corruption",
        })
        overall_risk = "high"

    return {
        "overall_risk": overall_risk,
        "risk_signals": risk_signals,
        "production_readiness": _assess_production_readiness(pr_data, risk_signals),
    }


def _assess_production_readiness(pr_data: Dict, risk_signals: List) -> Dict[str, Any]:
    """Check production readiness checklist."""
    checks = []
    files = [f["filename"] for f in pr_data.get("files", [])]

    has_tests = any("test" in f.lower() for f in files)
    checks.append({"check": "Test coverage", "passed": has_tests, "detail": "Test files included in PR" if has_tests else "No test changes found"})

    has_error_handling = "try" in pr_data.get("diff", "") or "except" in pr_data.get("diff", "")
    checks.append({"check": "Error handling", "passed": has_error_handling, "detail": "Error boundaries present" if has_error_handling else "No error handling in changes"})

    high_risks = [s for s in risk_signals if s["risk"] == "high"]
    checks.append({"check": "No high-risk patterns", "passed": len(high_risks) == 0, "detail": f"{len(high_risks)} high-risk signal(s) detected" if high_risks else "No high-risk patterns found"})

    return {
        "checks": checks,
        "score": sum(1 for c in checks if c["passed"]) / len(checks) * 100 if checks else 100,
    }


def _generate_reasoning(
    pr_data: Dict,
    change_summary: Dict,
    impact_analysis: Dict,
    infra_risk: Dict,
) -> Dict[str, Any]:
    """LLM-powered reasoning about the PR."""
    try:
        llm = get_llm_client()

        files_summary = ", ".join(f["filename"] for f in pr_data.get("files", [])[:10])
        services = ", ".join(change_summary.get("services_touched", []))
        risk_text = "\n".join(f"- [{s['risk']}] {s['signal']}: {s['detail']}" for s in infra_risk.get("risk_signals", []))

        prompt = f"""You are a senior staff engineer reviewing a pull request for production safety.

PR: {pr_data.get('title', 'Unknown')}
Files changed: {files_summary}
Change type: {change_summary.get('change_type', 'unknown')}
Services touched: {services or 'none identified'}
Blast radius: {impact_analysis.get('blast_radius', 'unknown')}
Overall risk: {infra_risk.get('overall_risk', 'unknown')}

Risk signals:
{risk_text or 'None'}

Provide your analysis in EXACTLY this format (plain text, one item per line):

SUMMARY: (one sentence — what this PR does at a functional level)
RISK_ASSESSMENT: (one sentence — the primary risk and why)
EDGE_CASES: (2-3 edge cases that could cause issues, separated by semicolons)
RECOMMENDATION: (one sentence — approve/request-changes/needs-discussion and why)
INFRA_IMPACT: (one sentence — how this affects production infrastructure)"""

        result = llm.generate(prompt)
        return _parse_reasoning(result) if result else _fallback_reasoning(change_summary, infra_risk)

    except Exception as e:
        logger.warning(f"LLM reasoning failed: {e}")
        return _fallback_reasoning(change_summary, infra_risk)


def _parse_reasoning(text: str) -> Dict[str, Any]:
    result = {}
    key_map = {
        "SUMMARY": "summary",
        "RISK_ASSESSMENT": "risk_assessment",
        "EDGE_CASES": "edge_cases",
        "RECOMMENDATION": "recommendation",
        "INFRA_IMPACT": "infra_impact",
    }
    for line in text.strip().split("\n"):
        line = line.strip()
        for prefix, key in key_map.items():
            if line.startswith(f"{prefix}:"):
                value = line[len(prefix) + 1:].strip()
                if key == "edge_cases":
                    result[key] = [e.strip() for e in value.split(";") if e.strip()]
                else:
                    result[key] = value
                break
    return result


def _fallback_reasoning(change_summary: Dict, infra_risk: Dict) -> Dict[str, Any]:
    change_type = change_summary.get("change_type", "unknown")
    risk = infra_risk.get("overall_risk", "low")
    return {
        "summary": f"A {change_type} change touching {change_summary.get('total_files', 0)} files",
        "risk_assessment": f"Overall risk is {risk} based on detected patterns",
        "edge_cases": ["Concurrent access under load", "Error propagation across service boundaries"],
        "recommendation": "Review risk signals before merging",
        "infra_impact": "Monitor after deployment for latency or error rate changes",
    }
