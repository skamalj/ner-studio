"""Health, provider catalog and summary-type endpoints."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query

from ..config import get_settings
from ..prompts import SUMMARY_TYPE_LABELS
from ..providers import provider_catalog, refresh_catalog
from ..schemas import ProviderOut, SummaryTypeOut

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "aws_region": settings.aws_region,
        "default_provider": settings.default_provider,
        "chunk_token_limit": settings.chunk_token_limit,
    }


@router.get("/models", response_model=list[ProviderOut])
def models(refresh: bool = Query(False, description="Re-query provider list APIs")):
    infos = refresh_catalog() if refresh else provider_catalog()
    return [asdict(info) for info in infos]


@router.get("/summary-types", response_model=list[SummaryTypeOut])
def summary_types():
    return [{"id": key, "label": label} for key, label in SUMMARY_TYPE_LABELS]
