"""Uploaded-document store.

Each upload gets a short id; the original bytes, the OCR text and a small
metadata record live side by side under ``settings.upload_dir`` so a document
can be OCR'd once and then reused by both the extraction and summarization
flows.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings

_ID = re.compile(r"^[0-9a-f]{12}$")


class DocumentError(ValueError):
    """Raised for an unknown or malformed document id."""


@dataclass
class DocumentRecord:
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


def _dir() -> Path:
    return get_settings().upload_dir


def _check(document_id: str) -> str:
    if not _ID.match(document_id or ""):
        raise DocumentError("Malformed document id")
    return document_id


def save(
    *,
    data: bytes,
    filename: str,
    content_type: str,
    text: str,
    ocr_source: str,
    ocr_mode: str,
    pages: int,
    line_count: int,
) -> DocumentRecord:
    document_id = uuid.uuid4().hex[:12]
    suffix = Path(filename).suffix.lower()[:10]
    (_dir() / f"{document_id}{suffix}").write_bytes(data)
    (_dir() / f"{document_id}.text").write_text(text, encoding="utf-8")
    record = DocumentRecord(
        id=document_id,
        filename=filename,
        content_type=content_type,
        size=len(data),
        ocr_source=ocr_source,
        ocr_mode=ocr_mode,
        pages=pages,
        line_count=line_count,
        created_at=datetime.now(timezone.utc).isoformat(),
        char_count=len(text),
    )
    (_dir() / f"{document_id}.json").write_text(
        json.dumps(asdict(record), indent=2), encoding="utf-8"
    )
    return record


def get_text(document_id: str) -> str:
    path = _dir() / f"{_check(document_id)}.text"
    if not path.exists():
        raise DocumentError(f"Document {document_id!r} not found")
    return path.read_text(encoding="utf-8")


def get_bytes(document_id: str) -> tuple[bytes, str]:
    """The original uploaded file and its suffix (e.g. `.png`)."""
    document_id = _check(document_id)
    for path in _dir().glob(f"{document_id}.*"):
        if path.suffix in {".json", ".text"}:
            continue
        return path.read_bytes(), path.suffix.lower()
    raise DocumentError(f"No stored file for document {document_id!r}")


def get_record(document_id: str) -> DocumentRecord:
    path = _dir() / f"{_check(document_id)}.json"
    if not path.exists():
        raise DocumentError(f"Document {document_id!r} not found")
    return DocumentRecord(**json.loads(path.read_text(encoding="utf-8")))


def list_recent(limit: int = 25) -> list[DocumentRecord]:
    records = []
    for file in sorted(
        _dir().glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True
    )[:limit]:
        try:
            records.append(DocumentRecord(**json.loads(file.read_text(encoding="utf-8"))))
        except (OSError, ValueError, TypeError):
            continue
    return records
