"""Per-million-token prices for the models in the catalog.

Bedrock prices come from the AWS Price List API, so they are real, current and
correct for the configured region. The API has no notion of a Bedrock model id,
though: it identifies a model by a `usagetype` string that is sometimes the
model id (`qwen.qwen3-32b-mantle-output-tokens-standard`) and sometimes a
marketing name (`Qwen3-32B-output-tokens`), so both are normalized to the same
comparable key and matched against the model id.

The other providers publish no pricing API. Their prices, if you want them, go
in `backend/pricing.json`; anything absent simply shows no price in the UI
rather than a number nobody verified.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..config import BACKEND_ROOT, get_settings

log = logging.getLogger(__name__)

PRICING_OVERRIDES = BACKEND_ROOT / "pricing.json"

# Only plain on-demand rows. Batch/flex/priority tiers are different products,
# and the API mislabels some of them (a `-batch` usage type carrying the
# inferenceType "Output tokens"), so the usage type suffix is what decides.
_STANDARD_SUFFIX = re.compile(
    r"-(?P<direction>input|output)-tokens(?:-standard)?$", re.IGNORECASE
)
_REGION_PREFIX = re.compile(r"^[A-Z0-9]{2,6}-")
_CROSS_REGION_PREFIX = re.compile(r"^(us|usw|use|apac|eu|global|in|ca|sa|au|jp)\.")
_VERSION_SUFFIX = re.compile(r"[-:]v\d+(?::\d+)?$|:\d+$", re.IGNORECASE)
_NOISE = re.compile(r"(-mantle|-instruct|-preview)", re.IGNORECASE)


@dataclass(frozen=True)
class ModelPrice:
    """USD per one million tokens."""

    input_per_1m: float | None = None
    output_per_1m: float | None = None

    def known(self) -> bool:
        return self.input_per_1m is not None or self.output_per_1m is not None


def _key(value: str) -> str:
    """Reduce a model id or usage type to a comparable alphanumeric key."""
    value = _NOISE.sub("", value or "")
    value = _CROSS_REGION_PREFIX.sub("", value.strip())
    value = _VERSION_SUFFIX.sub("", value)
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _keys_for_model(model_id: str) -> list[str]:
    """Candidate keys for a Bedrock model id, most specific first.

    A price row may be named after the full id (`qwen.qwen3-32b`) or after the
    marketing name alone (`NovaPro` for `apac.amazon.nova-pro-v1:0`), so the
    cross-region prefix and then the vendor prefix are peeled off in turn.
    """
    stripped = _CROSS_REGION_PREFIX.sub("", model_id.strip())
    candidates = [model_id, stripped]
    if "." in stripped:
        candidates.append(stripped.split(".", 1)[1])
    return [k for k in dict.fromkeys(_key(c) for c in candidates) if k]


def _price_rows(region: str) -> list[dict]:
    import boto3

    # The Price List API lives in a handful of regions; us-east-1 always works.
    client = boto3.client("pricing", region_name="us-east-1")
    rows: list[dict] = []
    token: str | None = None
    while True:
        kwargs = {
            "ServiceCode": "AmazonBedrock",
            "Filters": [
                {"Type": "TERM_MATCH", "Field": "regionCode", "Value": region}
            ],
            "MaxResults": 100,
        }
        if token:
            kwargs["NextToken"] = token
        response = client.get_products(**kwargs)
        rows += [json.loads(item) for item in response["PriceList"]]
        token = response.get("NextToken")
        if not token:
            return rows


def _unit_price(record: dict) -> float | None:
    """USD per 1K tokens from a price record, or None."""
    for term in record.get("terms", {}).get("OnDemand", {}).values():
        for dimension in term.get("priceDimensions", {}).values():
            try:
                price = float(dimension["pricePerUnit"]["USD"])
            except (KeyError, TypeError, ValueError):
                continue
            if price > 0:
                return price
    return None


@lru_cache(maxsize=4)
def bedrock_prices(region: str) -> dict[str, ModelPrice]:
    """Map normalized model keys to per-million-token prices for a region."""
    try:
        rows = _price_rows(region)
    except Exception as exc:
        log.info("Bedrock price list unavailable: %s", exc)
        return {}

    collected: dict[str, dict[str, list[float]]] = {}
    for record in rows:
        attributes = record.get("product", {}).get("attributes", {})
        usage_type = attributes.get("usagetype", "")
        match = _STANDARD_SUFFIX.search(usage_type)
        if not match:
            continue
        per_1k = _unit_price(record)
        if per_1k is None:
            continue
        direction = match.group("direction").lower()

        stem = usage_type[: match.start()]
        candidates = {_key(_REGION_PREFIX.sub("", stem))}
        if attributes.get("model"):
            candidates.add(_key(attributes["model"]))
        for key in filter(None, candidates):
            collected.setdefault(key, {}).setdefault(direction, []).append(per_1k * 1000)

    return {
        key: ModelPrice(
            input_per_1m=min(directions["input"]) if directions.get("input") else None,
            output_per_1m=min(directions["output"]) if directions.get("output") else None,
        )
        for key, directions in collected.items()
    }


@lru_cache(maxsize=1)
def _overrides() -> dict[str, dict[str, float]]:
    """Hand-maintained prices, keyed `provider/model-id`."""
    if not PRICING_OVERRIDES.exists():
        return {}
    try:
        raw = json.loads(PRICING_OVERRIDES.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("Ignoring malformed %s: %s", PRICING_OVERRIDES.name, exc)
        return {}
    return {k.lower(): v for k, v in raw.items() if isinstance(v, dict)}


def price_for(provider: str, model_id: str) -> ModelPrice:
    """Price for one model, preferring an explicit override."""
    override = _overrides().get(f"{provider}/{model_id}".lower())
    if override:
        return ModelPrice(
            input_per_1m=override.get("input_per_1m"),
            output_per_1m=override.get("output_per_1m"),
        )
    if provider != "bedrock":
        return ModelPrice()

    table = bedrock_prices(get_settings().aws_region)
    if not table:
        return ModelPrice()
    candidates = _keys_for_model(model_id)
    for key in candidates:
        if key in table:
            return table[key]
    # Fall back to the longest price key that is a prefix of a candidate,
    # which catches ids carrying an extra date or revision segment.
    best = ""
    for candidate in candidates:
        for key in table:
            if len(key) >= 8 and candidate.startswith(key) and len(key) > len(best):
                best = key
    return table[best] if best else ModelPrice()


def refresh() -> None:
    bedrock_prices.cache_clear()
    _overrides.cache_clear()
