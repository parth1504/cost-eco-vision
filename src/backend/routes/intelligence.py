from fastapi import APIRouter
from typing import Dict, Any

from services.codebase_index import get_codebase_index
from services.pr_intelligence import analyze_pr, analyze_local_diff

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


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
