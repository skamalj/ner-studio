"""Application settings, loaded from the environment (.env supported)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT / ".env", BACKEND_ROOT.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- storage -------------------------------------------------------
    # Templates stay flat .txt files, one per template, exactly as the
    # original Flask app stored them.
    templates_dir: Path = BACKEND_ROOT / "templates"
    # Curated Bedrock catalogue: ids, prices and the vision flag no AWS API exposes.
    model_catalog_path: Path = BACKEND_ROOT / "model_catalog.json"
    upload_dir: Path = BACKEND_ROOT / "uploads"

    # --- llm defaults --------------------------------------------------
    default_provider: str = "openai"
    default_model: str = ""
    default_temperature: float = 0.5

    # Chunking budget for a single LLM call. The original code used a
    # 10k-token window with a gpt-3.5 encoder; kept as a tunable.
    chunk_token_limit: int = 10_000
    tokenizer_model: str = "gpt-4o"
    max_parallel_chunks: int = 4

    # --- aws / textract ------------------------------------------------
    aws_region: str = "us-east-1"
    # Optional named profile; exported to the environment so boto3's default
    # credential chain (including an `aws sso login` session) picks it up.
    aws_profile: str = ""

    # Prompt and temperature used when a local vision model acts as the OCR
    # engine. GLM-OCR and friends expect this exact bare instruction.
    ocr_prompt: str = "Text Recognition:"
    ocr_temperature: float = 0.02
    textract_max_bytes: int = 10 * 1024 * 1024  # sync API hard limit

    # --- providers -----------------------------------------------------
    # Any OpenAI-compatible server (llama.cpp, vLLM, Ollama). Set the base URL
    # to enable the "Local" provider; models are read from its /v1/models.
    local_base_url: str = ""
    local_api_key: str = "not-needed"
    # Local servers advertise no capabilities; the usual local model here is an
    # OCR VLM, so assume image input unless told otherwise.
    local_supports_images: bool = True

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""

    # --- http ----------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.templates_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    if settings.aws_profile and not os.environ.get("AWS_PROFILE"):
        os.environ["AWS_PROFILE"] = settings.aws_profile
    os.environ.setdefault("AWS_REGION", settings.aws_region)
    os.environ.setdefault("AWS_DEFAULT_REGION", settings.aws_region)
    return settings
