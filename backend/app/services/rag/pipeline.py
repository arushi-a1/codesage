"""Ties together retrieval, the LangGraph tool-using agent, and a final
streaming completion. This is what the /chat SSE endpoint calls.

Flow:
  1. Do an upfront semantic search so the model starts with concrete
     context (cheap, always useful) rather than needing a tool round-trip
     for the common case.
  2. Run the bounded agent loop (services/agents/graph.py) so the model
     can pull more context on demand (read_file, list_directory, more
     search_code calls) for harder questions.
  3. Stream the final natural-language answer token-by-token.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator, List, Optional

from app.core.config import get_settings
from app.services.agents.graph import MODE_SYSTEM_PROMPTS, run_agent_context_gathering
from app.services.agents.tools import RepoToolContext
from app.services.indexing.embedder import get_openai_client
from app.services.rag.retriever import citations_from_chunks, format_context, retrieve

settings = get_settings()


async def stream_chat_response(
    collection_name: str,
    local_path: str,
    mode: str,
    history: List[dict],
    user_message: str,
) -> AsyncGenerator[dict, None]:
    """Yields SSE-ready event dicts: {"type": "citations"|"token"|"done"|"error", ...}."""
    try:
        seed_chunks = await retrieve(collection_name, user_message, top_k=6)
        seed_context = format_context(seed_chunks)
        citations = citations_from_chunks(seed_chunks)

        yield {"type": "citations", "citations": citations}

        tool_ctx = RepoToolContext(collection_name=collection_name, local_path=local_path)
        seeded_history = history + [
            {
                "role": "system",
                "content": f"Initial retrieved context (may not be sufficient):\n\n{seed_context}",
            }
        ]
        agent_messages = await run_agent_context_gathering(
            tool_ctx, mode=mode, history=seeded_history, user_message=user_message
        )

        client = get_openai_client()
        system_prompt = MODE_SYSTEM_PROMPTS.get(mode, MODE_SYSTEM_PROMPTS["chat"])
        final_messages = [{"role": "system", "content": system_prompt}] + _sanitize(agent_messages)
        final_messages.append(
            {
                "role": "system",
                "content": (
                    "Now write the final answer for the user in clear prose/markdown. "
                    "Cite file paths and line ranges inline like `path/to/file.py:12-40` "
                    "when referring to specific code."
                ),
            }
        )

        stream = await client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=final_messages,
            temperature=0.2,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield {"type": "token", "content": delta}

        yield {"type": "done"}

    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "message": str(exc)}


def _sanitize(messages: List[dict]) -> List[dict]:
    """Drop tool_call scaffolding the final plain-completion call doesn't
    need to see verbatim, but keep tool results as readable context."""
    cleaned = []
    for m in messages:
        role = m.get("role")
        if role == "tool":
            cleaned.append({"role": "system", "content": f"[tool result]\n{m.get('content', '')}"})
        elif role == "assistant" and m.get("tool_calls") and not m.get("content"):
            continue  # skip empty assistant messages that only carried tool calls
        else:
            cleaned.append({"role": role, "content": m.get("content", "")})
    return cleaned


def sse_format(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"
