# Architecture

## Overview

CodeSage has four moving parts:

1. **Indexing pipeline** — turns a GitHub repo into searchable vectors.
2. **RAG retriever** — turns a question into relevant code chunks.
3. **LangGraph agent** — decides what extra context to pull and produces the answer.
4. **API + frontend** — auth, persistence, and the streaming chat UI.

```
┌─────────────┐     clone      ┌──────────────┐    chunk     ┌─────────────┐
│  GitHub repo │ ─────────────▶ │ local checkout│ ───────────▶│ Tree-sitter │
└─────────────┘                └──────────────┘              │  chunker    │
                                                               └──────┬──────┘
                                                                      │ CodeChunk[]
                                                                      ▼
                                                              ┌───────────────┐
                                                              │ OpenAI embed  │
                                                              └───────┬───────┘
                                                                      │ vectors
                                                                      ▼
                                                              ┌───────────────┐
                                                              │    Qdrant     │  (1 collection / repo)
                                                              └───────────────┘
```

```
User question
     │
     ▼
┌─────────────────┐   embed + search   ┌───────────────┐
│  seed retrieval  │ ──────────────────▶│    Qdrant     │
└────────┬─────────┘                    └───────────────┘
         │ seed chunks
         ▼
┌───────────────────────────────┐
│  LangGraph agent (bounded     │  tools: search_code, read_file, list_directory
│  ReAct loop, ≤4 tool rounds)  │
└────────────┬───────────────────┘
             │ full context (seed + tool results)
             ▼
┌───────────────────────────────┐
│  Final streaming completion    │ ──▶ SSE tokens ──▶ browser
└───────────────────────────────┘
```

## Why Tree-sitter chunking instead of fixed windows

Fixed-size chunking (e.g. "every 50 lines") routinely splits a function
signature from its body, or a class from half its methods — which hurts
embedding quality (the vector represents an incoherent fragment) and hurts
citation quality (you can't point someone at "lines 43-93" and have that be
a coherent unit).

`app/services/indexing/chunker.py` parses each file with the
language-appropriate Tree-sitter grammar and walks the syntax tree looking
for "definition" nodes (functions, methods, classes, interfaces — the exact
node types are tuned per language in `DEFINITION_NODE_TYPES`). Each
definition becomes its own chunk, tagged with the symbol name and exact
line range. Anything not inside a definition (imports, constants,
module-level docstrings) is captured as a separate "module-level" chunk.
Files in unsupported languages, or that fail to parse, fall back to
overlapping line-window chunking so nothing is silently skipped.

## Why a bounded agent loop instead of one giant retrieval

A single embedding search over the user's raw question works well for
"what does X do" style questions where the phrasing matches the code
closely. It works less well when the model needs to *decide* where to
look — e.g. "why would this endpoint 500 under load" requires reading a
few files, not just the top-K nearest neighbors of that sentence.

`app/services/agents/graph.py` builds a small LangGraph `StateGraph` with
two nodes:

- **agent** — calls the chat model with the conversation so far and the
  tool specs (`search_code`, `read_file`, `list_directory`); the model
  either replies directly or asks to call one or more tools.
- **tools** — executes whatever the model asked for, scoped to the current
  repo's Qdrant collection and local checkout (path traversal outside the
  checkout is rejected in `RepoToolContext._safe_path`).

The graph loops between these two nodes until the model stops requesting
tools or `MAX_TOOL_ITERATIONS` (4) is hit, then control returns to
`services/rag/pipeline.py`, which does a **separate, streamed** completion
call so the user sees fluent token-by-token output instead of the
back-and-forth tool-calling transcript.

## Modes

A chat session has a `mode` that selects the system prompt in
`MODE_SYSTEM_PROMPTS` (`app/services/agents/graph.py`):

| Mode            | Used for                                             |
|-----------------|-------------------------------------------------------|
| `chat`          | General Q&A about the codebase                        |
| `codegen`       | Generating a unified diff for a requested change       |
| `bug_detection` | Investigating an area for concrete, citable bugs        |
| `architecture`  | Summarizing module boundaries and structure            |
| `refactor`      | Proposing incremental refactors with rationale          |
| `pr_review`     | Reviewing a fetched GitHub PR diff                      |

PR review (`app/api/routes/pr.py`) reuses the same pipeline: it fetches the
diff via the GitHub REST API, feeds it into the agent as the first user
message (truncated to 20k characters to protect the context window), and
lets the agent pull in surrounding file context with `read_file` if it
needs to understand code the diff doesn't show.

## Data model

- **User** — auth identity.
- **Repository** — one GitHub repo import; owns an indexing `status`
  (`pending → cloning → parsing → embedding → ready`, or `failed`) and its
  own Qdrant collection (`repo_<uuid>`).
- **IndexedFile** — one row per indexed file (path, language, chunk count)
  — mainly for the UI/debugging; the actual chunk text/vectors live in
  Qdrant, not Postgres.
- **ChatSession** — a conversation scoped to one repository and one mode.
- **ChatMessage** — persisted turns, including the citation list the
  assistant's answer was grounded in.

## Streaming transport

The backend uses `StreamingResponse` with `text/event-stream` and a tiny
hand-rolled SSE envelope (`sse_format` in `services/rag/pipeline.py`):
`{"type": "citations"|"token"|"done"|"error", ...}`. The frontend's
`streamSSE` helper (`frontend/src/api/client.ts`) reads the response body
with a `ReadableStreamDefaultReader`, splits on blank lines, and parses
each `data: ...` frame — no external SSE library needed.

## Security notes

- JWT access tokens are short-lived (default 60 min); refresh tokens
  (default 14 days) are only accepted at `/auth/refresh` (`decode_token`
  checks the `type` claim), so a leaked access token can't be used to mint
  new ones.
- Passwords are hashed with bcrypt via passlib.
- `RepoToolContext._safe_path` resolves paths against the repo's local
  checkout root and rejects anything that escapes it, so the `read_file`/
  `list_directory` tools can't be used to read arbitrary host files even
  if the model is coaxed into trying.
- Chat and PR-review endpoints are rate-limited per user via Redis
  (`enforce_rate_limit`).
