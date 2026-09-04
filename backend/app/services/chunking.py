"""Token-aware chunking.

The original code sliced the document into equal character ranges once the
gpt-3.5 encoder reported more than ~10k tokens. This keeps the same budget but
splits on paragraph / sentence boundaries so a chunk never cuts a line in half.
"""
from __future__ import annotations

import re
from functools import lru_cache

from ..config import get_settings


@lru_cache(maxsize=4)
def _encoder(model: str):
    import tiktoken

    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str | None = None) -> int:
    model = model or get_settings().tokenizer_model
    return len(_encoder(model).encode(text))


def normalize(text: str) -> str:
    """Collapse runs of whitespace, as the original summarizer did."""
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text or "")).strip()


def _split_units(text: str) -> tuple[list[str], str]:
    """Paragraphs, falling back to lines, sentences, then words.

    Returns the units and the separator they should be rejoined with, so a
    chunk reads like the original text rather than a reflowed version of it.
    """
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) > 1:
        return paragraphs, "\n\n"
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if len(lines) > 1:
        return lines, "\n"
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(sentences) > 1:
        return sentences, " "
    return text.split(" "), " "


def split_text(text: str, token_limit: int | None = None, model: str | None = None) -> list[str]:
    """Split ``text`` into chunks that each fit inside ``token_limit`` tokens."""
    settings = get_settings()
    token_limit = token_limit or settings.chunk_token_limit
    model = model or settings.tokenizer_model
    text = normalize(text)
    if not text:
        return []
    if count_tokens(text, model) <= token_limit:
        return [text]

    units, separator = _split_units(text)
    separator_tokens = count_tokens(separator, model)

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for unit in units:
        unit_tokens = count_tokens(unit, model)
        if unit_tokens > token_limit:
            # A single oversized unit: fall back to a hard token-slice.
            if current:
                chunks.append(separator.join(current))
                current, current_tokens = [], 0
            chunks.extend(_hard_split(unit, token_limit, model))
            continue
        # The separator itself costs tokens once a chunk holds more than one unit.
        cost = unit_tokens + (separator_tokens if current else 0)
        if current_tokens + cost > token_limit and current:
            chunks.append(separator.join(current))
            current, current_tokens = [], 0
            cost = unit_tokens
        current.append(unit)
        current_tokens += cost
    if current:
        chunks.append(separator.join(current))
    return chunks


def _hard_split(text: str, token_limit: int, model: str) -> list[str]:
    encoder = _encoder(model)
    tokens = encoder.encode(text)
    return [
        encoder.decode(tokens[i : i + token_limit])
        for i in range(0, len(tokens), token_limit)
    ]
