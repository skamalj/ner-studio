"""OCR engine dispatch.

Two ways to turn a page into text before the extraction LLM sees it:

* **Textract** - AWS OCR, either raw lines or with FORMS + TABLES flattened in.
* **Local VLM** - an OCR model served over an OpenAI-compatible endpoint
  (GLM-OCR on llama.cpp, for example). Free per page and it tends to preserve
  line structure that Textract splits apart, but it is a model: it can misread
  a digit where Textract would not.

`raw` skips OCR entirely and just stores the bytes, for the vision flow where
the image goes to the model directly.
"""
from __future__ import annotations

from ..config import get_settings
from ..graphs.common import call_vision_model
from ..providers import LOCAL, default_model_for
from . import textract
from .textract import RAW_MODE, TextractError

LOCAL_OCR = "local_ocr"

ENGINES = (textract.TEXT_MODE, textract.FORMS_MODE, LOCAL_OCR, RAW_MODE)


async def run(
    data: bytes,
    filename: str,
    mode: str,
    provider: str | None = None,
    model: str | None = None,
) -> textract.OcrResult:
    """Produce text for an uploaded file using the requested engine."""
    if mode != LOCAL_OCR:
        return textract.extract_text(data, filename, mode)

    settings = get_settings()
    provider = provider or LOCAL
    model = model or default_model_for(provider)
    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""

    if suffix in textract.TEXT_EXTENSIONS:  # already text, nothing to read
        return textract.extract_text(data, filename, textract.TEXT_MODE)

    try:
        # No system prompt: OCR models are trained on a bare instruction and
        # extra framing degrades them.
        text, _usage = await call_vision_model(
            None,
            settings.ocr_prompt,
            data,
            suffix,
            provider,
            model,
            settings.ocr_temperature,
        )
    except ValueError as exc:  # unsupported image type
        raise TextractError(str(exc)) from exc
    except Exception as exc:
        raise TextractError(f"Local OCR model failed: {exc}") from exc

    lines = [line for line in text.splitlines() if line.strip()]
    return textract.OcrResult(
        text=text,
        source=f"{provider}:{model}",
        mode=LOCAL_OCR,
        line_count=len(lines),
        warnings=[] if text.strip() else ["The OCR model returned no text."],
    )
