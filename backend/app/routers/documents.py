"""Document upload and OCR."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from ..schemas import DocumentOut, ExtractTextOut
from ..services import documents, ocr, textract

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=ExtractTextOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    mode: str = Form(textract.TEXT_MODE),
    ocr_provider: str | None = Form(None),
    ocr_model: str | None = Form(None),
) -> ExtractTextOut:
    """Upload a document or image, run the chosen OCR engine, store the text."""
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty")
    if mode not in ocr.ENGINES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"mode must be one of {', '.join(ocr.ENGINES)}",
        )
    try:
        result = await ocr.run(
            data, file.filename or "upload", mode, ocr_provider, ocr_model
        )
    except textract.TextractError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    record = documents.save(
        data=data,
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        text=result.text,
        ocr_source=result.source,
        ocr_mode=result.mode,
        pages=result.pages,
        line_count=result.line_count,
    )
    return ExtractTextOut(
        document=DocumentOut(**asdict(record)),
        text=result.text,
        key_values=result.key_values,
        tables=result.tables,
        warnings=result.warnings,
    )


@router.get("", response_model=list[DocumentOut])
def list_documents(limit: int = 25) -> list[DocumentOut]:
    return [DocumentOut(**asdict(r)) for r in documents.list_recent(limit)]


@router.get("/{document_id}/text")
def document_text(document_id: str) -> dict:
    try:
        return {"document_id": document_id, "text": documents.get_text(document_id)}
    except documents.DocumentError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
