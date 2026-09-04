"""Chat-model factory and catalog for the four supported providers."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

from .config import get_settings
from .services import catalog
from .services.pricing import price_for, refresh as refresh_prices

log = logging.getLogger(__name__)

BEDROCK = "bedrock"
ANTHROPIC = "anthropic"
OPENAI = "openai"
GEMINI = "gemini"
LOCAL = "local"

PROVIDERS = (BEDROCK, ANTHROPIC, OPENAI, GEMINI, LOCAL)


@dataclass
class ModelOption:
    """A selectable model: what to send, what it costs, what it accepts."""

    id: str  # the value sent as modelId
    label: str = ""
    input_per_1m: float | None = None
    output_per_1m: float | None = None
    # Only models with supports_images may be offered on an image-based tab.
    supports_images: bool = False
    context: int | None = None
    residency: str = ""
    flags: list[str] = field(default_factory=list)
    note: str = ""


# What the UI shows next to a provider.
READY = "ready"
NOT_CONFIGURED = "not_configured"
UNREACHABLE = "unreachable"

STATUS_LABELS = {
    READY: "Ready",
    NOT_CONFIGURED: "Not configured",
    UNREACHABLE: "Not responding",
}


# What to do to make each provider usable. Kept server-side because this is
# where the configuration actually lives.
ENV_KEY = {
    ANTHROPIC: "ANTHROPIC_API_KEY",
    OPENAI: "OPENAI_API_KEY",
    GEMINI: "GOOGLE_API_KEY",
}


def setup_hint(provider: str, status: str) -> str:
    """One line telling the user how to configure or revive a provider."""
    settings = get_settings()
    if provider == BEDROCK:
        if status == READY:
            return (
                f"Using AWS credentials for region {settings.aws_region}. "
                "If calls fail with an expired token, run: aws sso login"
            )
        return (
            "No AWS credentials found. Run `aws sso login --profile <name>`, or set "
            "AWS_PROFILE / AWS_ACCESS_KEY_ID in backend/.env, then restart the backend."
        )
    if provider == LOCAL:
        if status == UNREACHABLE:
            return (
                f"Nothing is answering at {settings.local_base_url}. Start the server, "
                "e.g. llama-server -hf ggml-org/GLM-OCR-GGUF --port 8085"
            )
        if status == READY:
            return f"Reading models from {settings.local_base_url}"
        return (
            "Set LOCAL_BASE_URL in backend/.env to an OpenAI-compatible server, "
            "e.g. http://127.0.0.1:8085/v1, then restart the backend."
        )
    key = ENV_KEY.get(provider, "")
    if status == READY:
        return f"Configured via {key}"
    return f"Set {key} in backend/.env, then restart the backend."


@dataclass
class ProviderInfo:
    id: str
    label: str
    configured: bool
    default_model: str
    models: list[ModelOption] = field(default_factory=list)
    note: str = ""
    status: str = READY
    #: How to configure this provider, shown on hover in the UI.
    setup_hint: str = ""


# Fallback lists, used when live discovery is unavailable (no credentials, no
# network). The UI also accepts a free-text model id, so these are only hints.
FALLBACK_MODELS: dict[str, list[str]] = {
    BEDROCK: [
        "qwen.qwen3-235b-a22b-2507-v1:0",
        "qwen.qwen3-32b-v1:0",
        "qwen.qwen3-next-80b-a3b",
        "us.amazon.nova-pro-v1:0",
    ],
    ANTHROPIC: [
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-haiku-4-5",
    ],
    OPENAI: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4"],
    GEMINI: ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
    # Whatever the local server is serving; discovered from /v1/models.
    LOCAL: ["model"],
}

DEFAULT_MODEL: dict[str, str] = {
    BEDROCK: FALLBACK_MODELS[BEDROCK][0],
    ANTHROPIC: FALLBACK_MODELS[ANTHROPIC][1],
    OPENAI: FALLBACK_MODELS[OPENAI][0],
    GEMINI: FALLBACK_MODELS[GEMINI][0],
    LOCAL: FALLBACK_MODELS[LOCAL][0],
}

LABELS = {
    BEDROCK: "AWS Bedrock",
    ANTHROPIC: "Anthropic",
    OPENAI: "OpenAI",
    GEMINI: "Google Gemini",
    LOCAL: "Local (OpenAI-compatible)",
}


class ProviderError(RuntimeError):
    """Raised when a provider is requested but cannot be used."""


def _has_aws_credentials() -> bool:
    if os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_PROFILE"):
        return True
    try:
        import boto3

        return boto3.Session().get_credentials() is not None
    except Exception:  # pragma: no cover - boto3 config edge cases
        return False


def is_configured(provider: str) -> bool:
    s = get_settings()
    if provider == OPENAI:
        return bool(s.openai_api_key or os.environ.get("OPENAI_API_KEY"))
    if provider == ANTHROPIC:
        return bool(s.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"))
    if provider == GEMINI:
        return bool(
            s.google_api_key
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
        )
    if provider == BEDROCK:
        return _has_aws_credentials()
    if provider == LOCAL:
        return bool(s.local_base_url)
    return False


def build_chat_model(
    provider: str,
    model: str | None = None,
    temperature: float = 0.5,
) -> BaseChatModel:
    """Return a LangChain chat model for the given provider."""
    s = get_settings()
    provider = (provider or s.default_provider).lower()
    if provider not in PROVIDERS:
        raise ProviderError(f"Unknown provider {provider!r}. Expected one of {PROVIDERS}.")
    if not is_configured(provider):
        raise ProviderError(
            f"{LABELS[provider]} is not configured. "
            "Set the matching credentials in backend/.env and restart the server."
        )
    model = model or DEFAULT_MODEL[provider]

    if provider == LOCAL:
        from langchain_openai import ChatOpenAI

        # A local server needs no real key, but the client insists on one.
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            base_url=s.local_base_url,
            api_key=s.local_api_key or "not-needed",
        )

    if provider == OPENAI:
        from langchain_openai import ChatOpenAI

        kwargs = {"model": model, "temperature": temperature}
        if s.openai_api_key:
            kwargs["api_key"] = s.openai_api_key
        return ChatOpenAI(**kwargs)

    if provider == ANTHROPIC:
        from langchain_anthropic import ChatAnthropic

        kwargs = {"model": model, "temperature": temperature, "max_tokens": 8192}
        if s.anthropic_api_key:
            kwargs["api_key"] = s.anthropic_api_key
        return ChatAnthropic(**kwargs)

    if provider == GEMINI:
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs = {"model": model, "temperature": temperature}
        if s.google_api_key:
            kwargs["google_api_key"] = s.google_api_key
        return ChatGoogleGenerativeAI(**kwargs)

    from langchain_aws import ChatBedrockConverse

    return ChatBedrockConverse(
        model=model, temperature=temperature, region_name=s.aws_region
    )


# --------------------------------------------------------------------------
# Catalog / discovery
# --------------------------------------------------------------------------
def _discover_bedrock() -> list[str]:
    import boto3

    s = get_settings()
    client = boto3.client("bedrock", region_name=s.aws_region)
    models: list[str] = []
    try:
        paginator = client.get_paginator("list_inference_profiles")
        for page in paginator.paginate():
            models += [
                p["inferenceProfileId"]
                for p in page.get("inferenceProfileSummaries", [])
                if p.get("status") == "ACTIVE"
            ]
    except Exception as exc:  # pragma: no cover - optional permission
        log.debug("list_inference_profiles unavailable: %s", exc)
    try:
        resp = client.list_foundation_models(byOutputModality="TEXT")
        models += [
            m["modelId"]
            for m in resp.get("modelSummaries", [])
            if "ON_DEMAND" in m.get("inferenceTypesSupported", [])
        ]
    except Exception as exc:  # pragma: no cover - optional permission
        log.debug("list_foundation_models unavailable: %s", exc)
    return sorted(set(models))


def _discover_openai() -> list[str]:
    from openai import OpenAI

    s = get_settings()
    client = OpenAI(api_key=s.openai_api_key or os.environ.get("OPENAI_API_KEY"))
    ids = [m.id for m in client.models.list().data]
    return sorted(i for i in ids if i.startswith(("gpt-", "o1", "o3", "o4", "chatgpt")))


def _discover_anthropic() -> list[str]:
    import anthropic

    s = get_settings()
    client = anthropic.Anthropic(
        api_key=s.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
    )
    return [m.id for m in client.models.list(limit=50).data]


def _discover_gemini() -> list[str]:
    import google.generativeai as genai

    s = get_settings()
    genai.configure(
        api_key=s.google_api_key
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
    )
    return sorted(
        m.name.removeprefix("models/")
        for m in genai.list_models()
        if "generateContent" in getattr(m, "supported_generation_methods", [])
    )


def _discover_local() -> list[str]:
    from openai import OpenAI

    s = get_settings()
    client = OpenAI(
        base_url=s.local_base_url,
        api_key=s.local_api_key or "not-needed",
        timeout=3.0,
        max_retries=0,
    )
    return [m.id for m in client.models.list().data]


_DISCOVERY = {
    BEDROCK: _discover_bedrock,
    OPENAI: _discover_openai,
    ANTHROPIC: _discover_anthropic,
    GEMINI: _discover_gemini,
    LOCAL: _discover_local,
}


@lru_cache(maxsize=1)
def provider_catalog() -> list[ProviderInfo]:
    """List providers, whether they are configured, and their model ids.

    Model ids are discovered live where the provider exposes a list API and
    credentials are present; otherwise a static fallback list is returned.
    """
    s_settings = get_settings()
    infos: list[ProviderInfo] = []
    for provider in PROVIDERS:
        configured = is_configured(provider)
        status = READY if configured else NOT_CONFIGURED
        models = list(FALLBACK_MODELS[provider])
        note = ""
        if provider == BEDROCK and catalog.entries():
            # The curated catalogue wins over live discovery: it carries the
            # vision flag and the correct inference-profile ids.
            models = [e.id for e in catalog.entries()]
        elif configured:
            try:
                discovered = _DISCOVERY[provider]()
                if discovered:
                    models = discovered
            except Exception as exc:
                log.info("model discovery failed for %s: %s", provider, exc)
                if provider == LOCAL:
                    # A local server is only usable if it answers. Failing to
                    # list models means nothing is listening, so offer nothing
                    # rather than a model id that cannot be called.
                    configured, status = False, UNREACHABLE
                    models = []
                    note = f"No server responding at {s_settings.local_base_url}."
                else:
                    note = (
                        f"Could not list models ({type(exc).__name__}); showing defaults."
                    )
        else:
            note = "Credentials not configured."
        default = DEFAULT_MODEL[provider]
        if provider == s_settings.default_provider and s_settings.default_model:
            default = s_settings.default_model
        elif default not in models:
            default = models[0] if models else default

        options = _options_for(provider, models)
        vision = sum(1 for o in options if o.supports_images)
        if options and not note:
            note = (
                f"{len(options)} models, {vision} accept images - cheapest output first."
            )

        infos.append(
            ProviderInfo(
                id=provider,
                label=LABELS[provider],
                configured=configured,
                default_model=default,
                models=sort_by_price(options),
                note=note,
                status=status,
                setup_hint=setup_hint(provider, status),
            )
        )
    return infos


def _options_for(provider: str, models: list[str]) -> list[ModelOption]:
    """Build the selectable options for a provider.

    Bedrock comes from the curated catalogue, which is the only source that
    knows about image support; the AWS Price List fills in a price where the
    catalogue has none. Other providers have no capability metadata, so an
    OpenAI-compatible local server is assumed to serve a vision model.
    """
    settings = get_settings()
    known = catalog.by_id() if provider == BEDROCK else {}
    options: list[ModelOption] = []
    for model in models:
        entry = known.get(model)
        if entry is not None:
            price_in, price_out = entry.input_per_1m, entry.output_per_1m
            if price_out is None:  # catalogue has no figure - try the price list
                fallback = price_for(provider, model)
                price_in = price_in if price_in is not None else fallback.input_per_1m
                price_out = fallback.output_per_1m
            options.append(
                ModelOption(
                    id=entry.id,
                    label=entry.label,
                    input_per_1m=price_in,
                    output_per_1m=price_out,
                    supports_images=entry.vision,
                    context=entry.context,
                    residency=entry.residency,
                    flags=list(entry.flags),
                    note=entry.note,
                )
            )
            continue
        price = price_for(provider, model)
        options.append(
            ModelOption(
                id=model,
                input_per_1m=price.input_per_1m,
                output_per_1m=price.output_per_1m,
                supports_images=(provider == LOCAL and settings.local_supports_images),
            )
        )
    return options


def sort_by_price(options: list[ModelOption]) -> list[ModelOption]:
    """Cheapest output price first; models with no known price go last."""
    return sorted(
        options,
        key=lambda o: (
            o.output_per_1m is None,
            o.output_per_1m if o.output_per_1m is not None else 0.0,
            o.id,
        ),
    )


def default_model_for(provider: str) -> str:
    """The model used when a request does not name one."""
    for info in provider_catalog():
        if info.id == provider:
            return info.default_model
    return DEFAULT_MODEL.get(provider, "")


def refresh_catalog() -> list[ProviderInfo]:
    provider_catalog.cache_clear()
    catalog.refresh()
    refresh_prices()
    return provider_catalog()
