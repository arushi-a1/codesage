"""Orchestrates the end-to-end indexing pipeline for a repository:

  clone -> discover files -> Tree-sitter chunk -> embed -> upsert to Qdrant
  -> persist file/chunk counts to Postgres -> mark repository READY

Progress is reported to Redis (`app.core.redis_client`) so the API layer
can expose polling / SSE progress endpoints without blocking on the whole
job, and the DB row's `status`/`status_detail` is updated as the durable
record.

This function is designed to be run as a background task (FastAPI
BackgroundTasks or an external worker) — it owns its own DB session.
"""
from __future__ import annotations

import logging
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis_client import set_job_status
from app.db.models.repository import IndexedFile, IndexStatus, Repository
from app.db.session import AsyncSessionLocal
from app.services.github_service import clone_repository, iter_source_files
from app.services.indexing.chunker import chunk_source
from app.services.indexing.embedder import embed_chunks_in_batches
from app.services.indexing.qdrant_store import ensure_collection, upsert_chunks

logger = logging.getLogger(__name__)
settings = get_settings()


async def _update_repo(db: AsyncSession, repo: Repository, **fields) -> None:
    for k, v in fields.items():
        setattr(repo, k, v)
    db.add(repo)
    await db.commit()
    await db.refresh(repo)


async def run_indexing_job(repository_id: str) -> None:
    async with AsyncSessionLocal() as db:
        repo = await db.get(Repository, repository_id)
        if repo is None:
            logger.error("Repository %s not found, aborting index job", repository_id)
            return

        try:
            await set_job_status(repository_id, "cloning")
            await _update_repo(db, repo, status=IndexStatus.CLONING, status_detail="Cloning repository")

            local_path = os.path.join(settings.repo_clone_dir, repository_id)
            local_path = clone_repository(repo.github_url, local_path, branch=repo.default_branch or None)
            await _update_repo(db, repo, local_path=local_path)

            await set_job_status(repository_id, "parsing")
            await _update_repo(db, repo, status=IndexStatus.PARSING, status_detail="Parsing files")

            collection_name = repo.qdrant_collection_name
            await ensure_collection(collection_name)

            all_chunks = []
            file_records = []
            for rel_path, abs_path in iter_source_files(local_path, settings.max_file_size_kb):
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        source = f.read()
                except OSError:
                    continue
                if not source.strip():
                    continue

                chunks = chunk_source(rel_path, source)
                if not chunks:
                    continue
                all_chunks.extend(chunks)
                file_records.append(
                    IndexedFile(
                        repository_id=repo.id,
                        path=rel_path,
                        language=chunks[0].language,
                        chunk_count=len(chunks),
                    )
                )

            await set_job_status(repository_id, "embedding", detail=f"{len(all_chunks)} chunks")
            await _update_repo(
                db, repo, status=IndexStatus.EMBEDDING,
                status_detail=f"Embedding {len(all_chunks)} chunks across {len(file_records)} files",
            )

            texts = [c.text for c in all_chunks]
            vectors = await embed_chunks_in_batches(texts)
            await upsert_chunks(collection_name, all_chunks, vectors)

            for record in file_records:
                db.add(record)

            await _update_repo(
                db, repo,
                status=IndexStatus.READY,
                status_detail="Indexing complete",
                file_count=len(file_records),
                chunk_count=len(all_chunks),
            )
            await set_job_status(repository_id, "ready")

        except Exception as exc:  # noqa: BLE001 - want to persist any failure reason
            logger.exception("Indexing job failed for repo %s", repository_id)
            await set_job_status(repository_id, "failed", detail=str(exc))
            await _update_repo(
                db, repo, status=IndexStatus.FAILED, status_detail=f"Indexing failed: {exc}"
            )
