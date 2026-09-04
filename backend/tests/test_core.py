"""Unit tests for the pure pieces: chunking, JSON recovery, prompts, store."""
from __future__ import annotations

import pytest

from app import prompts, store
from app.config import get_settings
from app.services.chunking import count_tokens, normalize, split_text
from app.services.jsonparse import parse_json_object


def test_short_text_is_one_chunk():
    assert split_text("hello world") == ["hello world"]


def test_long_text_splits_within_budget():
    paragraph = "The quick brown fox jumps over the lazy dog. " * 40
    document = "\n\n".join(paragraph for _ in range(30))
    chunks = split_text(document, token_limit=500)
    assert len(chunks) > 1
    assert all(count_tokens(chunk) <= 500 for chunk in chunks)


def test_oversized_single_unit_is_hard_split():
    chunks = split_text("word " * 5000, token_limit=100)
    assert len(chunks) > 1
    assert all(count_tokens(chunk) <= 100 for chunk in chunks)


def test_normalize_collapses_whitespace():
    assert normalize("a   b\n\n\n\nc") == "a b\n\nc"


@pytest.mark.parametrize(
    "raw",
    [
        '{"name": "Ada"}',
        '```json\n{"name": "Ada"}\n```',
        'Sure, here you go:\n{"name": "Ada"}\nHope that helps.',
    ],
)
def test_parse_json_object_recovers_object(raw):
    assert parse_json_object(raw) == {"name": "Ada"}


def test_parse_json_object_returns_none_without_json():
    assert parse_json_object("no json here") is None


def test_entity_prompt_keeps_original_prefix():
    prompt = prompts.entity_prompt("Total Income\nName")
    assert prompt.startswith(prompts.ENTITY_PROMPT_PREFIX)
    assert "Total Income" in prompt


def test_summary_prompt_embeds_text():
    assert "hello" in prompts.summary_prompt("concise", "hello")


def test_unknown_summary_type_raises():
    with pytest.raises(ValueError):
        prompts.summary_prompt("nope", "hello")


def test_template_roundtrip(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "templates_dir", tmp_path)

    store.save_template("invoice", "Invoice number\nTotal")
    assert store.get_template("invoice") == "Invoice number\nTotal"
    assert "invoice" in store.list_templates()
    assert store.list_template_meta()[0]["name"] == "invoice"

    store.delete_template("invoice")
    assert store.list_templates() == {}


@pytest.mark.parametrize("name", ["", "../escape", "bad/name", "x" * 100])
def test_template_name_validation(name, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "templates_dir", tmp_path)
    with pytest.raises(store.TemplateError):
        store.save_template(name, "definition")


# --- pricing -------------------------------------------------------------
def test_price_keys_peel_region_and_vendor_prefixes():
    from app.services.pricing import _keys_for_model

    keys = _keys_for_model("apac.amazon.nova-pro-v1:0")
    assert "amazonnovapro" in keys  # matches a usage type named after the id
    assert "novapro" in keys  # matches one named "Nova Pro"


def test_price_key_ignores_marketing_noise():
    from app.services.pricing import _key, _keys_for_model

    # `-mantle` and the version suffix are noise on an otherwise identical id.
    assert _key("qwen.qwen3-32b-mantle") == _key("qwen.qwen3-32b-v1:0")
    # A row named after the marketing name still resolves to the same model.
    assert _key("Qwen3-32B") in _keys_for_model("qwen.qwen3-32b-v1:0")


def test_standard_suffix_rejects_non_ondemand_tiers():
    from app.services.pricing import _STANDARD_SUFFIX

    assert _STANDARD_SUFFIX.search("APS3-Qwen3-32B-output-tokens")
    assert _STANDARD_SUFFIX.search("APS3-qwen.qwen3-32b-output-tokens-standard")
    # Batch/flex/priority are different products, even when the record's
    # inferenceType claims otherwise.
    assert not _STANDARD_SUFFIX.search("APS3-Qwen3-32B-output-tokens-batch")
    assert not _STANDARD_SUFFIX.search("APS3-Qwen3-32B-output-tokens-flex")
    assert not _STANDARD_SUFFIX.search("APS3-Qwen3-32B-output-tokens-priority")


def test_models_sort_cheapest_output_first_unpriced_last():
    from app.providers import ModelOption, sort_by_price

    ordered = sort_by_price(
        [
            ModelOption("expensive", 1.0, 9.0),
            ModelOption("unknown"),
            ModelOption("cheap", 0.1, 0.5),
        ]
    )
    assert [m.id for m in ordered] == ["cheap", "expensive", "unknown"]


# --- model catalogue -----------------------------------------------------
def test_catalogue_loads_and_flags_vision():
    from app.services import catalog

    entries = catalog.entries()
    assert entries, "model_catalog.json should load"
    assert any(e.vision for e in entries)
    assert any(not e.vision for e in entries)


def test_catalogue_uses_invoke_id_not_base_id():
    from app.services import catalog

    by_id = catalog.by_id()
    # Claude in ap-south-1 is global-routed: the bare id is not callable.
    assert "global.anthropic.claude-sonnet-5" in by_id
    assert "anthropic.claude-sonnet-5" not in by_id


def test_vision_filter_excludes_text_only_models():
    from app.providers import BEDROCK, provider_catalog

    bedrock = next(p for p in provider_catalog() if p.id == BEDROCK)
    vision = [m for m in bedrock.models if m.supports_images]
    assert vision and len(vision) < len(bedrock.models)
    # A known text-only model must not reach the vision tab.
    assert all(m.id != "qwen.qwen3-235b-a22b-2507-v1:0" for m in vision)


def test_embeddings_and_audio_models_are_not_offered():
    from app.services import catalog

    ids = set(catalog.by_id())
    for excluded in (
        "amazon.titan-embed-text-v2:0",
        "mistral.voxtral-mini-3b-2507",
        "global.twelvelabs.pegasus-1-2-v1:0",
    ):
        assert excluded not in ids


def test_provider_status_values_are_distinct():
    from app import providers

    assert {providers.READY, providers.NOT_CONFIGURED, providers.UNREACHABLE} == {
        "ready",
        "not_configured",
        "unreachable",
    }
    # Every status the API can emit has a label for the UI.
    assert set(providers.STATUS_LABELS) == {
        providers.READY,
        providers.NOT_CONFIGURED,
        providers.UNREACHABLE,
    }


def test_setup_hint_names_the_env_key_to_set():
    from app import providers

    for provider, key in providers.ENV_KEY.items():
        hint = providers.setup_hint(provider, providers.NOT_CONFIGURED)
        assert key in hint and "backend/.env" in hint


def test_setup_hint_for_dead_local_server_says_how_to_start_it():
    from app import providers

    hint = providers.setup_hint(providers.LOCAL, providers.UNREACHABLE)
    assert "llama-server" in hint


def test_setup_hint_for_bedrock_mentions_sso_login():
    from app import providers

    assert "aws sso login" in providers.setup_hint(providers.BEDROCK, providers.READY)
