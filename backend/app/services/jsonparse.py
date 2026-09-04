"""Best-effort recovery of a JSON object from an LLM response."""
from __future__ import annotations

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def parse_json_object(text: str) -> dict | list | None:
    """Return the JSON value embedded in ``text``, or None if there is none."""
    if not text:
        return None
    candidates = [text.strip()]
    fenced = _FENCE.findall(text)
    candidates = [f.strip() for f in fenced] + candidates

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (ValueError, TypeError):
            pass

    # Fall back to the outermost balanced object / array in the response.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except (ValueError, TypeError):
                continue
    return None
