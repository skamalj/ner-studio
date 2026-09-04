"""Entity-extraction pipeline.

    prepare -> (fan out) extract_chunk* -> merge

`prepare` normalizes the OCR text and splits it into token-sized chunks. Each
chunk is extracted in parallel against the template's field list. `merge`
returns the single extraction unchanged, or asks the model to reconcile the
partial JSON objects into one.
"""
from __future__ import annotations

import json
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from ..prompts import (
    EXTRACTOR_SYSTEM_PROMPT,
    MERGE_EXTRACTIONS_PROMPT,
    extraction_prompt,
)
from ..services.chunking import count_tokens, split_text
from ..services.jsonparse import parse_json_object
from .common import LogList, UsageTotal, call_model, describe_usage, log_entry

NODE_PREPARE = "prepare"
NODE_EXTRACT = "extract_chunk"
NODE_MERGE = "merge"


class Partial(TypedDict, total=False):
    index: int
    raw: str
    data: object
    error: str


class ExtractionState(TypedDict, total=False):
    # inputs
    text: str
    instruction: str
    provider: str
    model: str
    temperature: float
    # working state
    chunks: list[str]
    partials: Annotated[list[Partial], operator.add]
    # outputs
    raw: str
    data: object
    log: LogList
    usage: UsageTotal


class ChunkTask(TypedDict):
    index: int
    total: int
    chunk: str
    instruction: str
    provider: str
    model: str
    temperature: float


async def prepare(state: ExtractionState) -> dict:
    chunks = split_text(state.get("text", ""))
    tokens = count_tokens(state.get("text", "") or "")
    return {
        "chunks": chunks,
        "log": log_entry(
            NODE_PREPARE,
            f"Prepared {len(chunks)} chunk(s) from {tokens} tokens of text",
            detail=f"{len(state.get('text') or '')} characters",
        ),
    }


def fan_out(state: ExtractionState) -> list[Send] | str:
    chunks = state.get("chunks") or []
    if not chunks:
        return NODE_MERGE
    total = len(chunks)
    return [
        Send(
            NODE_EXTRACT,
            ChunkTask(
                index=i,
                total=total,
                chunk=chunk,
                instruction=state["instruction"],
                provider=state["provider"],
                model=state.get("model", ""),
                temperature=state.get("temperature", 0.5),
            ),
        )
        for i, chunk in enumerate(chunks)
    ]


async def extract_chunk(task: ChunkTask) -> dict:
    index, total = task["index"], task["total"]
    try:
        raw, usage = await call_model(
            EXTRACTOR_SYSTEM_PROMPT,
            extraction_prompt(task["instruction"], task["chunk"]),
            task["provider"],
            task.get("model") or None,
            task.get("temperature", 0.5),
        )
    except Exception as exc:
        return {
            "partials": [Partial(index=index, raw="", data=None, error=str(exc))],
            "log": log_entry(
                NODE_EXTRACT, f"Chunk {index + 1}/{total} failed", detail=str(exc)
            ),
        }
    parsed = parse_json_object(raw)
    quality = "valid JSON" if parsed is not None else "no JSON found in response"
    return {
        "partials": [Partial(index=index, raw=raw, data=parsed)],
        "usage": usage,
        "log": log_entry(
            NODE_EXTRACT,
            f"Extracted chunk {index + 1}/{total}",
            detail=f"{quality} - {describe_usage(usage)}",
        ),
    }


async def merge(state: ExtractionState) -> dict:
    partials = sorted(state.get("partials") or [], key=lambda p: p.get("index", 0))
    good = [p for p in partials if not p.get("error")]
    if not good:
        errors = "; ".join(p.get("error", "") for p in partials) or "no text to extract"
        raise RuntimeError(f"Extraction failed: {errors}")

    if len(good) == 1:
        only = good[0]
        return {
            "raw": only.get("raw", ""),
            "data": only.get("data"),
            "log": log_entry(NODE_MERGE, "Single chunk, no merge needed"),
        }

    rendered = "\n\n".join(
        f"--- Part {p['index'] + 1} ---\n"
        + (json.dumps(p["data"], indent=2) if p.get("data") is not None else p.get("raw", ""))
        for p in good
    )
    raw, usage = await call_model(
        EXTRACTOR_SYSTEM_PROMPT,
        MERGE_EXTRACTIONS_PROMPT.format(
            instruction=state["instruction"].strip(), partials=rendered
        ),
        state["provider"],
        state.get("model") or None,
        state.get("temperature", 0.5),
    )
    return {
        "raw": raw,
        "data": parse_json_object(raw),
        "usage": usage,
        "log": log_entry(
            NODE_MERGE,
            f"Merged {len(good)} partial extractions",
            detail=describe_usage(usage),
        ),
    }


def build_extraction_graph():
    graph = StateGraph(ExtractionState)
    graph.add_node(NODE_PREPARE, prepare)
    graph.add_node(NODE_EXTRACT, extract_chunk)
    graph.add_node(NODE_MERGE, merge)
    graph.add_edge(START, NODE_PREPARE)
    graph.add_conditional_edges(NODE_PREPARE, fan_out, [NODE_EXTRACT, NODE_MERGE])
    graph.add_edge(NODE_EXTRACT, NODE_MERGE)
    graph.add_edge(NODE_MERGE, END)
    return graph.compile()


extraction_graph = build_extraction_graph()
