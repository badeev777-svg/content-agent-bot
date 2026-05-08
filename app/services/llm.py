"""LLM-клиент: OpenRouter через openai SDK + Prompt Caching + retry + перевод ошибок в LLMError.

`LLMError.code` — это ключ в `app/services/messages.py`. Хендлер в боте делает:

    try:
        text = await llm.complete(system=..., user=...)
    except LLMError as e:
        await update.message.reply_text(e.user_message)
        log.warning("LLM failed: %s", e.log_message)

Всё остальное — внутренняя кухня (retry, caching, маппинг кодов).
"""
import json
import logging
from typing import Any

import openai
from openai import AsyncOpenAI
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
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
)


@retry(
    retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def _create_completion(client: AsyncOpenAI, **kwargs: Any) -> Any:
    return await client.chat.completions.create(**kwargs)


def _build_messages(
    system: str, user: str, *, cache_system: bool
) -> list[dict[str, Any]]:
    """Собрать messages с опциональным cache_control на system prompt.

    Anthropic-модели через OpenRouter поддерживают `cache_control: ephemeral`
    в content blocks — кэшируется system_prompt между вызовами.
    """
    if cache_system:
        sys_content: Any = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
    else:
        sys_content = system
    return [
        {"role": "system", "content": sys_content},
        {"role": "user", "content": user},
    ]


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self._settings = s
        self._client = AsyncOpenAI(
            api_key=s.openrouter_api_key,
            base_url=s.openrouter_base_url,
            default_headers={
                "HTTP-Referer": s.openrouter_app_url,
                "X-Title": s.openrouter_app_name,
            },
            timeout=60.0,
            max_retries=0,  # ретраим сами через tenacity
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
    ) -> str:
        s = self._settings
        messages = _build_messages(system, user, cache_system=s.enable_prompt_caching)

        kwargs: dict[str, Any] = {
            "model": model or s.model_name,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            resp = await _create_completion(self._client, **kwargs)
        except openai.APITimeoutError as e:
            raise LLMError("llm_timeout", f"timeout: {e}") from e
        except openai.APIConnectionError as e:
            raise LLMError("llm_connection", f"connection failed: {e}") from e
        except openai.RateLimitError as e:
            raise LLMError("llm_rate_limit", f"rate limit: {e}") from e
        except openai.AuthenticationError as e:
            err = LLMError("llm_auth_error", f"401 auth: {e}", is_critical=True)
            await alerts.send_critical(f"OpenRouter API key invalid: {e}")
            raise err from e
        except openai.PermissionDeniedError as e:
            err = LLMError("llm_permission_denied", f"403: {e}", is_critical=True)
            await alerts.send_critical(f"OpenRouter permission denied: {e}")
            raise err from e
        except openai.NotFoundError as e:
            err = LLMError("llm_model_not_found", f"404 model {kwargs['model']}: {e}", is_critical=True)
            await alerts.send_critical(f"Model not found on OpenRouter: {kwargs['model']} ({e})")
            raise err from e
        except openai.BadRequestError as e:
            msg = str(e).lower()
            if "moderation" in msg or "content_filter" in msg or "policy" in msg:
                raise LLMError("llm_moderation", f"moderation: {e}") from e
            raise LLMError("llm_bad_request", f"400: {e}") from e
        except openai.APIStatusError as e:
            code = getattr(e, "status_code", None)
            if code == 402:
                err = LLMError("llm_no_credits", f"402 out of credits: {e}", is_critical=True)
                await alerts.send_critical(f"OpenRouter: out of credits ({e})")
                raise err from e
            if code == 502:
                raise LLMError("llm_upstream_down", f"502 upstream down: {e}") from e
            if code in {503, 529}:
                raise LLMError("llm_overloaded", f"{code} overloaded: {e}") from e
            raise LLMError("llm_unknown", f"unexpected status {code}: {e}") from e
        except LLMError:
            raise
        except Exception as e:
            raise LLMError("llm_unknown", f"unexpected: {type(e).__name__}: {e}") from e

        text = resp.choices[0].message.content or ""
        if not text:
            raise LLMError("llm_invalid_json", "empty response from LLM")
        log.info(
            "llm ok model=%s in_tokens=%s out_tokens=%s",
            kwargs["model"],
            getattr(resp.usage, "prompt_tokens", "?"),
            getattr(resp.usage, "completion_tokens", "?"),
        )
        return text

    async def complete_json(self, **kw: Any) -> dict[str, Any]:
        text = await self.complete(json_mode=True, **kw)
        cleaned = _strip_json_fences(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise LLMError(
                "llm_invalid_json", f"JSON parse failed, raw={text[:300]!r}"
            ) from e


def _strip_json_fences(text: str) -> str:
    """Anthropic-модели иногда оборачивают JSON в ```json ... ```. Снимаем."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[: -3]
    return s.strip()


_singleton: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _singleton
    if _singleton is None:
        _singleton = LLMClient()
    return _singleton
