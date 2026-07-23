"""Centralized application configuration.

All environment-derived settings live here so the rest of the codebase
never touches os.environ directly. See .env.example for every supported
variable and docs/SETUP.md for explanations.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Auth ---
    jwt_secret_key: str = "insecure-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 14

    # --- OpenAI ---
    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4.1"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dim: int = 1536

    # --- GitHub ---
    github_token: str = ""

    # --- Postgres ---
    database_url: str = "postgresql+asyncpg://codesage:codesage@localhost:5432/codesage"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Qdrant ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_prefix: str = "codesage"

    # --- App ---
    environment: str = "development"
    cors_origins: str = "http://localhost:5173"
    repo_clone_dir: str = "/data/repos"
    max_file_size_kb: int = 800
    chunk_max_tokens: int = 400

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
