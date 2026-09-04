"""Flat-file template store.

One template per ``.txt`` file in ``settings.templates_dir``, with the file
stem as the template name -- the same storage the original Flask app used, so
the existing templates directory can be dropped in unchanged.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from .config import get_settings

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$")


class TemplateError(ValueError):
    """Raised for an invalid template name or a missing template."""


def _validate(name: str) -> str:
    name = (name or "").strip()
    if not _SAFE_NAME.match(name):
        raise TemplateError(
            "Template name must be 1-64 characters of letters, digits, "
            "space, dot, dash or underscore."
        )
    return name


def _path(name: str) -> Path:
    return get_settings().templates_dir / f"{_validate(name)}.txt"


def list_templates() -> dict[str, str]:
    """Return every template as ``{name: definition}``."""
    directory = get_settings().templates_dir
    templates: dict[str, str] = {}
    for file in sorted(directory.glob("*.txt")):
        try:
            templates[file.stem] = file.read_text(encoding="utf-8")
        except OSError:
            continue
    return templates


def list_template_meta() -> list[dict]:
    """Return name/size/modified metadata for each template."""
    directory = get_settings().templates_dir
    meta = []
    for file in sorted(directory.glob("*.txt")):
        stat = file.stat()
        meta.append(
            {
                "name": file.stem,
                "size": stat.st_size,
                "updated_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        )
    return meta


def get_template(name: str) -> str:
    path = _path(name)
    if not path.exists():
        raise TemplateError(f"Template {name!r} not found")
    return path.read_text(encoding="utf-8")


def save_template(name: str, definition: str) -> str:
    """Create or overwrite a template; returns the stored name."""
    if not (definition or "").strip():
        raise TemplateError("Template definition cannot be empty")
    path = _path(name)
    path.write_text(definition, encoding="utf-8")
    return path.stem


def delete_template(name: str) -> None:
    path = _path(name)
    if not path.exists():
        raise TemplateError(f"Template {name!r} not found")
    path.unlink()
