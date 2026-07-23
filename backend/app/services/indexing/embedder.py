"""Wraps the OpenAI embeddings endpoint with batching and retry."""
from __future__ import annotations

from typing import List

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_random_exponential

from app.core.config import get_settings

settings = get_settings()
_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


@retry(wait=wait_random_exponential(min=1, max=20), stop=stop_after_attempt(5))
async def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed up to ~100 short/medium code chunks per call."""
    if not texts:
        return []
    client = get_openai_client()
    response = await client.embeddings.create(
        model=settings.openai_embedding_model,
        input=texts,
    )
    return [item.embedding for item in response.data]


async def embed_chunks_in_batches(texts: List[str], batch_size: int = 64) -> List[List[float]]:
    vectors: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        vectors.extend(await embed_batch(batch))
    return vectors
