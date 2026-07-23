import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import enforce_rate_limit, get_current_user
from app.db.models.repository import IndexStatus, Repository
from app.db.models.user import User
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.github_service import GitHubAPIClient
from app.services.rag.pipeline import sse_format, stream_chat_response

router = APIRouter(prefix="/repositories", tags=["pull-requests"])


@router.post("/{repo_id}/pull-requests/{pr_number}/review")
async def review_pull_request(
    repo_id: uuid.UUID,
    pr_number: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await enforce_rate_limit(user, bucket="pr_review", limit=10, window_seconds=60)

    repo = await db.get(Repository, repo_id)
    if repo is None or repo.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
    if repo.status != IndexStatus.READY:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Repository is not ready yet (status={repo.status.value})")

    gh = GitHubAPIClient()
    try:
        diff = await gh.get_pull_request_diff(repo.full_name, pr_number)
        pr_meta = await gh.get_pull_request(repo.full_name, pr_number)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Failed to fetch PR from GitHub: {exc}") from exc
    finally:
        await gh.close()

    truncated_diff = diff[:20000]  # guard against giant diffs blowing the context window
    user_message = (
        f"Review PR #{pr_number}: {pr_meta.get('title', '')}\n\n"
        f"Description:\n{pr_meta.get('body') or '(no description)'}\n\n"
        f"Diff:\n```diff\n{truncated_diff}\n```"
    )

    async def event_stream():
        async for event in stream_chat_response(
            collection_name=repo.qdrant_collection_name,
            local_path=repo.local_path,
            mode="pr_review",
            history=[],
            user_message=user_message,
        ):
            yield sse_format(event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
