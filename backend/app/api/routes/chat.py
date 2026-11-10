import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import enforce_rate_limit, get_current_user
from app.db.models.chat import ChatMessage, ChatSession, MessageRole
from app.db.models.repository import IndexStatus, Repository
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.schemas import ChatMessageCreate, ChatMessageOut, ChatSessionCreate, ChatSessionOut
from app.services.rag.pipeline import sse_format, stream_chat_response

router = APIRouter(prefix="/chat", tags=["chat"])

VALID_MODES = {"chat", "codegen", "bug_detection", "architecture", "refactor"}


@router.post("/sessions", response_model=ChatSessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: ChatSessionCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    if payload.mode not in VALID_MODES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"mode must be one of {sorted(VALID_MODES)}")

    repo = await db.get(Repository, payload.repository_id)
    if repo is None or repo.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")

    session = ChatSession(
        user_id=user.id,
        repository_id=repo.id,
        mode=payload.mode,
        title=payload.title or f"{payload.mode} — {repo.full_name}",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def list_messages(session_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    session = await _get_owned_session(session_id, db, user)
    result = await db.scalars(
        select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at)
    )
    return [ChatMessageOut.model_validate(m) for m in result.all()]


async def _get_owned_session(session_id: uuid.UUID, db: AsyncSession, user: User) -> ChatSession:
    session = await db.get(ChatSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat session not found")
    return session


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: uuid.UUID,
    payload: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Streams the assistant's reply over Server-Sent Events. Persists both
    the user message and the final assistant message once streaming
    completes."""
    await enforce_rate_limit(user, bucket="chat", limit=30, window_seconds=60)

    session = await _get_owned_session(session_id, db, user)
    repo = await db.get(Repository, session.repository_id)
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
    if repo.status != IndexStatus.READY:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Repository is not ready yet (status={repo.status.value})")

    user_msg = ChatMessage(session_id=session.id, role=MessageRole.USER, content=payload.content)
    db.add(user_msg)
    await db.commit()

    history_rows = await db.scalars(
        select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at)
    )
    history = [
        {"role": "user" if m.role == MessageRole.USER else "assistant", "content": m.content}
        for m in history_rows.all()
        if m.id != user_msg.id
    ][-20:]  # cap context window growth

    async def event_stream():
        full_text = []
        citations: list[dict] = []
        async for event in stream_chat_response(
            collection_name=repo.qdrant_collection_name,
            local_path=repo.local_path,
            mode=session.mode,
            history=history,
            user_message=payload.content,
        ):
            if event["type"] == "token":
                full_text.append(event["content"])
            elif event["type"] == "citations":
                citations = event["citations"]
            yield sse_format(event)

        assistant_msg = ChatMessage(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content="".join(full_text),
            citations=json.dumps(citations),
        )
        db.add(assistant_msg)
        await db.commit()

    return StreamingResponse(event_stream(), media_type="text/event-stream")
