# CodeSage — AI Software Engineering Assistant

CodeSage is a self-hosted, Cursor-style AI coding assistant. Import a GitHub
repository, CodeSage indexes it (Tree-sitter → chunks → OpenAI embeddings →
Qdrant), and you get a streaming RAG chat that can answer questions about the
codebase, explain architecture, find bugs, suggest refactors, generate code
changes, and review pull requests — all backed by a LangGraph agent with
real tools (search, read file, propose diff).

## Stack

| Layer         | Technology                                   |
|---------------|-----------------------------------------------|
| Frontend      | React + TypeScript + Vite, SSE streaming      |
| Backend       | FastAPI (async), LangGraph, JWT auth          |
| Database      | PostgreSQL (SQLAlchemy 2.0 async, Alembic)    |
| Cache/Queue   | Redis (rate limiting, job status, pub/sub)    |
| Vector store  | Qdrant                                        |
| Parsing       | Tree-sitter (Python, JS, TS, Go, Java, ...)   |
| LLM/Embeddings| OpenAI API                                    |
| Infra         | Docker Compose                                |

## Quick start

```bash
cp .env.example .env      # fill in OPENAI_API_KEY, GITHUB_TOKEN, secrets
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend API docs: http://localhost:8000/docs
- Qdrant dashboard: http://localhost:6333/dashboard

## Docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system design, data flow, agent graph
- [`docs/API.md`](docs/API.md) — REST + streaming endpoint reference
- [`docs/SETUP.md`](docs/SETUP.md) — local dev setup, env vars, migrations
- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) — running tests, adding a language, extending agent tools

## Core capabilities

1. **Repo import** — clone a GitHub repo (public or via PAT for private), track indexing status.
2. **Indexing** — Tree-sitter splits files into semantically meaningful chunks (functions, classes) rather than naive fixed-size windows; each chunk is embedded and upserted into Qdrant with file/line metadata.
3. **RAG chat** — retrieval-augmented chat scoped to a repo, streamed token-by-token over SSE.
4. **Code generation** — agent proposes unified diffs grounded in retrieved context.
5. **PR review** — fetches a GitHub PR's diff, runs it through the agent for bug/style/security review.
6. **Bug detection & refactor suggestions** — dedicated agent nodes reasoning over retrieved code.
7. **Architecture explanation** — agent synthesizes a directory/module-level summary from indexed chunks.

## License

MIT (sample/reference project).
