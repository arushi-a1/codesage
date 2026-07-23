"""Async Redis client used for: indexing job status/progress, simple rate
limiting on chat/completion endpoints, and pub/sub for streaming indexing
progress to multiple subscribers if needed.
"""
from __future__ import annotations

import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# --- Simple fixed-window rate limiter, used by chat/completion routes ---
async def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """Returns True if the request is allowed, False if the caller is over
    the limit for the current window."""
    r = get_redis()
    current = await r.incr(key)
    if current == 1:
        await r.expire(key, window_seconds)
    return current <= limit


# --- Indexing job status helpers ---
def job_status_key(repo_id: str) -> str:
    return f"index_job:{repo_id}:status"


async def set_job_status(repo_id: str, status: str, detail: str = "") -> None:
    r = get_redis()
    await r.hset(job_status_key(repo_id), mapping={"status": status, "detail": detail})
    await r.expire(job_status_key(repo_id), 60 * 60 * 24)


async def get_job_status(repo_id: str) -> dict:
    r = get_redis()
    data = await r.hgetall(job_status_key(repo_id))
    return data or {"status": "unknown", "detail": ""}
