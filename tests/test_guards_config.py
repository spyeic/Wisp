import pytest

from config import Config, ConfigError
from guards import Deduplicator, RateLimiter


def test_dedup_ttl_and_bound():
    now = [0]
    guard = Deduplicator(max_entries=2, ttl=10, clock=lambda: now[0])
    assert guard.claim((42, 1))
    assert not guard.claim((42, 1))
    assert guard.claim((43, 1))
    assert guard.claim((42, 2))
    assert len(guard.entries) == 2
    now[0] = 11
    assert guard.claim((42, 2))


def test_rate_limit_per_user_and_expiry():
    now = [0]
    guard = RateLimiter(1, lambda: now[0])
    assert guard.allow(42)
    assert not guard.allow(42)
    assert guard.allow(43)
    now[0] = 60
    assert guard.allow(42)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr("config.load_environment", lambda: None)
    # Do not let the developer's real environment affect config tests.
    from pathlib import Path
    for line in Path(".env.example").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            monkeypatch.delenv(line.split("=")[0], raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:fake")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-test-value")
    monkeypatch.setenv("ALLOWED_USER_IDS", "42, 43")
    return monkeypatch


def test_defaults_and_no_secret_repr(env):
    config = Config.from_env()
    assert config.allowed_user_ids == {42, 43}
    assert config.openai_model == "gpt-5.4-2026-03-05"
    assert config.reasoning_effort == "high"
    assert config.max_output_tokens == 16000
    assert config.request_timeout_seconds == 240
    assert config.default_language == "en" and config.default_mode == "watch"
    assert "secret-test-value" not in repr(config)
    assert "123456:fake" not in repr(config)
    assert config.ai_provider == "openai"
    assert config.ai_model == config.openai_model


@pytest.mark.parametrize("name,value", [("ALLOWED_USER_IDS", ""), ("ALLOWED_USER_IDS", "abc"), ("ALLOWED_USER_IDS", "-1"), ("MAX_HISTORY_MESSAGES", "1"), ("MAX_IMAGE_MB", "21"), ("DEFAULT_MODE", "long"), ("DEFAULT_LANGUAGE", "xx"), ("MAX_OUTPUT_TOKENS", "nan"), ("OPENAI_API_KEY", "")])
def test_invalid_config_fails_closed(env, name, value):
    env.setenv(name, value)
    with pytest.raises(ConfigError):
        Config.from_env()


def test_deepseek_requires_only_its_own_key(env):
    env.setenv("AI_PROVIDER", "deepseek")
    env.setenv("DEEPSEEK_API_KEY", "deepseek-secret-test")
    env.delenv("OPENAI_API_KEY")
    config = Config.from_env()
    assert config.ai_provider == "deepseek"
    assert config.ai_model == "deepseek-flash"
    assert config.ai_api_key == "deepseek-secret-test"
    assert config.ai_base_url == "https://api.deepseek.com"
    assert config.ai_reasoning_effort == "high"
    assert "deepseek-secret-test" not in repr(config)


def test_deepseek_never_falls_back_to_openai_key(env):
    env.setenv("AI_PROVIDER", "deepseek")
    with pytest.raises(ConfigError, match="DEEPSEEK_API_KEY"):
        Config.from_env()


@pytest.mark.parametrize("name,value", [("AI_PROVIDER", "unknown"), ("DEEPSEEK_MODEL", "deepseek-reasoner"), ("DEEPSEEK_REASONING_EFFORT", "unsupported")])
def test_bad_provider_settings_rejected(env, name, value):
    env.setenv("AI_PROVIDER", "deepseek")
    env.setenv("DEEPSEEK_API_KEY", "fake")
    env.setenv(name, value)
    with pytest.raises(ConfigError):
        Config.from_env()


def test_inactive_provider_settings_do_not_block_startup(env):
    env.setenv("DEEPSEEK_MODEL", "unused-model")
    env.setenv("DEEPSEEK_REASONING_EFFORT", "unused-effort")
    assert Config.from_env().ai_provider == "openai"
    env.setenv("AI_PROVIDER", "deepseek")
    env.setenv("DEEPSEEK_API_KEY", "fake")
    env.delenv("DEEPSEEK_MODEL")
    env.delenv("DEEPSEEK_REASONING_EFFORT")
    env.setenv("OPENAI_REASONING_EFFORT", "unused-effort")
    assert Config.from_env().ai_provider == "deepseek"
