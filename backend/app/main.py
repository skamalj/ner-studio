"""FastAPI application entry point."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import analysis, documents, meta, templates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = get_settings()

app = FastAPI(
    title="NER Studio API",
    version="0.1.0",
    description=(
        "Upload a document or image, OCR it with AWS Textract, then run "
        "template-driven entity extraction or summarization through LangGraph "
        "against Bedrock, Anthropic, OpenAI or Gemini."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router, prefix="/api")
app.include_router(templates.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(analysis.router, prefix="/api")


@app.get("/")
def root() -> dict:
    return {"service": "ner-studio", "docs": "/docs", "api": "/api"}
