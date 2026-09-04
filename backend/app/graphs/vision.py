"""Vision pipeline: the image itself goes to the model, with no OCR step.

    look -> END

There is nothing to chunk - a page is one image - so this is a single node.
It stays a graph so the vision flow streams progress and reports token usage
through exactly the same machinery as the text pipelines.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from ..prompts import EXTRACTOR_SYSTEM_PROMPT
from ..services.jsonparse import parse_json_object
from .common import LogList, UsageTotal, call_vision_model, describe_usage, log_entry

NODE_LOOK = "look"


class VisionState(TypedDict, total=False):
    # inputs
    image: bytes
    suffix: str
    filename: str
    prompt: str
    provider: str
    model: str
    temperature: float
    # outputs
    raw: str
    data: object
    log: LogList
    usage: UsageTotal


async def look(state: VisionState) -> dict:
    image = state.get("image") or b""
    raw, usage = await call_vision_model(
        EXTRACTOR_SYSTEM_PROMPT,
        state["prompt"],
        image,
        state.get("suffix", ""),
        state["provider"],
        state.get("model") or None,
        state.get("temperature", 0.2),
    )
    parsed = parse_json_object(raw)
    return {
        "raw": raw,
        "data": parsed,
        "usage": usage,
        "log": log_entry(
            NODE_LOOK,
            f"Sent {state.get('filename') or 'image'} ({len(image) / 1024:.0f} KB) "
            "straight to the model",
            detail=(
                f"{'valid JSON' if parsed is not None else 'no JSON found in response'}"
                f" - {describe_usage(usage)}"
            ),
        ),
    }


def build_vision_graph():
    graph = StateGraph(VisionState)
    graph.add_node(NODE_LOOK, look)
    graph.add_edge(START, NODE_LOOK)
    graph.add_edge(NODE_LOOK, END)
    return graph.compile()


vision_graph = build_vision_graph()
