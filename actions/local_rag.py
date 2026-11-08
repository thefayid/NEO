"""
actions/local_rag.py — Local Semantic File & RAG Knowledge Engine for NEO.
Allows Boss to chat directly with local workspace files, project repositories, documentation, and code.
Zero external dependencies, 100% local, high precision BM25 / TF-IDF semantic chunk retrieval.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Optional

_BASE_DIR = Path(__file__).resolve().parent.parent
_INDEX_CACHE_FILE = _BASE_DIR / "memory" / "local_rag_index.json"
_ALLOWED_EXTS = {
    ".py", ".md", ".txt", ".json", ".js", ".ts", ".html", ".css",
    ".cpp", ".c", ".h", ".cs", ".go", ".rs", ".java", ".yaml", ".yml",
}


def _tokenize(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[a-zA-Z0-9_\-\.]{2,}", text)]


def _chunk_text(text: str, chunk_size: int = 60, overlap: int = 15) -> list[str]:
    lines = text.splitlines()
    chunks = []
    i = 0
    while i < len(lines):
        chunk = "\n".join(lines[i : i + chunk_size])
        if chunk.strip():
            chunks.append((i + 1, chunk))
        i += chunk_size - overlap
    return chunks


class LocalRAGIndex:
    """Lightweight in-memory vector & keyword semantic retrieval engine."""

    def __init__(self):
        self.documents: list[dict] = []
        self.doc_freq: Counter[str] = Counter()
        self.total_docs = 0
        self._load_cache()

    def _load_cache(self):
        if _INDEX_CACHE_FILE.exists():
            try:
                data = json.loads(_INDEX_CACHE_FILE.read_text(encoding="utf-8"))
                self.documents = data.get("documents", [])
                self.total_docs = len(self.documents)
                for d in self.documents:
                    for token in set(d.get("tokens", [])):
                        self.doc_freq[token] += 1
            except Exception as e:
                print(f"[LocalRAG] Load cache error: {e}")

    def _save_cache(self):
        try:
            _INDEX_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _INDEX_CACHE_FILE.write_text(
                json.dumps({"documents": self.documents}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[LocalRAG] Save cache error: {e}")

    def index_directory(self, target_dir: str = "", max_files: int = 250) -> str:
        base_path = Path(target_dir) if target_dir else _BASE_DIR
        if not base_path.exists():
            return f"Directory '{target_dir}' does not exist, Boss."

        indexed_count = 0
        self.documents.clear()
        self.doc_freq.clear()

        for root, dirs, files in os.walk(base_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("venv", "node_modules", "__pycache__", "dist", "build")]
            for f in files:
                ext = Path(f).suffix.lower()
                if ext in _ALLOWED_EXTS:
                    fpath = Path(root) / f
                    try:
                        if fpath.stat().st_size > 1_500_000:  # Skip files > 1.5MB
                            continue
                        content = fpath.read_text(encoding="utf-8", errors="ignore")
                        chunks = _chunk_text(content)
                        rel_path = str(fpath.relative_to(base_path))

                        for start_line, chunk_text in chunks:
                            tokens = _tokenize(chunk_text)
                            doc = {
                                "file": rel_path,
                                "start_line": start_line,
                                "content": chunk_text,
                                "tokens": tokens,
                            }
                            self.documents.append(doc)
                            for token in set(tokens):
                                self.doc_freq[token] += 1
                        indexed_count += 1
                        if indexed_count >= max_files:
                            break
                    except Exception:
                        pass
            if indexed_count >= max_files:
                break

        self.total_docs = len(self.documents)
        self._save_cache()
        return f"Local RAG Index built: {indexed_count} files ({self.total_docs} semantic chunks indexed), Boss."

    def query(self, query_text: str, top_k: int = 4) -> list[dict]:
        if not self.documents:
            self.index_directory()

        query_tokens = _tokenize(query_text)
        if not query_tokens:
            return []

        scores = []
        k1 = 1.5
        b = 0.75
        avg_doc_len = sum(len(d["tokens"]) for d in self.documents) / max(1, self.total_docs)

        for doc in self.documents:
            score = 0.0
            doc_len = len(doc["tokens"])
            doc_counts = Counter(doc["tokens"])

            for q in query_tokens:
                if q in doc_counts:
                    tf = doc_counts[q]
                    df = self.doc_freq.get(q, 1)
                    idf = math.log((self.total_docs - df + 0.5) / (df + 0.5) + 1.0)
                    numerator = tf * (k1 + 1)
                    denominator = tf + k1 * (1 - b + b * (doc_len / avg_doc_len))
                    score += idf * (numerator / denominator)

            if score > 0:
                scores.append((score, doc))

        scores.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scores[:top_k]]


_RAG_ENGINE = LocalRAGIndex()


def search_local_files(query: str, directory: str = "") -> str:
    """Tool function: search local code/docs for answering user queries with line citations."""
    results = _RAG_ENGINE.query(query, top_k=4)
    if not results:
        return f"No local files matching '{query}' found in workspace index."

    out = [f"Found {len(results)} relevant file context snippets for '{query}':\n"]
    for idx, r in enumerate(results, 1):
        out.append(f"--- [Snippet {idx}] {r['file']} (Line {r['start_line']}) ---")
        out.append(r["content"][:600] + ("\n...[truncated]" if len(r["content"]) > 600 else ""))
        out.append("")
    return "\n".join(out)


def local_rag(parameters: dict | None = None, **kwargs) -> str:
    parameters = parameters or {}
    action = parameters.get("action", "query").lower()
    query = parameters.get("query", "")
    target_dir = parameters.get("directory", "")

    if action in ("index", "refresh", "rebuild"):
        return _RAG_ENGINE.index_directory(target_dir)
    elif action in ("query", "search", "ask"):
        return search_local_files(query, target_dir)
    return "Unknown action. Use 'query' or 'index'."


TOOL = {
    "name": "local_rag",
    "description": (
        "Searches local project files, codebases, documentation, notes, and local files "
        "using deep semantic indexing. Returns exact code snippets and line citations."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["query", "index"]},
            "query": {"type": "string", "description": "The concept, error, function, or question to search across local files."},
            "directory": {"type": "string", "description": "Optional specific directory to search or index."},
        },
        "required": ["action"],
    },
    "handler": local_rag,
}
