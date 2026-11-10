"""Regression test: GET /chat/sessions/{id}/messages returned 500 because
ChatMessage.citations is stored as a JSON string but ChatMessageOut
declared it as a list."""
import json

from sqlalchemy import select

from app.db.models.chat import ChatMessage, ChatSession, MessageRole
from app.db.models.repository import IndexStatus, Repository
from app.db.models.user import User


async def _login(client, email="history@example.com"):
    await client.post("/api/auth/register", json={"email": email, "password": "supersecret1"})
    login = await client.post("/api/auth/login", json={"email": email, "password": "supersecret1"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_list_messages_returns_decoded_citations(client, db_session):
    headers = await _login(client)
    user = (await db_session.scalars(select(User).where(User.email == "history@example.com"))).one()

    repo = Repository(owner_id=user.id, github_url="https://github.com/o/r", full_name="o/r", status=IndexStatus.READY)
    db_session.add(repo)
    await db_session.commit()
    session = ChatSession(user_id=user.id, repository_id=repo.id, mode="chat", title="t")
    db_session.add(session)
    await db_session.commit()

    citation = {"path": "a.py", "start_line": 1, "end_line": 5, "symbol": "foo"}
    db_session.add_all([
        ChatMessage(session_id=session.id, role=MessageRole.USER, content="question"),
        ChatMessage(session_id=session.id, role=MessageRole.ASSISTANT, content="answer", citations=json.dumps([citation])),
    ])
    await db_session.commit()

    resp = await client.get(f"/api/chat/sessions/{session.id}/messages", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert [m["content"] for m in body] == ["question", "answer"]
    assert body[0]["citations"] == []
    assert body[1]["citations"] == [citation]
