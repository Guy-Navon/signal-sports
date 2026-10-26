"""The documented hosted LLM configuration selects the intended provider (#370).

deploy/signal.env.example documents the openai_compat block the PC uses. These checks read
the template itself, so the documentation and the code cannot drift apart:

- the documented block selects and INITIALIZES the OpenAI-compatible provider with the
  documented settings, without any network call (httpx sends are made to fail);
- the template's active defaults are an intentional rules-only start (disabled, no warning);
- a named provider with a missing key is an ACCIDENT: hosted startup refuses it instead of
  running rules-only silently, and the refusal names variables, never secret values;
- the committed template carries no secret value.
"""
import logging
import re
from pathlib import Path

import httpx
import pytest

from app.classification.providers import DisabledLLMProvider, OpenAICompatibleProvider
from app.classification.service import get_llm_provider
from app.core.deploy_mode import UnsafeDeployConfig, validate_deploy_startup_config

TEMPLATE = Path(__file__).resolve().parents[2] / "deploy" / "signal.env.example"
SENTINEL = "sk-test-SENTINEL-not-a-real-key"
_CLASSIFICATION_KEYS = (
    "CLASSIFICATION_PROVIDER", "CLASSIFICATION_BASE_URL", "CLASSIFICATION_MODEL",
    "CLASSIFICATION_API_KEY", "CLASSIFICATION_RESPONSE_FORMAT", "CLASSIFICATION_REASONING_EFFORT",
    "CLASSIFICATION_MAX_OUTPUT_TOKENS", "CLASSIFICATION_TIMEOUT_SECONDS",
)


def _active(text):
    return dict(re.findall(r"^([A-Z_]+)=(.*)$", text, re.M))


def _documented_llm_block(text):
    return dict(re.findall(r"^#\s+(CLASSIFICATION_[A-Z_]+)=(\S+)\s*$", text, re.M))


@pytest.fixture
def clean_env(monkeypatch):
    for k in _CLASSIFICATION_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    return monkeypatch


def test_the_documented_block_initializes_openai_compat_without_a_call(clean_env, caplog):
    block = _documented_llm_block(TEMPLATE.read_text(encoding="utf-8"))
    assert block["CLASSIFICATION_PROVIDER"] == "openai_compat"
    for k, v in block.items():
        clean_env.setenv(k, v)
    clean_env.setenv("CLASSIFICATION_API_KEY", SENTINEL)
    with caplog.at_level(logging.INFO):
        provider = get_llm_provider()
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.provider_id == f"openai_compat:{block['CLASSIFICATION_MODEL']}"
    assert provider._url == block["CLASSIFICATION_BASE_URL"].rstrip("/") + "/chat/completions"
    assert provider._response_format == block["CLASSIFICATION_RESPONSE_FORMAT"]
    assert provider._reasoning_effort == block["CLASSIFICATION_REASONING_EFFORT"]
    assert provider._max_output_tokens == int(block["CLASSIFICATION_MAX_OUTPUT_TOKENS"])
    assert SENTINEL not in caplog.text


def test_the_template_defaults_are_an_intentional_rules_only_start(clean_env, caplog):
    active = _active(TEMPLATE.read_text(encoding="utf-8"))
    for k in _CLASSIFICATION_KEYS:
        if k in active:
            clean_env.setenv(k, active[k])
    with caplog.at_level(logging.WARNING):
        provider = get_llm_provider()
    assert active["CLASSIFICATION_PROVIDER"] == "disabled"
    assert isinstance(provider, DisabledLLMProvider)
    assert "CLASSIFICATION" not in caplog.text          # intentional: nothing to warn about


@pytest.mark.parametrize("missing", ["CLASSIFICATION_BASE_URL", "CLASSIFICATION_MODEL", "CLASSIFICATION_API_KEY"])
def test_a_named_provider_with_a_missing_key_refuses_hosted_startup(clean_env, monkeypatch, missing, caplog):
    for k, v in _documented_llm_block(TEMPLATE.read_text(encoding="utf-8")).items():
        clean_env.setenv(k, v)
    clean_env.setenv("CLASSIFICATION_API_KEY", SENTINEL)
    clean_env.delenv(missing)
    monkeypatch.setenv("DEPLOY_ENV", "hosted")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    monkeypatch.setenv("AUTH_SIGNUP_ENABLED", "false")
    with caplog.at_level(logging.WARNING), pytest.raises(UnsafeDeployConfig) as err:
        validate_deploy_startup_config()
    assert "rules-only" in str(err.value) and "CLASSIFICATION_PROVIDER=openai_compat" in str(err.value)
    assert SENTINEL not in str(err.value) and SENTINEL not in caplog.text


def test_the_committed_template_holds_no_secret_value():
    text = TEMPLATE.read_text(encoding="utf-8")
    active = _active(text)
    for k in ("CLASSIFICATION_API_KEY", "TRANSLATION_API_KEY", "TELEGRAM_BOT_TOKEN", "SMTP_PASSWORD",
              "AUTH_ADMIN_PASSWORD", "GOOGLE_OAUTH_CLIENT_SECRET"):
        assert active.get(k, "") == "", k
    assert not re.search(r"\b(gsk_|sk-|AIza)[A-Za-z0-9_\-]{8,}", text)
