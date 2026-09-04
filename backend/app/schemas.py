"""Request and response models for the HTTP API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .config import get_settings

Provider = Literal["bedrock", "anthropic", "openai", "gemini", "local"]


class ModelSettings(BaseModel):
    provider: Provider = Field(default_factory=lambda: get_settings().default_provider)
    model: str = ""
    temperature: float = Field(default=0.5, ge=0.0, le=2.0)


class ModelOut(BaseModel):
    """A selectable model: what to send, what it costs, what it accepts."""

    id: str
    label: str = ""
    input_per_1m: float | None = None
    output_per_1m: float | None = None
    supports_images: bool = False
    context: int | None = None
    residency: str = ""
    flags: list[str] = []
    note: str = ""


class ProviderOut(BaseModel):
    id: str
    label: str
    configured: bool
    default_model: str
    models: list[ModelOut]
    note: str = ""
    #: ready | not_configured | unreachable
    status: str = "ready"
    #: One line on how to configure or revive this provider.
    setup_hint: str = ""


class SummaryTypeOut(BaseModel):
    id: str
    label: str


class TemplateOut(BaseModel):
    name: str
    definition: str


class TemplateSaveIn(BaseModel):
    name: str
    definition: str


class DocumentOut(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int
    ocr_source: str
    ocr_mode: str
    pages: int
    line_count: int
    created_at: str
    char_count: int


class ExtractTextOut(BaseModel):
    document: DocumentOut
    text: str
    key_values: dict[str, str] = {}
    tables: list[list[list[str]]] = []
    warnings: list[str] = []


class TextSource(ModelSettings):
    """Either a previously uploaded document or raw text."""

    document_id: str | None = None
    text: str | None = None

    @model_validator(mode="after")
    def _one_source(self):
        if not self.document_id and not (self.text or "").strip():
            raise ValueError("Provide either document_id or text")
        return self


class NerIn(TextSource):
    template_name: str | None = None
    template_definition: str | None = None
    temperature: float = Field(default=0.5, ge=0.0, le=2.0)

    @model_validator(mode="after")
    def _one_template(self):
        if not self.template_name and not (self.template_definition or "").strip():
            raise ValueError("Provide either template_name or template_definition")
        return self


class VisionIn(ModelSettings):
    """Send an uploaded image straight to a vision model with a prompt."""

    document_id: str
    prompt: str
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)

    @model_validator(mode="after")
    def _needs_prompt(self):
        if not (self.prompt or "").strip():
            raise ValueError("prompt cannot be empty")
        return self


class SummarizeIn(TextSource):
    summary_type: str = "concise"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class LogEntryOut(BaseModel):
    node: str
    message: str
    detail: str = ""
    ts: float = 0.0


class UsageOut(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0


class NerOut(BaseModel):
    data: Any = None
    raw: str = ""
    chunks: int = 0
    instruction: str = ""
    provider: str
    model: str
    elapsed_ms: int = 0
    usage: UsageOut = UsageOut()
    log: list[LogEntryOut] = []


class SummarizeOut(BaseModel):
    summary: str = ""
    summary_type: str
    chunks: int = 0
    passes: int = 1
    provider: str
    model: str
    elapsed_ms: int = 0
    usage: UsageOut = UsageOut()
    log: list[LogEntryOut] = []
