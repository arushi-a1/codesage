import pytest


async def test_register_creates_user(client):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "dev@example.com", "password": "supersecret1", "full_name": "Dev User"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "dev@example.com"
    assert "hashed_password" not in body


async def test_register_duplicate_email_rejected(client):
    payload = {"email": "dupe@example.com", "password": "supersecret1"}
    first = await client.post("/api/auth/register", json=payload)
    assert first.status_code == 201
    second = await client.post("/api/auth/register", json=payload)
    assert second.status_code == 400


async def test_login_success_returns_tokens(client):
    await client.post(
        "/api/auth/register", json={"email": "login@example.com", "password": "supersecret1"}
    )
    resp = await client.post(
        "/api/auth/login", json={"email": "login@example.com", "password": "supersecret1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


async def test_login_wrong_password_rejected(client):
    await client.post(
        "/api/auth/register", json={"email": "wrongpw@example.com", "password": "supersecret1"}
    )
    resp = await client.post(
        "/api/auth/login", json={"email": "wrongpw@example.com", "password": "not-the-password"}
    )
    assert resp.status_code == 401


async def test_protected_route_requires_token(client):
    resp = await client.get("/api/repositories")
    assert resp.status_code == 401


async def test_full_auth_flow_allows_protected_access(client):
    await client.post(
        "/api/auth/register", json={"email": "flow@example.com", "password": "supersecret1"}
    )
    login = await client.post(
        "/api/auth/login", json={"email": "flow@example.com", "password": "supersecret1"}
    )
    token = login.json()["access_token"]
    resp = await client.get("/api/repositories", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_refresh_token_flow(client):
    await client.post(
        "/api/auth/register", json={"email": "refresh@example.com", "password": "supersecret1"}
    )
    login = await client.post(
        "/api/auth/login", json={"email": "refresh@example.com", "password": "supersecret1"}
    )
    refresh_token = login.json()["refresh_token"]
    resp = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_access_token_rejected_at_refresh_endpoint(client):
    """An access token should not work where a refresh token is required."""
    await client.post(
        "/api/auth/register", json={"email": "wrongtype@example.com", "password": "supersecret1"}
    )
    login = await client.post(
        "/api/auth/login", json={"email": "wrongtype@example.com", "password": "supersecret1"}
    )
    access_token = login.json()["access_token"]
    resp = await client.post("/api/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401
