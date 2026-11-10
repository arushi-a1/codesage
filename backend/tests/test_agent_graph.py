"""Tests for the LangGraph tool-calling loop.

Regression coverage: the graph state used langgraph's `add_messages`
reducer, which converted message dicts into LangChain objects, so the
`isinstance(last, dict)` checks never matched and tool calls were never
executed. These tests drive the graph with a fake OpenAI client and assert
the tools actually run.
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.agents.graph import MAX_TOOL_ITERATIONS, run_agent_context_gathering


def _tool_call_response(call_id: str, name: str, args: dict):
    tc = SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(args)))
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[tc]))])


def _text_response(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=None))])


def _fake_client(responses):
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=responses))))
    return client


class FakeToolContext:
    def __init__(self):
        self.calls = []

    async def dispatch(self, name, arguments):
        self.calls.append((name, arguments))
        return [{"path": "worker/processor.py", "text": "def process_event(...)"}]


async def test_agent_executes_tool_calls_then_stops():
    client = _fake_client([
        _tool_call_response("call_1", "search_code", {"query": "idempotency"}),
        _text_response("I have enough context."),
    ])
    tool_ctx = FakeToolContext()

    with patch("app.services.agents.graph.get_openai_client", return_value=client):
        messages = await run_agent_context_gathering(tool_ctx, mode="chat", history=[], user_message="how is idempotency handled?")

    assert tool_ctx.calls == [("search_code", {"query": "idempotency"})]
    roles = [m["role"] for m in messages]
    assert roles == ["user", "assistant", "tool", "assistant"]
    tool_msg = messages[2]
    assert tool_msg["tool_call_id"] == "call_1"
    assert "worker/processor.py" in tool_msg["content"]

    # The second model call must see the tool result, in OpenAI's format.
    second_call_messages = client.chat.completions.create.await_args_list[1].kwargs["messages"]
    assert any(m.get("role") == "tool" and m.get("tool_call_id") == "call_1" for m in second_call_messages)
    assert any(m.get("role") == "assistant" and m.get("tool_calls") for m in second_call_messages)


async def test_agent_tool_loop_is_bounded():
    responses = [_tool_call_response(f"call_{i}", "list_directory", {"path": ""}) for i in range(MAX_TOOL_ITERATIONS + 3)]
    client = _fake_client(responses)
    tool_ctx = FakeToolContext()

    with patch("app.services.agents.graph.get_openai_client", return_value=client):
        await run_agent_context_gathering(tool_ctx, mode="chat", history=[], user_message="explore")

    assert client.chat.completions.create.await_count == MAX_TOOL_ITERATIONS
    assert len(tool_ctx.calls) == MAX_TOOL_ITERATIONS - 1
