"""LLM-клиент: Anthropic SDK + Prompt Caching + retry + Effort Control.

`LLMError.code` — это ключ в `app/services/messages.py`. Хендлер в боте делает:

    try:
        text = await llm.complete(system=..., user=...)
    except LLMError as e:
        await update.message.reply_text(e.user_message)
        log.warning("LLM failed: %s", e.log_message)

Поддерживает Effort Control для оптимизации токен-траты.
"""
import json
import logging
from typing import Any, Literal

from anthropic import Anthropic, APIError, APIConnectionError, RateLimitError, APITimeoutError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings, get_settings
from app.services import alerts
from app.services.messages import get_user_message

log = logging.getLogger(__name__)


class LLMError(Exception):
    """Любая ошибка LLM-вызова. `code` маппится в русский текст для пользователя."""

    def __init__(self, code: str, log_message: str, *, is_critical: bool = False) -> None:
        super().__init__(log_message)
        self.code = code
        self.user_message = get_user_message(code)
        self.log_message = log_message
        self.is_critical = is_critical


_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
)


@retry(
    retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def _create_completion(client: Anthropic, **kwargs: Any) -> Any:
    return client.messages.create(**kwargs)


def _strip_json_fences(text: str) -> str:
    """Anthropic-модели иногда оборачивают JSON в ```json ... ```. Снимаем."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[: -3]
    return s.strip()


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self._settings = s
        self._client = Anthropic(api_key=s.anthropic_api_key)

    async def complete(
        self,
        *,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        model: str | None = None,
        effort: Literal["low", "medium", "high", "max"] = "high",
    ) -> str:
        """Complete a message with Effort Control.

        Args:
            system: System prompt
            user: User message
            json_mode: Return JSON (claude-opus-4-8 will validate it)
            temperature: Temperature (0.0-1.0)
            max_tokens: Max output tokens
            model: Model name override
            effort: Effort level for token optimization (low/medium/high/max)
                   - low: 50% fewer tokens, good for simple tasks
                   - medium: balanced
                   - high: better quality (default)
                   - max: best quality, Opus-tier only
        """
        s = self._settings

        messages = [
            {"role": "user", "content": user}
        ]

        # Build output_config with cache_control if enabled
        output_config: dict[str, Any] = {"effort": effort}

        # If caching enabled, add cache control to system prompt
        if s.enable_prompt_caching:
            system = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"}
                }
            ]

        kwargs: dict[str, Any] = {
            "model": model or s.model_name,
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens or 4000,
            "output_config": output_config,
            "thinking": {
                "type": "adaptive",
                "display": "omitted",
            },
        }

        try:
            resp = await _create_completion(self._client, **kwargs)
        except APITimeoutError as e:
            raise LLMError("llm_timeout", f"timeout: {e}") from e
        except APIConnectionError as e:
            raise LLMError("llm_connection", f"connection failed: {e}") from e
        except RateLimitError as e:
            raise LLMError("llm_rate_limit", f"rate limit: {e}") from e
        except APIError as e:
            if "401" in str(e) or "Unauthorized" in str(e):
                err = LLMError("llm_auth_error", f"401 auth: {e}", is_critical=True)
                await alerts.send_critical(f"Anthropic API key invalid: {e}")
                raise err from e
            if "403" in str(e):
                err = LLMError("llm_permission_denied", f"403: {e}", is_critical=True)
                await alerts.send_critical(f"Anthropic permission denied: {e}")
                raise err from e
            if "not found" in str(e).lower():
                err = LLMError("llm_model_not_found", f"404 model {kwargs['model']}: {e}", is_critical=True)
                await alerts.send_critical(f"Model not found: {kwargs['model']} ({e})")
                raise err from e
            if "moderation" in str(e).lower() or "policy" in str(e).lower():
                raise LLMError("llm_moderation", f"moderation: {e}") from e
            raise LLMError("llm_unknown", f"API error: {e}") from e
        except Exception as e:
            raise LLMError("llm_unknown", f"unexpected: {type(e).__name__}: {e}") from e

        if not resp.content or not resp.content[0].text:
            raise LLMError("llm_invalid_json", "empty response from LLM")

        text = resp.content[0].text
        log.info(
            "llm ok model=%s effort=%s in_tokens=%s out_tokens=%s",
            kwargs["model"],
            effort,
            resp.usage.input_tokens,
            resp.usage.output_tokens,
        )
        return text

    async def complete_json(self, **kw: Any) -> dict[str, Any]:
        # Ensure JSON validation
        kw.setdefault("effort", "medium")  # Medium effort for JSON tasks
        text = await self.complete(json_mode=True, **kw)
        cleaned = _strip_json_fences(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise LLMError(
                "llm_invalid_json", f"JSON parse failed, raw={text[:300]!r}"
            ) from e


_singleton: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _singleton
    if _singleton is None:
        _singleton = LLMClient()
    return _singleton
