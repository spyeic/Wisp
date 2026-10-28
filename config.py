"""Validated environment configuration; no secrets in repr or error messages."""
from dataclasses import dataclass, field
import os
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(ValueError):
    pass


def load_environment() -> None:
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value.startswith("your_"):
        raise ConfigError(f"Set {name} in .env.")
    return value


def integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        raise ConfigError(f"{name} must be an integer.") from None
    if not minimum <= value <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}.")
    return value


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str = field(repr=False)
    openai_api_key: str = field(repr=False)
    allowed_user_ids: frozenset[int]
    openai_model: str = "gpt-5.4-2026-03-05"
    ai_provider: str = "openai"
    deepseek_api_key: str = field(default="", repr=False)
    deepseek_model: str = "deepseek-flash"
    deepseek_reasoning_effort: str = "high"
    max_history_messages: int = 10
    max_history_chars: int = 48000
    max_history_images: int = 1
    history_ttl_seconds: int = 1800
    default_language: str = "en"
    default_mode: str = "watch"
    max_image_mb: int = 10
    max_image_pixels: int = 25000000
    max_text_chars: int = 6000
    requests_per_minute: int = 6
    request_timeout_seconds: int = 240
    max_output_tokens: int = 16000
    reasoning_effort: str = "high"
    message_interval_ms: int = 1100

    @property
    def ai_api_key(self) -> str:
        return self.deepseek_api_key if self.ai_provider == "deepseek" else self.openai_api_key

    @property
    def ai_model(self) -> str:
        return self.deepseek_model if self.ai_provider == "deepseek" else self.openai_model

    @property
    def ai_reasoning_effort(self) -> str:
        return self.deepseek_reasoning_effort if self.ai_provider == "deepseek" else self.reasoning_effort

    @property
    def ai_base_url(self) -> str:
        return {"openai": "https://api.openai.com/v1", "deepseek": "https://api.deepseek.com"}[self.ai_provider]

    @property
    def max_image_bytes(self) -> int:
        return self.max_image_mb * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Config":
        load_environment()
        token = required("TELEGRAM_BOT_TOKEN")
        provider = os.getenv("AI_PROVIDER", "openai").strip().lower()
        if provider not in {"openai", "deepseek"}:
            raise ConfigError("AI_PROVIDER must be openai or deepseek.")
        # Only the selected provider needs credentials; never fall back to another key.
        key = required("OPENAI_API_KEY") if provider == "openai" else os.getenv("OPENAI_API_KEY", "").strip()
        deepseek_key = required("DEEPSEEK_API_KEY") if provider == "deepseek" else os.getenv("DEEPSEEK_API_KEY", "").strip()
        try:
            raw = required("ALLOWED_USER_IDS")
            ids = frozenset(int(part.strip()) for part in raw.split(","))
            if not ids or any(uid <= 0 for uid in ids):
                raise ValueError
        except ValueError:
            raise ConfigError("ALLOWED_USER_IDS must contain positive numeric user IDs separated by commas.") from None
        language = os.getenv("DEFAULT_LANGUAGE", "en").strip().lower()
        if language not in {"en", "zh"}:
            raise ConfigError("DEFAULT_LANGUAGE must be en or zh.")
        mode = os.getenv("DEFAULT_MODE", "watch").strip().lower()
        if mode != "watch":
            raise ConfigError("DEFAULT_MODE must be watch.")
        effort = os.getenv("OPENAI_REASONING_EFFORT", "high").strip()
        if provider == "openai" and effort not in {"", "none", "low", "medium", "high", "xhigh", "max"}:
            raise ConfigError("Invalid OPENAI_REASONING_EFFORT.")
        model = os.getenv("OPENAI_MODEL", "gpt-5.4-2026-03-05").strip() or "gpt-5.4-2026-03-05"
        deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-flash").strip() or "deepseek-flash"
        deepseek_effort = os.getenv("DEEPSEEK_REASONING_EFFORT", "high").strip()
        if provider == "deepseek":
            if deepseek_model not in {"deepseek-flash", "deepseek-v4-pro"}:
                raise ConfigError("DEEPSEEK_MODEL must be deepseek-flash (images + text) or deepseek-v4-pro (text only).")
            if deepseek_effort not in {"", "none", "low", "high", "max"}:
                raise ConfigError("DEEPSEEK_REASONING_EFFORT must be none, low, high, max, or empty.")
        return cls(
            telegram_bot_token=token, openai_api_key=key, allowed_user_ids=ids,
            ai_provider=provider, deepseek_api_key=deepseek_key,
            deepseek_model=deepseek_model, deepseek_reasoning_effort=deepseek_effort,
            openai_model=model, default_language=language, default_mode=mode,
            reasoning_effort=effort,
            max_history_messages=integer("MAX_HISTORY_MESSAGES", 10, 2, 50),
            max_history_chars=integer("MAX_HISTORY_CHARS", 48000, 1000, 100000),
            max_history_images=integer("MAX_HISTORY_IMAGES", 1, 0, 3),
            history_ttl_seconds=integer("HISTORY_TTL_SECONDS", 1800, 60, 86400),
            max_image_mb=integer("MAX_IMAGE_MB", 10, 1, 20),
            max_image_pixels=integer("MAX_IMAGE_PIXELS", 25000000, 1000, 40000000),
            max_text_chars=integer("MAX_TEXT_CHARS", 6000, 100, 10000),
            requests_per_minute=integer("REQUESTS_PER_MINUTE", 6, 1, 60),
            request_timeout_seconds=integer("REQUEST_TIMEOUT_SECONDS", 240, 10, 600),
            max_output_tokens=integer("MAX_OUTPUT_TOKENS", 16000, 1000, 32000),
            message_interval_ms=integer("MESSAGE_INTERVAL_MS", 1100, 1000, 5000),
        )
