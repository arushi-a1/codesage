from app.services.indexing.chunker import chunk_source, detect_language

PY_SOURCE = '''\
import os

CONSTANT = 42


def add(a, b):
    """Add two numbers."""
    return a + b


class Calculator:
    def __init__(self):
        self.value = 0

    def add(self, x):
        self.value += x
        return self.value
'''

JS_SOURCE = """\
const API_URL = "https://example.com";

function fetchData(id) {
  return fetch(`${API_URL}/${id}`);
}

class Widget {
  render() {
    return "<div></div>";
  }
}
"""


def test_detect_language_by_extension():
    assert detect_language("app/main.py") == "python"
    assert detect_language("src/index.ts") == "typescript"
    assert detect_language("README.md") is None


def test_python_chunking_splits_function_and_class():
    chunks = chunk_source("calc.py", PY_SOURCE)
    symbols = {c.symbol for c in chunks if c.symbol}
    assert "add" in symbols
    assert "Calculator" in symbols
    # Each chunk should carry accurate line ranges
    for c in chunks:
        assert c.start_line >= 1
        assert c.end_line >= c.start_line
        assert c.path == "calc.py"
        assert c.language == "python"


def test_python_definition_chunk_contains_its_own_body():
    chunks = chunk_source("calc.py", PY_SOURCE)
    add_chunk = next(c for c in chunks if c.symbol == "add" and c.kind == "definition")
    assert "return a + b" in add_chunk.text


def test_javascript_chunking_finds_function_and_class():
    chunks = chunk_source("widget.js", JS_SOURCE)
    symbols = {c.symbol for c in chunks if c.symbol}
    assert "fetchData" in symbols
    assert "Widget" in symbols


def test_unknown_extension_falls_back_to_line_windows():
    text = "\n".join(f"line {i}" for i in range(150))
    chunks = chunk_source("notes.txt", text)
    assert len(chunks) > 1
    assert all(c.language == "text" for c in chunks)
    # Windows should be contiguous and cover the whole file
    assert chunks[0].start_line == 1
    assert chunks[-1].end_line == 150


def test_empty_file_produces_no_chunks():
    assert chunk_source("empty.py", "") == []
    assert chunk_source("empty.py", "   \n\n  ") == []


def test_unparsable_source_falls_back_gracefully():
    # Malformed syntax shouldn't crash the chunker; tree-sitter still
    # produces a (partial) tree, and worst case we fall back to line windows.
    chunks = chunk_source("broken.py", "def f(:\n    pass\n" * 3)
    assert isinstance(chunks, list)
