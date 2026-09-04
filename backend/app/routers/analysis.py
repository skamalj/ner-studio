"""Entity extraction and summarization endpoints (LangGraph pipelines).

Both flows come in two shapes: a plain JSON endpoint that returns the finished
result, and an SSE endpoint that streams each graph node's progress as it runs
before emitting the same result.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from .. import store
from ..graphs.extraction import extraction_graph
from ..graphs.summarization import summarization_graph
from ..graphs.vision import vision_graph
from ..prompts import SUMMARY_TYPES, entity_prompt
from ..providers import ProviderError, default_model_for
from ..schemas import NerIn, NerOut, SummarizeIn, SummarizeOut, VisionIn
from ..services import documents

router = APIRouter(tags=["analysis"])


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _resolve_text(payload: NerIn | SummarizeIn) -> str:
    if payload.document_id:
        try:
            text = documents.get_text(payload.document_id)
        except documents.DocumentError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    else:
        text = payload.text or ""
    if not text.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "The document contains no text to analyse"
        )
    return text


def _resolve_instruction(payload: NerIn) -> str:
    definition = payload.template_definition
    if not (definition or "").strip():
        try:
            definition = store.get_template(payload.template_name or "")
        except store.TemplateError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return entity_prompt(definition or "")


def _resolve_model(provider: str, model: str) -> str:
    return model or default_model_for(provider)


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _stream(graph, state: dict, build_result: Callable[[dict, int], dict]):
    started = time.perf_counter()

    async def generator():
        emitted = 0
        final: dict = {}
        try:
            async for snapshot in graph.astream(state, stream_mode="values"):
                final = snapshot
                entries = snapshot.get("log") or []
                for entry in entries[emitted:]:
                    yield _sse("log", entry)
                emitted = len(entries)
            elapsed = int((time.perf_counter() - started) * 1000)
            yield _sse("result", build_result(final, elapsed))
        except ProviderError as exc:
            yield _sse("error", {"message": str(exc)})
        except Exception as exc:  # surface graph failures to the UI
            yield _sse("error", {"message": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------
# entity extraction
# --------------------------------------------------------------------------
def _ner_state(payload: NerIn) -> tuple[dict, str, str]:
    text = _resolve_text(payload)
    instruction = _resolve_instruction(payload)
    model = _resolve_model(payload.provider, payload.model)
    state = {
        "text": text,
        "instruction": instruction,
        "provider": payload.provider,
        "model": model,
        "temperature": payload.temperature,
    }
    return state, instruction, model


def _ner_result(payload: NerIn, instruction: str, model: str):
    def build(final: dict, elapsed_ms: int) -> dict:
        return NerOut(
            data=final.get("data"),
            raw=final.get("raw", ""),
            chunks=len(final.get("chunks") or []),
            instruction=instruction,
            provider=payload.provider,
            model=model,
            elapsed_ms=elapsed_ms,
            usage=final.get("usage") or {},
            log=final.get("log") or [],
        ).model_dump()

    return build


@router.post("/ner", response_model=NerOut)
async def run_ner(payload: NerIn) -> NerOut:
    state, instruction, model = _ner_state(payload)
    started = time.perf_counter()
    try:
        final = await extraction_graph.ainvoke(state)
    except ProviderError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    elapsed = int((time.perf_counter() - started) * 1000)
    return NerOut(**_ner_result(payload, instruction, model)(final, elapsed))


@router.post("/ner/stream")
async def run_ner_stream(payload: NerIn):
    state, instruction, model = _ner_state(payload)
    return _stream(extraction_graph, state, _ner_result(payload, instruction, model))


# --------------------------------------------------------------------------
# vision - the image goes to the model, no OCR
# --------------------------------------------------------------------------
def _vision_state(payload: VisionIn) -> tuple[dict, str]:
    try:
        image, suffix = documents.get_bytes(payload.document_id)
        record = documents.get_record(payload.document_id)
    except documents.DocumentError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    model = _resolve_model(payload.provider, payload.model)
    state = {
        "image": image,
        "suffix": suffix,
        "filename": record.filename,
        "prompt": payload.prompt,
        "provider": payload.provider,
        "model": model,
        "temperature": payload.temperature,
    }
    return state, model


def _vision_result(payload: VisionIn, model: str):
    def build(final: dict, elapsed_ms: int) -> dict:
        return NerOut(
            data=final.get("data"),
            raw=final.get("raw", ""),
            chunks=1,
            instruction=payload.prompt,
            provider=payload.provider,
            model=model,
            elapsed_ms=elapsed_ms,
            usage=final.get("usage") or {},
            log=final.get("log") or [],
        ).model_dump()

    return build


@router.post("/vision", response_model=NerOut)
async def run_vision(payload: VisionIn) -> NerOut:
    state, model = _vision_state(payload)
    started = time.perf_counter()
    try:
        final = await vision_graph.ainvoke(state)
    except ProviderError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ValueError as exc:  # unsupported image type
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    elapsed = int((time.perf_counter() - started) * 1000)
    return NerOut(**_vision_result(payload, model)(final, elapsed))


@router.post("/vision/stream")
async def run_vision_stream(payload: VisionIn):
    state, model = _vision_state(payload)
    return _stream(vision_graph, state, _vision_result(payload, model))


# --------------------------------------------------------------------------
# summarization
# --------------------------------------------------------------------------
def _summarize_state(payload: SummarizeIn) -> tuple[dict, str]:
    if payload.summary_type not in SUMMARY_TYPES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown summary type '{payload.summary_type}'",
        )
    text = _resolve_text(payload)
    model = _resolve_model(payload.provider, payload.model)
    state = {
        "document": text,
        "summary_type": payload.summary_type,
        "provider": payload.provider,
        "model": model,
        "temperature": payload.temperature,
        "pass_index": 0,
    }
    return state, model


def _summary_result(payload: SummarizeIn, model: str):
    def build(final: dict, elapsed_ms: int) -> dict:
        return SummarizeOut(
            summary=final.get("summary", ""),
            summary_type=payload.summary_type,
            chunks=len(final.get("chunks") or []),
            passes=final.get("passes", 1),
            provider=payload.provider,
            model=model,
            elapsed_ms=elapsed_ms,
            usage=final.get("usage") or {},
            log=final.get("log") or [],
        ).model_dump()

    return build


@router.post("/summarize", response_model=SummarizeOut)
async def run_summarize(payload: SummarizeIn) -> SummarizeOut:
    state, model = _summarize_state(payload)
    started = time.perf_counter()
    try:
        final = await summarization_graph.ainvoke(state)
    except ProviderError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    elapsed = int((time.perf_counter() - started) * 1000)
    return SummarizeOut(**_summary_result(payload, model)(final, elapsed))


@router.post("/summarize/stream")
async def run_summarize_stream(payload: SummarizeIn):
    state, model = _summarize_state(payload)
    return _stream(summarization_graph, state, _summary_result(payload, model))
