"""Heading-aware markdown chunking. Splits on headings, then packs to a
target token budget with overlap, and prepends the heading path to each
chunk's text before embedding - a cheap trick that materially helps
retrieval, since "## Refund timelines" carries real signal on its own.

Token counts are approximated by whitespace word count (roughly 0.75 tokens
per word for English) rather than a real tokenizer - good enough to size
chunks sensibly, not worth a tokenizer dependency for KB documents this
short (the seed set is FAQ/policy paragraphs, not manuals).
"""

import re
from dataclasses import dataclass

TARGET_TOKENS = 400
OVERLAP_TOKENS = 60
_WORDS_PER_TOKEN = 0.75  # approximation; see module docstring

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


@dataclass
class Chunk:
    heading_path: str | None
    content: str
    token_count: int


def _approx_tokens(text: str) -> int:
    return max(1, round(len(text.split()) / _WORDS_PER_TOKEN))


def _split_by_heading(markdown: str) -> list[tuple[str | None, str]]:
    """Returns [(heading_path, section_body), ...]. Nested headings build a
    '>' joined path, e.g. 'Refunds > Timelines'.
    """
    matches = list(HEADING_RE.finditer(markdown))
    if not matches:
        return [(None, markdown.strip())] if markdown.strip() else []

    sections: list[tuple[str | None, str]] = []
    path_stack: list[tuple[int, str]] = []  # (level, title)

    for i, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()

        while path_stack and path_stack[-1][0] >= level:
            path_stack.pop()
        path_stack.append((level, title))
        heading_path = " > ".join(t for _, t in path_stack)

        if body:
            sections.append((heading_path, body))

    return sections


def _pack_section(heading_path: str | None, body: str) -> list[Chunk]:
    """Pack one section's body into token-budgeted chunks with overlap."""
    words = body.split()
    if not words:
        return []

    target_words = round(TARGET_TOKENS * _WORDS_PER_TOKEN)
    overlap_words = round(OVERLAP_TOKENS * _WORDS_PER_TOKEN)

    if len(words) <= target_words:
        text = body.strip()
        prefixed = f"{heading_path}\n{text}" if heading_path else text
        return [Chunk(heading_path, prefixed, _approx_tokens(prefixed))]

    chunks: list[Chunk] = []
    start = 0
    while start < len(words):
        end = min(start + target_words, len(words))
        piece = " ".join(words[start:end])
        prefixed = f"{heading_path}\n{piece}" if heading_path else piece
        chunks.append(Chunk(heading_path, prefixed, _approx_tokens(prefixed)))
        if end == len(words):
            break
        start = end - overlap_words
    return chunks


def chunk_markdown(markdown: str) -> list[Chunk]:
    """Markdown document -> heading-aware, token-budgeted chunks."""
    chunks: list[Chunk] = []
    for heading_path, body in _split_by_heading(markdown):
        chunks.extend(_pack_section(heading_path, body))
    return chunks
