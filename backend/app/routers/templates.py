"""Template CRUD backed by flat .txt files."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from .. import store
from ..schemas import TemplateOut, TemplateSaveIn

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=dict[str, str])
def get_templates() -> dict[str, str]:
    """All templates as ``{name: definition}`` (same shape as the original API)."""
    return store.list_templates()


@router.get("/meta")
def get_template_meta() -> list[dict]:
    return store.list_template_meta()


@router.get("/{name}", response_model=TemplateOut)
def get_template(name: str) -> TemplateOut:
    try:
        return TemplateOut(name=name, definition=store.get_template(name))
    except store.TemplateError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("", status_code=status.HTTP_201_CREATED)
def save_template(payload: TemplateSaveIn) -> dict:
    try:
        name = store.save_template(payload.name, payload.definition)
    except store.TemplateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {
        "message": f"Template '{name}' saved successfully",
        "name": name,
        "templates": store.list_templates(),
    }


@router.delete("/{name}")
def delete_template(name: str) -> dict:
    try:
        store.delete_template(name)
    except store.TemplateError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"message": f"Template '{name}' deleted", "templates": store.list_templates()}
