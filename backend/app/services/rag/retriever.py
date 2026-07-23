"""Retrieves relevant code chunks for a query against a repo's Qdrant
collection, and formats them into a context block + citation list.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.services.indexing.embedder import embed_batch
from app.services.indexing.qdrant_store import search


@dataclass
class RetrievedChunk:
    path: str
    start_line: int
    end_line: int
    symbol: Optional[str]
    text: str
    score: float


async def retrieve(
    collection_name: str, query: str, top_k: int = 8, path_prefix: Optional[str] = None
) -> List[RetrievedChunk]:
    vectors = await embed_batch([query])
    if not vectors:
        return []
    hits = await search(collection_name, vectors[0], top_k=top_k, path_prefix=path_prefix)
    return [
        RetrievedChunk(
            path=h["path"], start_line=h["start_line"], end_line=h["end_line"],
            symbol=h.get("symbol"), text=h["text"], score=h["score"],
        )
        for h in hits
    ]


def format_context(chunks: List[RetrievedChunk]) -> str:
    """Formats retrieved chunks into a single context string with clear
    delimiters so the LLM can attribute claims to specific files/lines."""
    blocks = []
    for c in chunks:
        header = f"# {c.path} (lines {c.start_line}-{c.end_line})"
        if c.symbol:
            header += f" — {c.symbol}"
        blocks.append(f"{header}\n```{'' }\n{c.text}\n```")
    return "\n\n".join(blocks)


def citations_from_chunks(chunks: List[RetrievedChunk]) -> List[dict]:
    return [
        {"path": c.path, "start_line": c.start_line, "end_line": c.end_line, "symbol": c.symbol}
        for c in chunks
    ]
