import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.redis_client import get_job_status
from app.db.models.repository import IndexStatus, Repository
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.schemas import RepositoryCreate, RepositoryOut, RepositoryStatusOut
from app.services.github_service import GitHubError, parse_repo_full_name
from app.services.indexing.pipeline import run_indexing_job
from app.services.indexing.qdrant_store import delete_collection

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.post("", response_model=RepositoryOut, status_code=status.HTTP_201_CREATED)
async def import_repository(
    payload: RepositoryCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        full_name = parse_repo_full_name(payload.github_url)
    except GitHubError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    repo = Repository(
        owner_id=user.id,
        github_url=payload.github_url,
        full_name=full_name,
        default_branch=payload.branch or "main",
        status=IndexStatus.PENDING,
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)

    background_tasks.add_task(run_indexing_job, str(repo.id))
    return repo


@router.get("", response_model=list[RepositoryOut])
async def list_repositories(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.scalars(
        select(Repository).where(Repository.owner_id == user.id).order_by(Repository.created_at.desc())
    )
    return result.all()


async def _get_owned_repo(repo_id: uuid.UUID, db: AsyncSession, user: User) -> Repository:
    repo = await db.get(Repository, repo_id)
    if repo is None or repo.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
    return repo


@router.get("/{repo_id}", response_model=RepositoryOut)
async def get_repository(repo_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await _get_owned_repo(repo_id, db, user)


@router.get("/{repo_id}/status", response_model=RepositoryStatusOut)
async def get_repository_status(repo_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    repo = await _get_owned_repo(repo_id, db, user)
    live = await get_job_status(str(repo.id))
    return RepositoryStatusOut(status=live.get("status", repo.status.value), detail=live.get("detail", repo.status_detail))


@router.post("/{repo_id}/reindex", response_model=RepositoryOut)
async def reindex_repository(
    repo_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    repo = await _get_owned_repo(repo_id, db, user)
    repo.status = IndexStatus.PENDING
    repo.status_detail = "Re-index queued"
    db.add(repo)
    await db.commit()
    await db.refresh(repo)
    background_tasks.add_task(run_indexing_job, str(repo.id))
    return repo


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository(repo_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    repo = await _get_owned_repo(repo_id, db, user)
    await delete_collection(repo.qdrant_collection_name)
    await db.delete(repo)
    await db.commit()
