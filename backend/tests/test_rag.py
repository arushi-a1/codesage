from unittest.mock import AsyncMock, patch

import pytest

from app.services.rag.retriever import RetrievedChunk, citations_from_chunks, format_context, retrieve


@patch("app.services.rag.retriever.search", new_callable=AsyncMock)
@patch("app.services.rag.retriever.embed_batch", new_callable=AsyncMock)
async def test_retrieve_embeds_query_and_searches(mock_embed, mock_search):
    mock_embed.return_value = [[0.1, 0.2, 0.3]]
    mock_search.return_value = [
        {
            "path": "app/main.py", "language": "python", "start_line": 1, "end_line": 10,
            "symbol": "main", "kind": "definition", "text": "def main(): ...", "score": 0.87,
        }
    ]

    results = await retrieve("repo_abc", "how does startup work?", top_k=5)

    mock_embed.assert_awaited_once_with(["how does startup work?"])
    mock_search.assert_awaited_once()
    assert len(results) == 1
    assert isinstance(results[0], RetrievedChunk)
    assert results[0].path == "app/main.py"
    assert results[0].symbol == "main"


@patch("app.services.rag.retriever.embed_batch", new_callable=AsyncMock)
async def test_retrieve_returns_empty_when_embedding_fails_to_produce_vectors(mock_embed):
    mock_embed.return_value = []
    results = await retrieve("repo_abc", "anything")
    assert results == []


def test_format_context_includes_path_and_line_range():
    chunks = [
        RetrievedChunk(path="a.py", start_line=1, end_line=5, symbol="foo", text="def foo(): pass", score=0.9),
    ]
    ctx = format_context(chunks)
    assert "a.py (lines 1-5)" in ctx
    assert "foo" in ctx
    assert "def foo(): pass" in ctx


def test_citations_from_chunks_shapes_output():
    chunks = [
        RetrievedChunk(path="a.py", start_line=1, end_line=5, symbol="foo", text="...", score=0.9),
        RetrievedChunk(path="b.py", start_line=10, end_line=20, symbol=None, text="...", score=0.5),
    ]
    citations = citations_from_chunks(chunks)
    assert citations == [
        {"path": "a.py", "start_line": 1, "end_line": 5, "symbol": "foo"},
        {"path": "b.py", "start_line": 10, "end_line": 20, "symbol": None},
    ]
