"""Importing this package registers every ORM model with Base.metadata,
which is required for `Base.metadata.create_all` (dev) and for Alembic's
autogenerate (via env.py importing this package) to see all tables.
"""
from app.db.models.chat import ChatMessage, ChatSession  # noqa: F401
from app.db.models.repository import IndexedFile, Repository  # noqa: F401
from app.db.models.user import User  # noqa: F401
