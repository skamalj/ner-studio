"""Shared state pieces and helpers for the LangGraph pipelines."""
from __future__ import annotations

import base64
import operator
import time
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

from ..providers import build_chat_model


class LogEntry(TypedDict, total=False):
    node: str
    message: str
    detail: str
    ts: float


def log_entry(node: str, message: str, detail: str = "") -> list[LogEntry]:
    return [{"node": node, "message": message, "detail": detail, "ts": time.time()}]


class ModelConfig(TypedDict, total=False):
    provider: str
    model: str
    temperature: float


class Usage(TypedDict, total=False):
    input_tokens: int
    output_tokens: int
    calls: int


def merge_usage(left: Usage, right: Usage) -> Usage:
    return {
        "input_tokens": left.get("input_tokens", 0) + right.get("input_tokens", 0),
        "output_tokens": left.get("output_tokens", 0) + right.get("output_tokens", 0),
        "calls": left.get("calls", 0) + right.get("calls", 0),
    }


def describe_usage(usage: Usage) -> str:
    """Human-readable token counts for a single model call."""
    total = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    if not total:
        return "token usage not reported by provider"
    return f"{usage.get('input_tokens', 0)} in / {usage.get('output_tokens', 0)} out"


LogList = Annotated[list[LogEntry], operator.add]
UsageTotal = Annotated[Usage, merge_usage]


MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


async def call_vision_model(
    system_prompt: str | None,
    user_prompt: str,
    image: bytes,
    suffix: str,
    provider: str,
    model: str | None,
    temperature: float,
) -> tuple[str, Usage]:
    """Invoke a chat model with an image plus a prompt, in one call.

    The image goes to the model as-is; no OCR happens anywhere in this path.
    """
    mime = MIME_BY_SUFFIX.get(suffix)
    if mime is None:
        raise ValueError(
            f"Cannot send {suffix or 'this file'} to a vision model. "
            f"Supported: {', '.join(sorted(MIME_BY_SUFFIX))}."
        )
    block = {
        "type": "image",
        "source_type": "base64",
        "data": base64.b64encode(image).decode("ascii"),
        "mime_type": mime,
    }
    llm = build_chat_model(provider, model, temperature)
    messages = [HumanMessage(content=[block, {"type": "text", "text": user_prompt}])]
    if system_prompt:
        messages.insert(0, SystemMessage(content=system_prompt))
    response = await llm.ainvoke(messages)
    return _text_and_usage(response)


async def call_model(
    system_prompt: str,
    user_prompt: str,
    provider: str,
    model: str | None,
    temperature: float,
) -> tuple[str, Usage]:
    """Invoke a chat model once and return its text plus token usage."""
    llm = build_chat_model(provider, model, temperature)
    response = await llm.ainvoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    )
    return _text_and_usage(response)


def _text_and_usage(response) -> tuple[str, Usage]:
    content = response.content
    if isinstance(content, list):  # some providers return content blocks
        content = "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    meta = getattr(response, "usage_metadata", None) or {}
    usage: Usage = {
        "input_tokens": meta.get("input_tokens", 0),
        "output_tokens": meta.get("output_tokens", 0),
        "calls": 1,
    }
    return (content or "").strip(), usage
