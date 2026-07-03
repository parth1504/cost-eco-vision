import logging
import os
import sys

from dotenv import load_dotenv
from fastapi import APIRouter
from typing import Dict, Any, List

from github import Github

from services.codebase_index import get_codebase_index
from services.pr_intelligence import analyze_pr, analyze_local_diff

load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intelligence", tags=["intelligence"])

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
_raw_repo = os.getenv("GITHUB_REPO", "")
if "github.com/" in _raw_repo:
    GITHUB_REPO = "/".join(_raw_repo.rstrip("/").split("github.com/")[1].split("/")[:2])
else:
    GITHUB_REPO = _raw_repo
DEMO_REPO = os.getenv("DEMO_GITHUB_REPO", "https://github.com/parth1504/application_demo")
logger.info(f"GitHub config: repo={GITHUB_REPO!r}, token_set={bool(GITHUB_TOKEN)}")


@router.post("/index")
def index_repo():
    """Index (or re-index) the repository into ChromaDB."""
    index = get_codebase_index()
    result = index.index_repository()
    return result


@router.get("/index/stats")
def index_stats():
    """Get current index statistics."""
    index = get_codebase_index()
    return index.get_stats()


@router.get("/pr/open")
def list_open_prs():
    """Fetch all open PRs from the configured GitHub repo."""
    logger.info(f"list_open_prs called: GITHUB_REPO={GITHUB_REPO!r}")
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return {"status": "error", "error": "GITHUB_TOKEN or GITHUB_REPO not configured", "prs": []}
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(GITHUB_REPO)
        prs = repo.get_pulls(state="open", sort="updated", direction="desc")
        result = []
        for pr in prs[:20]:
            result.append({
                "number": pr.number,
                "title": pr.title,
                "author": pr.user.login,
                "branch": pr.head.ref,
                "base": pr.base.ref,
                "updated_at": pr.updated_at.isoformat() if pr.updated_at else "",
                "additions": pr.additions,
                "deletions": pr.deletions,
                "files_changed": pr.changed_files,
                "labels": [l.name for l in pr.labels],
                "draft": pr.draft,
            })
        return {"status": "ok", "prs": result, "repo": GITHUB_REPO}
    except Exception as e:
        logger.error(f"Failed to fetch open PRs from {GITHUB_REPO!r}: {e}")
        print(f"Failed to fetch open PRs: {e}")
        return {"status": "error", "error": str(e), "prs": [], "repo_used": GITHUB_REPO}


@router.post("/pr/analyze")
def analyze_pull_request(payload: Dict[str, Any]):
    """Analyze a PR by number."""
    pr_number = payload.get("pr_number")
    if not pr_number:
        return {"status": "error", "error": "pr_number is required"}
    return analyze_pr(int(pr_number))


@router.post("/pr/analyze-diff")
def analyze_diff(payload: Dict[str, Any]):
    """Analyze a raw diff (local changes without a PR)."""
    diff_text = payload.get("diff", "")
    if not diff_text:
        return {"status": "error", "error": "diff text is required"}
    return analyze_local_diff(diff_text)


@router.post("/search")
def search_codebase(payload: Dict[str, Any]):
    """Semantic search across the indexed codebase."""
    query = payload.get("query", "")
    n = payload.get("n_results", 10)
    if not query:
        return {"status": "error", "error": "query is required"}
    index = get_codebase_index()
    return index.search(query, n_results=n)


@router.get("/dependencies/{file_path:path}")
def get_file_dependencies(file_path: str):
    """Get dependencies and dependents for a file."""
    index = get_codebase_index()
    return {
        "file": file_path,
        "dependencies": index.get_dependencies(file_path),
        "dependents": index.get_dependents(file_path),
    }


@router.post("/pr/simulate")
def simulate_pr_analysis():
    """Run PR analysis on a simulated diff from the demo application."""
    demo_script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "application_demo", "scripts", "simulate_pr.py"
    )

    try:
        sys.path.insert(0, os.path.dirname(demo_script))
        from simulate_pr import generate_pr_diff
        pr_data = generate_pr_diff()
        return analyze_local_diff(pr_data["diff"])
    except Exception as e:
        return {"status": "error", "error": f"Simulation failed: {str(e)}"}


@router.get("/demo/config")
def demo_config():
    """Return demo application configuration for the UI."""
    return {
        "github_repo": DEMO_REPO,
        "log_group": "/app/order-processing-api",
        "app_name": "order-processing-api",
        "features": {
            "pr_intelligence": True,
            "log_intelligence": True,
            "codebase_search": True,
        },
    }
