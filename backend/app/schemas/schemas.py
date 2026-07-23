import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


# --- Auth ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = ""


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    model_config = {"from_attributes": True}


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# --- Repositories ---
class RepositoryCreate(BaseModel):
    github_url: str
    branch: Optional[str] = None


class RepositoryOut(BaseModel):
    id: uuid.UUID
    github_url: str
    full_name: str
    default_branch: str
    status: str
    status_detail: str
    file_count: int
    chunk_count: int
    created_at: datetime
    model_config = {"from_attributes": True}


class RepositoryStatusOut(BaseModel):
    status: str
    detail: str = ""


# --- Chat ---
class ChatSessionCreate(BaseModel):
    repository_id: uuid.UUID
    mode: str = "chat"  # chat|codegen|bug_detection|architecture|refactor
    title: Optional[str] = None


class ChatSessionOut(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    title: str
    mode: str
    created_at: datetime
    model_config = {"from_attributes": True}


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    citations: List[dict] = []
    created_at: datetime
    model_config = {"from_attributes": True}


class ChatMessageCreate(BaseModel):
    content: str


# --- PR review ---
class PRReviewRequest(BaseModel):
    pr_number: int
