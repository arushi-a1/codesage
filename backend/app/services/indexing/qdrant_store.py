"""Qdrant integration. Each repository gets its own collection so we can
cheaply delete/re-index a single repo, and so retrieval never leaks chunks
across repos even by mistake.
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings
from app.services.indexing.chunker import CodeChunk

settings = get_settings()
_client: AsyncQdrantClient | None = None


def get_qdrant_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(url=settings.qdrant_url)
    return _client


async def ensure_collection(collection_name: str) -> None:
    client = get_qdrant_client()
    exists = await client.collection_exists(collection_name)
    if not exists:
        await client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=settings.openai_embedding_dim,
                distance=models.Distance.COSINE,
            ),
        )
        # Index payload fields we filter on frequently
        await client.create_payload_index(
            collection_name, field_name="path", field_schema=models.PayloadSchemaType.KEYWORD
        )
        await client.create_payload_index(
            collection_name, field_name="language", field_schema=models.PayloadSchemaType.KEYWORD
        )


async def delete_collection(collection_name: str) -> None:
    client = get_qdrant_client()
    if await client.collection_exists(collection_name):
        await client.delete_collection(collection_name)


async def upsert_chunks(
    collection_name: str, chunks: List[CodeChunk], vectors: List[List[float]]
) -> None:
    assert len(chunks) == len(vectors)
    if not chunks:
        return
    client = get_qdrant_client()
    points = [
        models.PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "path": chunk.path,
                "language": chunk.language,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "symbol": chunk.symbol,
                "kind": chunk.kind,
                "text": chunk.text,
            },
        )
        for chunk, vector in zip(chunks, vectors)
    ]
    await client.upsert(collection_name=collection_name, points=points, wait=True)


async def delete_file_chunks(collection_name: str, path: str) -> None:
    client = get_qdrant_client()
    await client.delete(
        collection_name=collection_name,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[models.FieldCondition(key="path", match=models.MatchValue(value=path))]
            )
        ),
    )


async def search(
    collection_name: str,
    query_vector: List[float],
    top_k: int = 8,
    path_prefix: Optional[str] = None,
) -> List[dict]:
    client = get_qdrant_client()
    query_filter = None
    if path_prefix:
        query_filter = models.Filter(
            must=[models.FieldCondition(key="path", match=models.MatchText(text=path_prefix))]
        )
    results = await client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    )
    return [
        {
            "score": point.score,
            "path": point.payload.get("path"),
            "language": point.payload.get("language"),
            "start_line": point.payload.get("start_line"),
            "end_line": point.payload.get("end_line"),
            "symbol": point.payload.get("symbol"),
            "kind": point.payload.get("kind"),
            "text": point.payload.get("text"),
        }
        for point in results.points
    ]
