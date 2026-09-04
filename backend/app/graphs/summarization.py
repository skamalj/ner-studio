"""Progressive (map/reduce) summarization pipeline.

    split -> (fan out) summarize_chunk* -> collect -> split | END

This preserves the original recursion: while the text does not fit in a single
model call it is chunked, every chunk is summarized in parallel, the partial
summaries are joined, and the joined text is summarized again. The loop ends
with one final pass over text that fits in a single call.
"""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from ..prompts import SUMMARIZER_SYSTEM_PROMPT, summary_prompt
from ..services.chunking import count_tokens, split_text
from .common import LogList, UsageTotal, call_model, describe_usage, log_entry

NODE_SPLIT = "split"
NODE_SUMMARIZE = "summarize_chunk"
NODE_COLLECT = "collect"

MAX_PASSES = 4


class PartialSummary(TypedDict, total=False):
    pass_index: int
    index: int
    text: str
    error: str


class SummarizationState(TypedDict, total=False):
    # inputs
    document: str
    summary_type: str
    provider: str
    model: str
    temperature: float
    # working state
    chunks: list[str]
    pass_index: int
    partials: Annotated[list[PartialSummary], operator.add]
    # outputs
    summary: str
    passes: int
    log: LogList
    usage: UsageTotal


class SummaryTask(TypedDict):
    pass_index: int
    index: int
    total: int
    chunk: str
    summary_type: str
    provider: str
    model: str
    temperature: float


async def split(state: SummarizationState) -> dict:
    document = state.get("document", "")
    chunks = split_text(document)
    pass_index = state.get("pass_index", 0)
    return {
        "chunks": chunks,
        "pass_index": pass_index,
        "log": log_entry(
            NODE_SPLIT,
            f"Pass {pass_index + 1}: {len(chunks)} chunk(s)",
            detail=f"{count_tokens(document)} tokens",
        ),
    }


def fan_out(state: SummarizationState) -> list[Send] | str:
    chunks = state.get("chunks") or []
    if not chunks:
        return NODE_COLLECT
    total = len(chunks)
    return [
        Send(
            NODE_SUMMARIZE,
            SummaryTask(
                pass_index=state.get("pass_index", 0),
                index=i,
                total=total,
                chunk=chunk,
                summary_type=state["summary_type"],
                provider=state["provider"],
                model=state.get("model", ""),
                temperature=state.get("temperature", 0.7),
            ),
        )
        for i, chunk in enumerate(chunks)
    ]


async def summarize_chunk(task: SummaryTask) -> dict:
    index, total = task["index"], task["total"]
    try:
        text, usage = await call_model(
            SUMMARIZER_SYSTEM_PROMPT,
            summary_prompt(task["summary_type"], task["chunk"]),
            task["provider"],
            task.get("model") or None,
            task.get("temperature", 0.7),
        )
    except Exception as exc:
        return {
            "partials": [
                PartialSummary(
                    pass_index=task["pass_index"], index=index, text="", error=str(exc)
                )
            ],
            "log": log_entry(
                NODE_SUMMARIZE, f"Chunk {index + 1}/{total} failed", detail=str(exc)
            ),
        }
    return {
        "partials": [
            PartialSummary(pass_index=task["pass_index"], index=index, text=text)
        ],
        "usage": usage,
        "log": log_entry(
            NODE_SUMMARIZE,
            f"Summarized chunk {index + 1}/{total}",
            detail=f"{len(text)} characters - {describe_usage(usage)}",
        ),
    }


async def collect(state: SummarizationState) -> dict:
    pass_index = state.get("pass_index", 0)
    current = sorted(
        (p for p in state.get("partials") or [] if p.get("pass_index") == pass_index),
        key=lambda p: p.get("index", 0),
    )
    good = [p for p in current if not p.get("error")]
    if not good:
        errors = "; ".join(p.get("error", "") for p in current) or "nothing to summarize"
        raise RuntimeError(f"Summarization failed: {errors}")

    joined = " ".join(p.get("text", "") for p in good).strip()
    single = len(state.get("chunks") or []) <= 1
    exhausted = pass_index + 1 >= MAX_PASSES

    if single or exhausted:
        return {
            "summary": joined,
            "passes": pass_index + 1,
            "log": log_entry(
                NODE_COLLECT,
                "Final summary ready"
                if single
                else f"Stopped after {MAX_PASSES} passes",
            ),
        }
    return {
        "document": joined,
        "pass_index": pass_index + 1,
        "passes": pass_index + 1,
        "log": log_entry(
            NODE_COLLECT,
            f"Merged {len(good)} partial summaries; running another pass",
            detail=f"{count_tokens(joined)} tokens",
        ),
    }


def should_continue(state: SummarizationState) -> str:
    return END if state.get("summary") else NODE_SPLIT


def build_summarization_graph():
    graph = StateGraph(SummarizationState)
    graph.add_node(NODE_SPLIT, split)
    graph.add_node(NODE_SUMMARIZE, summarize_chunk)
    graph.add_node(NODE_COLLECT, collect)
    graph.add_edge(START, NODE_SPLIT)
    graph.add_conditional_edges(NODE_SPLIT, fan_out, [NODE_SUMMARIZE, NODE_COLLECT])
    graph.add_edge(NODE_SUMMARIZE, NODE_COLLECT)
    graph.add_conditional_edges(NODE_COLLECT, should_continue, [NODE_SPLIT, END])
    return graph.compile()


summarization_graph = build_summarization_graph()
