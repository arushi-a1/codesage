"""Semantic code chunking with Tree-sitter.

Naive fixed-window chunking splits functions/classes across chunk
boundaries, which hurts retrieval quality. Instead we parse each file
with the language-appropriate Tree-sitter grammar and cut chunks at
top-level "definition" node boundaries (functions, methods, classes,
interfaces), falling back to line-window chunking for files/languages
we can't parse (config files, markdown, unsupported languages).

Each chunk carries the metadata RAG needs to cite sources: file path,
language, start/end line, and a symbol name when available.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from tree_sitter_languages import get_parser

# Maps file extension -> tree-sitter grammar name
EXTENSION_LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "c_sharp",
}

# Node types that represent a "definition" worth being its own chunk,
# per language. Anything not matched falls back to line-window chunking.
DEFINITION_NODE_TYPES = {
    "python": {"function_definition", "class_definition", "decorated_definition"},
    "javascript": {
        "function_declaration", "class_declaration", "method_definition",
        "lexical_declaration",  # covers `const foo = () => {}` at top level
    },
    "typescript": {
        "function_declaration", "class_declaration", "method_definition",
        "interface_declaration", "lexical_declaration",
    },
    "tsx": {
        "function_declaration", "class_declaration", "method_definition",
        "interface_declaration", "lexical_declaration",
    },
    "go": {"function_declaration", "method_declaration", "type_declaration"},
    "java": {"method_declaration", "class_declaration", "interface_declaration"},
    "ruby": {"method", "class", "module"},
    "rust": {"function_item", "impl_item", "struct_item", "trait_item"},
    "c": {"function_definition", "struct_specifier"},
    "cpp": {"function_definition", "class_specifier", "struct_specifier"},
    "c_sharp": {"method_declaration", "class_declaration", "interface_declaration"},
}

NAME_FIELD_CANDIDATES = ("name", "identifier")

FALLBACK_WINDOW_LINES = 60
FALLBACK_OVERLAP_LINES = 10
MAX_CHUNK_CHARS = 4000  # ~ soft cap; very large single definitions get sub-split


@dataclass
class CodeChunk:
    path: str
    language: str
    start_line: int  # 1-indexed, inclusive
    end_line: int  # 1-indexed, inclusive
    text: str
    symbol: Optional[str] = None
    kind: str = "block"  # "definition" | "block"
    metadata: dict = field(default_factory=dict)


def detect_language(path: str) -> Optional[str]:
    return EXTENSION_LANGUAGE_MAP.get(Path(path).suffix.lower())


def _extract_name(node, source: bytes) -> Optional[str]:
    for field_name in NAME_FIELD_CANDIDATES:
        child = node.child_by_field_name(field_name)
        if child is not None:
            return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
    return None


def _split_large_text(text: str, max_chars: int) -> List[str]:
    if len(text) <= max_chars:
        return [text]
    lines = text.splitlines(keepends=True)
    parts, current = [], ""
    for line in lines:
        if len(current) + len(line) > max_chars and current:
            parts.append(current)
            current = ""
        current += line
    if current:
        parts.append(current)
    return parts


def chunk_source(path: str, source: str) -> List[CodeChunk]:
    """Chunk a single file's source text into CodeChunks."""
    language = detect_language(path)
    if language is None:
        return _chunk_by_lines(path, source, language="text")

    try:
        parser = get_parser(language)
        tree = parser.parse(source.encode("utf-8"))
    except Exception:
        # Grammar not available or parse failure -> safe fallback
        return _chunk_by_lines(path, source, language=language)

    def_types = DEFINITION_NODE_TYPES.get(language, set())
    src_bytes = source.encode("utf-8")
    chunks: List[CodeChunk] = []

    def walk(node, depth: int):
        # Only look at top-level and one-nested-level definitions to avoid
        # chunk explosion from e.g. every nested closure.
        if node.type in def_types and depth <= 2:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            text = src_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            name = _extract_name(node, src_bytes)
            for i, part in enumerate(_split_large_text(text, MAX_CHUNK_CHARS)):
                chunks.append(
                    CodeChunk(
                        path=path,
                        language=language,
                        start_line=start_line,
                        end_line=end_line,
                        text=part,
                        symbol=name,
                        kind="definition",
                    )
                )
            return  # don't descend further into this definition
        for child in node.children:
            walk(child, depth + 1)

    walk(tree.root_node, 0)

    if not chunks:
        return _chunk_by_lines(path, source, language=language)

    # Also capture module-level code that isn't inside any definition
    # (imports, constants, top-of-file docstrings) as one leading chunk,
    # since that's often relevant context (e.g. "what does this module do").
    covered_lines = {ln for c in chunks for ln in range(c.start_line, c.end_line + 1)}
    lines = source.splitlines()
    leading = []
    for i, line in enumerate(lines, start=1):
        if i not in covered_lines and line.strip():
            leading.append((i, line))
        if len(leading) > FALLBACK_WINDOW_LINES:
            break
    if leading:
        start = leading[0][0]
        end = leading[-1][0]
        text = "\n".join(l for _, l in leading)
        chunks.insert(
            0,
            CodeChunk(
                path=path, language=language, start_line=start, end_line=end,
                text=text, symbol=None, kind="module_level",
            ),
        )

    return chunks


def _chunk_by_lines(path: str, source: str, language: str) -> List[CodeChunk]:
    lines = source.splitlines()
    if not lines:
        return []
    chunks = []
    step = FALLBACK_WINDOW_LINES - FALLBACK_OVERLAP_LINES
    i = 0
    while i < len(lines):
        window = lines[i:i + FALLBACK_WINDOW_LINES]
        if not window:
            break
        text = "\n".join(window)
        if text.strip():
            chunks.append(
                CodeChunk(
                    path=path,
                    language=language,
                    start_line=i + 1,
                    end_line=min(i + FALLBACK_WINDOW_LINES, len(lines)),
                    text=text,
                    symbol=None,
                    kind="block",
                )
            )
        i += step
    return chunks
