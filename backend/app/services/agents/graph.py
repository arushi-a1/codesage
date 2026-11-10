"""LangGraph agent: a bounded ReAct loop over the repo tools (search_code,
read_file, list_directory).

Design: the graph's job is *context gathering and tool use*, not producing
the final user-facing text — that's done as a separate streaming
completion afterwards (see services/rag/pipeline.py) so tokens can be
streamed to the client over SSE while the tool-calling steps themselves
happen non-streamed. This mirrors how Cursor-like tools work in practice:
a short deliberation/tool phase, then a fluent, streamed final answer.
"""
from __future__ import annotations

import json
import logging
import operator
from typing import Annotated, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from app.core.config import get_settings
from app.services.agents.tools import TOOL_SPECS, RepoToolContext
from app.services.indexing.embedder import get_openai_client

logger = logging.getLogger(__name__)
settings = get_settings()

MAX_TOOL_ITERATIONS = 4

MODE_SYSTEM_PROMPTS = {
    "chat": (
        "You are CodeSage, an expert AI pair programmer embedded in a codebase. "
        "Answer questions about the repository precisely, citing file paths and "
        "line ranges you actually retrieved. Use the available tools to look up "
        "code before answering rather than guessing."
    ),
    "codegen": (
        "You are CodeSage, generating a code change for the user's request. "
        "Investigate the relevant files with the tools, then produce a unified "
        "diff (```diff fenced) plus a short explanation. Keep changes minimal "
        "and consistent with the existing code style."
    ),
    "bug_detection": (
        "You are CodeSage, hunting for bugs. Investigate the area of the "
        "codebase the user points to (or the whole repo if unspecified), "
        "and report concrete, specific issues with file/line citations and "
        "a suggested fix for each. Do not invent issues you can't point to in code."
    ),
    "architecture": (
        "You are CodeSage, explaining the architecture of this repository. "
        "Use list_directory and search_code to understand module boundaries, "
        "then produce a clear, structured explanation (major components, how "
        "they interact, entry points)."
    ),
    "refactor": (
        "You are CodeSage, suggesting refactors. Investigate the referenced "
        "code, then propose specific, incremental refactors with rationale "
        "and, where useful, a diff. Prioritize readability, duplication, and "
        "coupling issues over stylistic nitpicks."
    ),
    "pr_review": (
        "You are CodeSage, reviewing a pull request diff. You will be given "
        "the diff directly in the conversation. Use search_code/read_file to "
        "pull in surrounding context from the base branch when needed. Flag "
        "bugs, security issues, and style/maintainability concerns, each with "
        "a file/line reference and a suggested fix. Be concise and specific."
    ),
}


class AgentState(TypedDict):
    # Plain list concatenation, NOT langgraph's `add_messages`: add_messages
    # converts OpenAI-style dicts into LangChain message objects, which made
    # every `isinstance(m, dict)` check below fail and silently disabled the
    # tool loop (the agent never executed a single tool call). Keeping the
    # state as raw OpenAI-format dicts end to end avoids that conversion.
    messages: Annotated[list, operator.add]
    mode: str
    iterations: int


def _tools_openai_format():
    return TOOL_SPECS


async def build_agent_step(tool_ctx: RepoToolContext):
    """Returns an async node function bound to a specific repo's tool context."""
    client = get_openai_client()

    async def agent_step(state: AgentState) -> AgentState:
        system_prompt = MODE_SYSTEM_PROMPTS.get(state["mode"], MODE_SYSTEM_PROMPTS["chat"])
        openai_messages = [{"role": "system", "content": system_prompt}]
        for m in state["messages"]:
            openai_messages.append(_to_openai_message(m))

        response = await client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=openai_messages,
            tools=_tools_openai_format(),
            tool_choice="auto",
            temperature=0.2,
        )
        choice = response.choices[0].message
        new_message = {
            "role": "assistant",
            "content": choice.content or "",
        }
        if choice.tool_calls:
            new_message["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in choice.tool_calls
            ]
        return {
            "messages": [new_message],
            "mode": state["mode"],
            "iterations": state["iterations"] + 1,
        }

    return agent_step


def _to_openai_message(m: dict) -> dict:
    # State holds raw OpenAI-format dicts (see AgentState); the object branch
    # below is only a defensive fallback.
    if isinstance(m, dict):
        return m
    role = getattr(m, "type", "user")
    role_map = {"human": "user", "ai": "assistant", "tool": "tool", "system": "system"}
    return {"role": role_map.get(role, "user"), "content": getattr(m, "content", "")}


def build_tool_step(tool_ctx: RepoToolContext):
    async def tool_step(state: AgentState) -> AgentState:
        last = state["messages"][-1]
        tool_calls = last.get("tool_calls", []) if isinstance(last, dict) else []
        results = []
        for call in tool_calls:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                result = await tool_ctx.dispatch(name, args)
            except Exception as exc:  # noqa: BLE001
                result = f"ERROR calling {name}: {exc}"
            results.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result)[:8000],
                }
            )
        return {"messages": results, "mode": state["mode"], "iterations": state["iterations"]}

    return tool_step


def _should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    has_tool_calls = isinstance(last, dict) and bool(last.get("tool_calls"))
    if has_tool_calls and state["iterations"] < MAX_TOOL_ITERATIONS:
        return "tools"
    return END


async def build_graph(tool_ctx: RepoToolContext):
    agent_step = await build_agent_step(tool_ctx)
    tool_step = build_tool_step(tool_ctx)

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_step)
    graph.add_node("tools", tool_step)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", _should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


async def run_agent_context_gathering(
    tool_ctx: RepoToolContext,
    mode: str,
    history: List[dict],
    user_message: str,
) -> List[dict]:
    """Runs the bounded tool-calling loop and returns the full message
    history (including tool calls/results) for the final streaming call
    to consume as context."""
    app_graph = await build_graph(tool_ctx)
    messages = list(history) + [{"role": "user", "content": user_message}]
    result = await app_graph.ainvoke({"messages": messages, "mode": mode, "iterations": 0})
    return [_to_openai_message(m) for m in result["messages"]]
