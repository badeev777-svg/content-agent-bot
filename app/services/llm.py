"""LLM-клиент: OpenAI SDK → OpenRouter → Claude + Prompt Caching + retry.

`LLMError.code` — это ключ в `app/services/messages.py`. Хендлер в боте делает:

    try:
        text = await llm.complete(system=..., user=...)
    except LLMError as e:
        await update.message.reply_text(e.user_message)
        log.warning("LLM failed: %s", e.log_message)
"""
import json
import logging
from typing import Any, Literal

from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APITimeoutError, APIError
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
async def _create_completion(client: AsyncOpenAI, **kwargs: Any) -> Any:
    return await client.chat.completions.create(**kwargs)


def _strip_json_fences(text: str) -> str:
    """Модели иногда оборачивают JSON в ```json ... ```. Снимаем."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self._settings = s
        self._client = AsyncOpenAI(
            api_key=s.openrouter_api_key,
            base_url=s.openrouter_base_url,
        )

    async def complete(
        self,
        *,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        model: str | None = None,
        effort: Literal["low", "medium", "high", "max"] = "high",  # зарезервировано, не используется
    ) -> str:
        s = self._settings

        # Prompt Caching: OpenRouter проксирует cache_control для Anthropic-моделей
        if s.enable_prompt_caching:
            system_content: Any = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            system_content = system

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user},
        ]

        kwargs: dict[str, Any] = {
            "model": model or s.model_name,
            "messages": messages,
            "max_tokens": max_tokens or 4000,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            resp = await _create_completion(self._client, **kwargs)
        except APITimeoutError as e:
            raise LLMError("llm_timeout", f"timeout: {e}") from e
        except APIConnectionError as e:
            raise LLMError("llm_connection", f"connection failed: {e}") from e
        except RateLimitError as e:
            raise LLMError("llm_rate_limit", f"rate limit: {e}") from e
        except APIError as e:
            status = getattr(e, "status_code", None)
            if status == 401 or "Unauthorized" in str(e):
                err = LLMError("llm_auth_error", f"401 auth: {e}", is_critical=True)
                await alerts.send_critical(f"OpenRouter API key invalid: {e}")
                raise err from e
            if status == 403:
                err = LLMError("llm_permission_denied", f"403: {e}", is_critical=True)
                await alerts.send_critical(f"OpenRouter permission denied: {e}")
                raise err from e
            if status == 404 or "not found" in str(e).lower():
                err = LLMError("llm_model_not_found", f"404 model {kwargs['model']}: {e}", is_critical=True)
                await alerts.send_critical(f"Model not found: {kwargs['model']} ({e})")
                raise err from e
            if "moderation" in str(e).lower() or "policy" in str(e).lower():
                raise LLMError("llm_moderation", f"moderation: {e}") from e
            raise LLMError("llm_unknown", f"API error: {e}") from e
        except Exception as e:
            raise LLMError("llm_unknown", f"unexpected: {type(e).__name__}: {e}") from e

        if not resp.choices or not resp.choices[0].message.content:
            raise LLMError("llm_invalid_json", "empty response from LLM")

        text = resp.choices[0].message.content
        log.info(
            "llm ok model=%s in_tokens=%s out_tokens=%s",
            kwargs["model"],
            resp.usage.prompt_tokens if resp.usage else "?",
            resp.usage.completion_tokens if resp.usage else "?",
        )
        return text

    async def complete_json(self, **kw: Any) -> dict[str, Any]:
        kw.setdefault("effort", "medium")
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
