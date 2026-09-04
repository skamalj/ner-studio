"""Synchronous AWS Textract OCR.

Only the synchronous Textract APIs are used, so no S3 bucket is required:

* ``DetectDocumentText`` for plain text.
* ``AnalyzeDocument`` with FORMS + TABLES when the caller wants key/value
  pairs and tables flattened into the text handed to the LLM.

The synchronous APIs accept JPEG, PNG, single-page PDF and single-page TIFF up
to 10 MB. Plain-text uploads bypass Textract entirely.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field

from ..config import get_settings

log = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
PDF_EXTENSIONS = {".pdf"}
TEXT_EXTENSIONS = {".txt", ".md", ".text", ".json", ".csv"}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | PDF_EXTENSIONS | TEXT_EXTENSIONS

TEXT_MODE = "text"
FORMS_MODE = "forms_tables"
# Store the bytes and skip OCR entirely - used by the vision flow, which sends
# the image itself to the model.
RAW_MODE = "raw"


class TextractError(RuntimeError):
    """Raised when a document cannot be OCR'd."""


@dataclass
class OcrResult:
    text: str
    source: str  # "textract" | "plaintext"
    mode: str
    pages: int = 1
    line_count: int = 0
    key_values: dict[str, str] = field(default_factory=dict)
    tables: list[list[list[str]]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _client():
    import boto3

    return boto3.client("textract", region_name=get_settings().aws_region)


def _pdf_page_count(data: bytes) -> int:
    try:
        from pypdf import PdfReader

        return len(PdfReader(io.BytesIO(data)).pages)
    except Exception as exc:
        log.debug("could not read pdf page count: %s", exc)
        return 1


def _lines(blocks: list[dict]) -> list[str]:
    return [b["Text"] for b in blocks if b.get("BlockType") == "LINE" and b.get("Text")]


def _block_index(blocks: list[dict]) -> dict[str, dict]:
    return {b["Id"]: b for b in blocks}


def _child_text(block: dict, index: dict[str, dict]) -> str:
    words: list[str] = []
    for rel in block.get("Relationships", []) or []:
        if rel.get("Type") != "CHILD":
            continue
        for child_id in rel.get("Ids", []):
            child = index.get(child_id, {})
            if child.get("BlockType") == "WORD":
                words.append(child.get("Text", ""))
            elif child.get("BlockType") == "SELECTION_ELEMENT":
                words.append(
                    "[X]" if child.get("SelectionStatus") == "SELECTED" else "[ ]"
                )
    return " ".join(w for w in words if w).strip()


def _key_values(blocks: list[dict]) -> dict[str, str]:
    index = _block_index(blocks)
    pairs: dict[str, str] = {}
    for block in blocks:
        if block.get("BlockType") != "KEY_VALUE_SET":
            continue
        if "KEY" not in (block.get("EntityTypes") or []):
            continue
        key = _child_text(block, index)
        value = ""
        for rel in block.get("Relationships", []) or []:
            if rel.get("Type") == "VALUE":
                for value_id in rel.get("Ids", []):
                    value = _child_text(index.get(value_id, {}), index)
        if key:
            pairs[key] = value
    return pairs


def _tables(blocks: list[dict]) -> list[list[list[str]]]:
    index = _block_index(blocks)
    tables: list[list[list[str]]] = []
    for block in blocks:
        if block.get("BlockType") != "TABLE":
            continue
        cells: dict[tuple[int, int], str] = {}
        rows = cols = 0
        for rel in block.get("Relationships", []) or []:
            if rel.get("Type") != "CHILD":
                continue
            for cell_id in rel.get("Ids", []):
                cell = index.get(cell_id, {})
                if cell.get("BlockType") != "CELL":
                    continue
                r, c = cell.get("RowIndex", 1), cell.get("ColumnIndex", 1)
                rows, cols = max(rows, r), max(cols, c)
                cells[(r, c)] = _child_text(cell, index)
        if rows and cols:
            tables.append(
                [
                    [cells.get((r, c), "") for c in range(1, cols + 1)]
                    for r in range(1, rows + 1)
                ]
            )
    return tables


def _render(lines: list[str], pairs: dict[str, str], tables: list[list[list[str]]]) -> str:
    parts = ["\n".join(lines)]
    if pairs:
        rendered = "\n".join(f"{k}: {v}" for k, v in pairs.items() if k)
        parts.append(f"--- Detected form fields ---\n{rendered}")
    for i, table in enumerate(tables, start=1):
        rendered = "\n".join(" | ".join(cell for cell in row) for row in table)
        parts.append(f"--- Detected table {i} ---\n{rendered}")
    return "\n\n".join(p for p in parts if p.strip())


def extract_text(data: bytes, filename: str, mode: str = TEXT_MODE) -> OcrResult:
    """OCR ``data`` with synchronous Textract and return the flattened text."""
    settings = get_settings()
    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""

    if mode == RAW_MODE:
        return OcrResult(text="", source="none", mode=RAW_MODE)

    if suffix in TEXT_EXTENSIONS:
        return OcrResult(
            text=data.decode("utf-8", errors="replace"),
            source="plaintext",
            mode="none",
            line_count=data.count(b"\n") + 1,
        )

    if suffix not in SUPPORTED_EXTENSIONS:
        raise TextractError(
            f"Unsupported file type {suffix or filename!r}. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}."
        )

    if len(data) > settings.textract_max_bytes:
        raise TextractError(
            f"File is {len(data) / 1e6:.1f} MB; the synchronous Textract API accepts "
            f"up to {settings.textract_max_bytes / 1e6:.0f} MB."
        )

    warnings: list[str] = []
    pages = 1
    if suffix in PDF_EXTENSIONS:
        pages = _pdf_page_count(data)
        if pages > 1:
            raise TextractError(
                f"This PDF has {pages} pages. Synchronous Textract handles single-page "
                "PDFs only -- split the file, or export the page you need as an image."
            )

    document = {"Bytes": data}
    try:
        client = _client()
        if mode == FORMS_MODE:
            response = client.analyze_document(
                Document=document, FeatureTypes=["FORMS", "TABLES"]
            )
        else:
            response = client.detect_document_text(Document=document)
    except Exception as exc:  # boto3 raises many client-specific errors
        raise TextractError(f"Textract call failed: {exc}") from exc

    blocks = response.get("Blocks", [])
    lines = _lines(blocks)
    pairs = _key_values(blocks) if mode == FORMS_MODE else {}
    tables = _tables(blocks) if mode == FORMS_MODE else []
    text = _render(lines, pairs, tables)
    if not text.strip():
        warnings.append("Textract returned no text for this document.")

    return OcrResult(
        text=text,
        source="textract",
        mode=mode,
        pages=pages,
        line_count=len(lines),
        key_values=pairs,
        tables=tables,
        warnings=warnings,
    )
