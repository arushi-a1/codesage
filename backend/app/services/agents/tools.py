"""Tools the LangGraph agent can call. Each tool is scoped to a single
repository (identified by its Qdrant collection + local clone path) so the
agent can only ever read within the repo the user is chatting about.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List

from app.services.rag.retriever import RetrievedChunk, retrieve

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": (
                "Semantic search over the indexed codebase. Use this to find "
                "functions, classes, or logic related to a natural-language "
                "description when you don't know the exact file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                    "path_prefix": {
                        "type": "string",
                        "description": "Optional substring to filter results to a directory/file",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the exact contents of a file (optionally a line range) from the repo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and subdirectories under a given path in the repo.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Relative path, '' for repo root"}},
                "required": [],
            },
        },
    },
]


class RepoToolContext:
    """Bundles what the tools need: the Qdrant collection and the local
    checkout path, both scoped to one repository."""

    def __init__(self, collection_name: str, local_path: str):
        self.collection_name = collection_name
        self.local_path = local_path

    def _safe_path(self, relative_path: str) -> Path:
        base = Path(self.local_path).resolve()
        target = (base / relative_path).resolve()
        if base not in target.parents and target != base:
            raise ValueError("Path escapes repository root")
        return target

    async def search_code(self, query: str, path_prefix: str | None = None) -> List[dict]:
        chunks: List[RetrievedChunk] = await retrieve(
            self.collection_name, query, top_k=6, path_prefix=path_prefix or None
        )
        return [
            {"path": c.path, "start_line": c.start_line, "end_line": c.end_line,
             "symbol": c.symbol, "text": c.text}
            for c in chunks
        ]

    def read_file(self, path: str, start_line: int | None = None, end_line: int | None = None) -> str:
        target = self._safe_path(path)
        if not target.is_file():
            return f"ERROR: {path} not found"
        text = target.read_text(encoding="utf-8", errors="ignore")
        if start_line is None and end_line is None:
            return text
        lines = text.splitlines()
        start = max((start_line or 1) - 1, 0)
        end = end_line or len(lines)
        return "\n".join(lines[start:end])

    def list_directory(self, path: str = "") -> List[str]:
        target = self._safe_path(path)
        if not target.is_dir():
            return [f"ERROR: {path} is not a directory"]
        entries = sorted(os.listdir(target))
        return entries[:200]

    async def dispatch(self, name: str, arguments: dict):
        if name == "search_code":
            return await self.search_code(arguments.get("query", ""), arguments.get("path_prefix"))
        if name == "read_file":
            return self.read_file(
                arguments.get("path", ""), arguments.get("start_line"), arguments.get("end_line")
            )
        if name == "list_directory":
            return self.list_directory(arguments.get("path", ""))
        return f"ERROR: unknown tool {name}"
