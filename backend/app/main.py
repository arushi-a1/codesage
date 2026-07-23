from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, chat, pr, repos
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.redis_client import close_redis
import app.db.models  # noqa: F401 - registers all models on Base.metadata
from app.db.base import Base
from app.db.session import engine

settings = get_settings()
configure_logging("DEBUG" if settings.environment == "development" else "INFO")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create tables in dev; production deployments should use Alembic
    # migrations instead (see docs/SETUP.md).
    if settings.environment == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="CodeSage API",
    description="AI software engineering assistant: repo indexing, RAG chat, code generation, PR review.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(repos.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(pr.router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
