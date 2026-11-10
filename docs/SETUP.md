# Setup

## Prerequisites

- Docker + Docker Compose v2
- An OpenAI API key
- (Optional but recommended) a GitHub personal access token — required for
  private repos, and raises the unauthenticated GitHub API rate limit
  (60 req/hr) to 5,000 req/hr for PR review calls.

## 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

| Variable          | Required | Notes                                          |
|-------------------|----------|-------------------------------------------------|
| `JWT_SECRET_KEY`  | Yes      | Long random string. `openssl rand -hex 32`     |
| `OPENAI_API_KEY`  | Yes      | Used for both chat completions and embeddings   |
| `GITHUB_TOKEN`    | Recommended | PAT with `repo` scope for private repos      |
| `OPENAI_CHAT_MODEL` | No     | Defaults to `gpt-4.1`                          |
| `OPENAI_EMBEDDING_MODEL` | No | Defaults to `text-embedding-3-small` (1536-dim) |

If you change `OPENAI_EMBEDDING_MODEL` to one with a different vector
size, also update `openai_embedding_dim` in `backend/app/core/config.py`
(and re-index existing repos — Qdrant collections are created with a fixed
vector size).

## 2. Run it

```bash
docker compose up --build
```

This starts: `postgres`, `redis`, `qdrant`, `backend` (FastAPI on `:8000`),
`frontend` (Vite dev server on `:5173`).

The backend's `lifespan` handler auto-creates tables on startup when
`ENVIRONMENT=development` (the default), so there's nothing else to run
for a first local boot. For anything beyond local dev, use Alembic
migrations instead (below).

Open http://localhost:5173, register an account, and import a repo.

## 3. Database migrations (production)

Table auto-creation is dev-only. For a real deployment:

```bash
cd backend
alembic upgrade head
```

The initial schema ships as `alembic/versions/0001_initial_schema.py`.
After changing a model, generate a new revision with
`alembic revision --autogenerate -m "describe change"`, review it (enum
types and data migrations usually need hand edits), and commit it.

Set `ENVIRONMENT=production` in `.env` so the app doesn't also try
`create_all` on startup.

## Running the backend outside Docker

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export $(cat ../.env | xargs)   # or use a proper env loader
uvicorn app.main:app --reload
```

You'll need local Postgres/Redis/Qdrant reachable at the URLs in `.env`
(easiest: `docker compose up postgres redis qdrant` and point
`DATABASE_URL`/`REDIS_URL`/`QDRANT_URL` at `localhost` instead of the
Docker service names).

## Running the frontend outside Docker

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_PROXY_TARGET` (or edit `vite.config.ts`) if your backend
isn't at `http://localhost:8000`.

## Tests

See [`DEVELOPMENT.md`](DEVELOPMENT.md).

## Troubleshooting

- **Repo stuck in `cloning`**: check `docker compose logs backend` — usually
  a bad `github_url` or a private repo without `GITHUB_TOKEN` set.
- **Repo stuck in `embedding` / fails**: check `OPENAI_API_KEY` is valid and
  has quota; check `docker compose logs backend` for the OpenAI error.
- **Qdrant connection refused**: make sure the `qdrant` service is healthy
  (`docker compose ps`) before the backend starts (compose's `depends_on`
  handles this, but a `docker compose restart backend` fixes races on
  first boot).
- **429 from chat**: the per-user rate limit — see `enforce_rate_limit` in
  `app/api/deps.py` to adjust limits.
