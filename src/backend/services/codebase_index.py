"""
Codebase Indexing Service — ChromaDB-powered semantic search over the repository.

Indexes:
- File contents (chunked)
- Function/class definitions
- File relationships (imports/dependencies)

Provides:
- Semantic search ("find code related to X")
- Dependency graph lookups
- Change impact analysis (what depends on this file?)
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ChromaDB is optional — falls back to in-memory grep-based search
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("chromadb not installed — falling back to in-memory indexing")


REPO_ROOT = os.getenv("REPO_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
CHROMA_PERSIST_DIR = os.path.join(REPO_ROOT, ".chroma_index")

INDEXABLE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".yaml", ".yml", ".tf", ".json"}
SKIP_DIRS = {"node_modules", ".git", "__pycache__", "dist", "build", ".venv", "venv", ".chroma_index"}
MAX_CHUNK_SIZE = 800
OVERLAP = 100


class CodebaseIndex:
    def __init__(self):
        self._client = None
        self._collection = None
        self._file_map: Dict[str, str] = {}
        self._dependency_graph: Dict[str, List[str]] = {}
        self._initialized = False

    def _init_chroma(self):
        if self._initialized:
            return
        if CHROMA_AVAILABLE:
            try:
                self._client = chromadb.Client(ChromaSettings(
                    anonymized_telemetry=False,
                    is_persistent=True,
                    persist_directory=CHROMA_PERSIST_DIR,
                ))
                self._collection = self._client.get_or_create_collection(
                    name="codebase",
                    metadata={"hnsw:space": "cosine"},
                )
                self._initialized = True
                logger.info(f"ChromaDB initialized at {CHROMA_PERSIST_DIR}")
            except Exception as e:
                logger.error(f"ChromaDB init failed: {e}")
                self._initialized = True
        else:
            self._initialized = True

    def index_repository(self, root: Optional[str] = None) -> Dict[str, Any]:
        """Walk the repo, chunk files, and index into ChromaDB."""
        self._init_chroma()
        root = root or REPO_ROOT
        indexed = 0
        files_found = 0
        chunks = []

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fname in filenames:
                ext = Path(fname).suffix
                if ext not in INDEXABLE_EXTENSIONS:
                    continue
                filepath = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(filepath, root)
                files_found += 1

                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except Exception:
                    continue

                self._file_map[rel_path] = content
                self._extract_dependencies(rel_path, content)

                file_chunks = self._chunk_file(rel_path, content)
                chunks.extend(file_chunks)
                indexed += 1

        if self._collection and chunks:
            batch_size = 100
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                self._collection.upsert(
                    ids=[c["id"] for c in batch],
                    documents=[c["text"] for c in batch],
                    metadatas=[c["metadata"] for c in batch],
                )

        return {
            "files_found": files_found,
            "files_indexed": indexed,
            "chunks_created": len(chunks),
            "chroma_available": CHROMA_AVAILABLE,
        }

    def search(self, query: str, n_results: int = 10) -> List[Dict[str, Any]]:
        """Semantic search across the codebase."""
        self._init_chroma()
        if self._collection:
            try:
                results = self._collection.query(
                    query_texts=[query],
                    n_results=n_results,
                )
                hits = []
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    hits.append({
                        "file": meta.get("file", ""),
                        "chunk_index": meta.get("chunk_index", 0),
                        "content": doc[:300],
                        "distance": results["distances"][0][i] if results.get("distances") else None,
                    })
                return hits
            except Exception as e:
                logger.warning(f"ChromaDB search failed: {e}")

        return self._fallback_search(query, n_results)

    def get_dependents(self, file_path: str) -> List[str]:
        """Find all files that import/depend on the given file."""
        dependents = []
        target = Path(file_path).stem
        for fp, deps in self._dependency_graph.items():
            if file_path in deps or target in deps:
                dependents.append(fp)
        return dependents

    def get_dependencies(self, file_path: str) -> List[str]:
        """Get what a file depends on."""
        return self._dependency_graph.get(file_path, [])

    def get_file_content(self, file_path: str) -> Optional[str]:
        if file_path in self._file_map:
            return self._file_map[file_path]
        full_path = os.path.join(REPO_ROOT, file_path)
        if os.path.exists(full_path):
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        return None

    def get_stats(self) -> Dict[str, Any]:
        self._init_chroma()
        count = 0
        if self._collection:
            try:
                count = self._collection.count()
            except Exception:
                pass
        return {
            "indexed_files": len(self._file_map),
            "total_chunks": count,
            "dependency_edges": sum(len(v) for v in self._dependency_graph.values()),
            "chroma_available": CHROMA_AVAILABLE,
        }

    def _chunk_file(self, rel_path: str, content: str) -> List[Dict]:
        chunks = []
        lines = content.split("\n")
        current_chunk = []
        current_size = 0
        chunk_idx = 0

        for line in lines:
            current_chunk.append(line)
            current_size += len(line) + 1
            if current_size >= MAX_CHUNK_SIZE:
                text = "\n".join(current_chunk)
                chunk_id = hashlib.md5(f"{rel_path}:{chunk_idx}".encode()).hexdigest()
                chunks.append({
                    "id": chunk_id,
                    "text": text,
                    "metadata": {
                        "file": rel_path,
                        "chunk_index": chunk_idx,
                        "extension": Path(rel_path).suffix,
                    },
                })
                overlap_lines = current_chunk[-3:] if len(current_chunk) > 3 else []
                current_chunk = overlap_lines
                current_size = sum(len(l) + 1 for l in current_chunk)
                chunk_idx += 1

        if current_chunk:
            text = "\n".join(current_chunk)
            chunk_id = hashlib.md5(f"{rel_path}:{chunk_idx}".encode()).hexdigest()
            chunks.append({
                "id": chunk_id,
                "text": text,
                "metadata": {
                    "file": rel_path,
                    "chunk_index": chunk_idx,
                    "extension": Path(rel_path).suffix,
                },
            })

        return chunks

    def _extract_dependencies(self, rel_path: str, content: str):
        deps = []
        import_patterns = [
            r'from\s+([\w.]+)\s+import',
            r'import\s+([\w.]+)',
            r'from\s+["\']([^"\']+)["\']',
            r'import\s+["\']([^"\']+)["\']',
            r'require\(["\']([^"\']+)["\']\)',
        ]
        for pattern in import_patterns:
            for match in re.finditer(pattern, content):
                deps.append(match.group(1))
        self._dependency_graph[rel_path] = deps

    def _fallback_search(self, query: str, n_results: int) -> List[Dict[str, Any]]:
        """Simple keyword search when ChromaDB unavailable."""
        keywords = query.lower().split()
        scored = []
        for fp, content in self._file_map.items():
            lower_content = content.lower()
            score = sum(lower_content.count(kw) for kw in keywords)
            if score > 0:
                scored.append((score, fp, content))
        scored.sort(reverse=True)
        results = []
        for score, fp, content in scored[:n_results]:
            results.append({
                "file": fp,
                "chunk_index": 0,
                "content": content[:300],
                "distance": 1.0 / (score + 1),
            })
        return results


# Singleton
_index_instance: Optional[CodebaseIndex] = None


def get_codebase_index() -> CodebaseIndex:
    global _index_instance
    if _index_instance is None:
        _index_instance = CodebaseIndex()
    return _index_instance
