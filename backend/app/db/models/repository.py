import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class IndexStatus(str, enum.Enum):
    PENDING = "pending"
    CLONING = "cloning"
    PARSING = "parsing"
    EMBEDDING = "embedding"
    READY = "ready"
    FAILED = "failed"


class Repository(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "repositories"

    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    github_url: Mapped[str] = mapped_column(String(512), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)  # "org/repo"
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    status: Mapped[IndexStatus] = mapped_column(
        Enum(IndexStatus), default=IndexStatus.PENDING
    )
    status_detail: Mapped[str] = mapped_column(Text, default="")
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    local_path: Mapped[str] = mapped_column(String(1024), default="")

    owner = relationship("User", back_populates="repositories")
    files = relationship("IndexedFile", back_populates="repository", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="repository", cascade="all, delete-orphan")

    @property
    def qdrant_collection_name(self) -> str:
        return f"repo_{self.id.hex}"


class IndexedFile(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "indexed_files"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id")
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    language: Mapped[str] = mapped_column(String(64), default="")
    sha: Mapped[str] = mapped_column(String(64), default="")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    repository = relationship("Repository", back_populates="files")
