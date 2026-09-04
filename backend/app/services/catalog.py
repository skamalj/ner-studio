"""The curated Bedrock model catalogue.

`model_catalog.json` is the source of truth for which Bedrock models the app
offers, what they cost, and - the part no AWS API exposes - whether each one
accepts image input. It replaces live model discovery for Bedrock, because
`list-foundation-models` cannot answer the vision question and the Price List
API has no per-model on-demand rate for the Marketplace-billed families.

Two rules from the catalogue that matter to callers:

* ``invoke_id`` is what goes on the wire. ``base_id`` is informational, and
  calling it for a model whose route is not ``in_region`` fails with a
  ValidationException telling you to use an inference profile.
* ``vision: true`` is the only signal that a model may be offered on an
  image-based tab.

Embeddings, video and speech models are deliberately not loaded - they are not
callable through the chat/Converse path this app uses.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache

from ..config import get_settings

log = logging.getLogger(__name__)

# route -> where inference physically runs, for the residency hint in the UI.
RESIDENCY = {
    "in_region": "India",
    "geo_in": "India",
    "geo_apac": "APAC",
    "global": "Worldwide",
}


@dataclass
class CatalogEntry:
    id: str  # invoke_id - what is sent as modelId
    name: str
    vendor: str
    vision: bool = False
    input_per_1m: float | None = None
    output_per_1m: float | None = None
    context: int | None = None
    max_output: int | None = None
    route: str = ""
    residency: str = ""
    flags: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def label(self) -> str:
        return f"{self.vendor} {self.name}"


def _entry(raw: dict) -> CatalogEntry | None:
    invoke_id = raw.get("invoke_id")
    if not invoke_id:
        return None

    flags: list[str] = []
    notes: list[str] = []
    if raw.get("access"):
        flags.append("gated")
        notes.append(str(raw["access"]))
    if raw.get("lifecycle"):
        flags.append("legacy")
        notes.append(str(raw["lifecycle"]))
    if raw.get("price_region"):
        flags.append("price unconfirmed")
        notes.append(f"price from {raw['price_region']}")
    if raw.get("note"):
        notes.append(str(raw["note"]))

    route = raw.get("route", "")
    return CatalogEntry(
        id=invoke_id,
        name=raw.get("name", invoke_id),
        vendor=raw.get("provider", ""),
        vision=bool(raw.get("vision")),
        input_per_1m=raw.get("price_in"),
        output_per_1m=raw.get("price_out"),
        context=raw.get("context"),
        max_output=raw.get("max_output"),
        route=route,
        residency=RESIDENCY.get(route, ""),
        flags=flags,
        note=" - ".join(notes),
    )


@lru_cache(maxsize=1)
def entries() -> list[CatalogEntry]:
    """Every chat-capable Bedrock model in the catalogue, in file order."""
    path = get_settings().model_catalog_path
    if not path.exists():
        log.info("no model catalogue at %s; falling back to live discovery", path)
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("could not read %s: %s", path.name, exc)
        return []

    parsed = [_entry(m) for m in raw.get("text_models", [])]
    return [e for e in parsed if e is not None]


@lru_cache(maxsize=1)
def by_id() -> dict[str, CatalogEntry]:
    return {e.id: e for e in entries()}


def region() -> str:
    """The region the catalogue was generated for, for a UI mismatch warning."""
    path = get_settings().model_catalog_path
    if not path.exists():
        return ""
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("region", "")
    except (OSError, ValueError):
        return ""


def refresh() -> None:
    entries.cache_clear()
    by_id.cache_clear()
