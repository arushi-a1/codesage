# Development

## Running tests

### Backend
```bash
cd backend
pip install -r requirements.txt
pytest                          # all tests
pytest --cov=app --cov-report=term-missing   # with coverage
pytest tests/test_chunker.py -v # a single file
```
Tests use in-memory SQLite (`tests/conftest.py`) and mock external calls
(OpenAI, Qdrant) — no live services required to run the suite. CI
(`.github/workflows/ci.yml`) runs this on every push/PR.

### Frontend
```bash
cd frontend
npm install
npx tsc -b        # typecheck
npx vitest run    # unit tests
npx vite build    # production build sanity check
```

## Project layout

```
backend/app/
  core/            # config, security (JWT/bcrypt), redis client, logging
  db/               # SQLAlchemy models + async session
  schemas/          # Pydantic request/response models
  api/routes/       # FastAPI routers (auth, repos, chat, pr)
  services/
    github_service.py       # clone repos, fetch PR diffs
    indexing/                # chunker, embedder, qdrant_store, pipeline
    rag/                     # retriever, streaming pipeline
    agents/                  # LangGraph graph + tools
frontend/src/
  api/client.ts     # typed fetch wrapper + SSE streaming helper
  store/            # zustand auth store
  pages/            # LoginPage, RepositoriesPage, RepoChatPage
  components/       # Sidebar, shared UI
```

## Adding a new Tree-sitter language

1. Confirm `tree-sitter-languages` bundles the grammar you want (check
   its package contents) — it covers most mainstream languages.
2. Add the extension → grammar name mapping to `EXTENSION_LANGUAGE_MAP`
   in `backend/app/services/indexing/chunker.py`.
3. Add the language's "this is a definition worth its own chunk" node
   types to `DEFINITION_NODE_TYPES`. The quickest way to find these is to
   parse a sample file and print `node.type` while walking the tree:
   ```python
   from tree_sitter_languages import get_parser
   parser = get_parser("kotlin")
   tree = parser.parse(open("Sample.kt", "rb").read())
   def walk(n, d=0):
       print("  " * d, n.type)
       for c in n.children: walk(c, d + 1)
   walk(tree.root_node)
   ```
4. Add a test in `backend/tests/test_chunker.py` mirroring
   `test_javascript_chunking_finds_function_and_class`.
5. Re-index any repos containing that language (`POST /repositories/{id}/reindex`).

## Adding a new agent tool

Tools live in `backend/app/services/agents/tools.py`:

1. Add the OpenAI-format tool spec to `TOOL_SPECS`.
2. Implement the method on `RepoToolContext` (keep it scoped to the repo —
   see `_safe_path` for the pattern used to prevent path traversal).
3. Wire it into `RepoToolContext.dispatch`.
4. The LangGraph agent (`agents/graph.py`) picks up new tools automatically
   since it reads `TOOL_SPECS` directly — no graph changes needed unless
   the tool needs different looping/termination behavior.

## Adding a new chat mode

1. Add a system prompt to `MODE_SYSTEM_PROMPTS` in `agents/graph.py`.
2. Add the mode string to `VALID_MODES` in `api/routes/chat.py`.
3. Add it to the `MODES` array in `frontend/src/pages/RepoChatPage.tsx`
   (and a placeholder string in `placeholderFor`).

## Code style

- Backend: standard library `logging`, type hints throughout, async
  everywhere in the request path (no blocking calls in route handlers).
- Frontend: functional components + hooks, no class components; state
  that needs to survive route changes lives in `store/` (zustand), local
  UI state stays in `useState`.

## What's intentionally out of scope for this reference implementation

- Multi-tenant org/team accounts (single-owner repos only).
- Incremental re-indexing (reindex currently re-clones and re-embeds the
  whole repo; for very large monorepos you'd want to diff against the
  last indexed commit and only re-chunk changed files).
- A production-hardened frontend Docker image (the provided `Dockerfile`
  runs the Vite dev server; for production, add a multi-stage build that
  runs `vite build` and serves `dist/` via nginx).
- Websocket-based live indexing progress (current implementation polls
  `/repositories/{id}/status` from the UI every few seconds).
