"""Тесты LLM-клиента: маппинг ошибок openai SDK → LLMError с правильным кодом."""
import json

import httpx
import openai
import pytest

from app.services import alerts, llm
from app.services.llm import LLMClient, LLMError, _build_messages
from app.services.messages import USER_MESSAGES


@pytest.fixture(autouse=True)
def _no_alerts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Алерты — побочный эффект (HTTP), мокаем."""
    sent: list[str] = []

    async def fake_send(text: str) -> None:
        sent.append(text)

    monkeypatch.setattr(alerts, "send_critical", fake_send)


@pytest.fixture
def client() -> LLMClient:
    return LLMClient()


def _fake_response(status: int) -> httpx.Response:
    return httpx.Response(status_code=status, request=httpx.Request("POST", "https://x"))


def _patch_create(monkeypatch: pytest.MonkeyPatch, raiser):
    """Заменить _create_completion (с retry-декоратором) на функцию, бросающую нужное."""
    async def fake(_client, **kw):
        raise raiser()

    monkeypatch.setattr(llm, "_create_completion", fake)


# ── messages.py: ключи существуют для всех LLM-кодов
def test_all_llm_codes_have_translations() -> None:
    required = {
        "llm_connection", "llm_timeout", "llm_rate_limit", "llm_overloaded",
        "llm_no_credits", "llm_upstream_down", "llm_bad_request", "llm_auth_error",
        "llm_permission_denied", "llm_model_not_found", "llm_moderation",
        "llm_invalid_json", "llm_invalid_schema", "llm_unknown",
    }
    assert required.issubset(USER_MESSAGES.keys())


# ── prompt caching: cache_control добавляется в system block
def test_build_messages_with_cache() -> None:
    msgs = _build_messages("you are X", "hi", cache_system=True)
    assert msgs[0]["role"] == "system"
    assert isinstance(msgs[0]["content"], list)
    assert msgs[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert msgs[1] == {"role": "user", "content": "hi"}


def test_build_messages_without_cache() -> None:
    msgs = _build_messages("you are X", "hi", cache_system=False)
    assert msgs[0] == {"role": "system", "content": "you are X"}


# ── Маппинг каждой ошибки openai SDK в LLMError с правильным кодом
@pytest.mark.asyncio
async def test_connection_error_maps(client, monkeypatch):
    def raiser():
        return openai.APIConnectionError(request=httpx.Request("POST", "https://x"))
    _patch_create(monkeypatch, raiser)
    with pytest.raises(LLMError) as ei:
        await client.complete(system="s", user="u")
    assert ei.value.code == "llm_connection"
    assert "Не могу связаться" in ei.value.user_message


@pytest.mark.asyncio
async def test_timeout_maps(client, monkeypatch):
    def raiser():
        return openai.APITimeoutError(request=httpx.Request("POST", "https://x"))
    _patch_create(monkeypatch, raiser)
    with pytest.raises(LLMError) as ei:
        await client.complete(system="s", user="u")
    assert ei.value.code == "llm_timeout"


@pytest.mark.asyncio
async def test_rate_limit_maps(client, monkeypatch):
    def raiser():
        return openai.RateLimitError(
            "rate limited", response=_fake_response(429), body=None
        )
    _patch_create(monkeypatch, raiser)
    with pytest.raises(LLMError) as ei:
        await client.complete(system="s", user="u")
    assert ei.value.code == "llm_rate_limit"


@pytest.mark.asyncio
async def test_auth_error_is_critical(client, monkeypatch):
    sent: list[str] = []

    async def fake_send(text: str) -> None:
        sent.append(text)

    monkeypatch.setattr(alerts, "send_critical", fake_send)

    def raiser():
        return openai.AuthenticationError(
            "bad key", response=_fake_response(401), body=None
        )
    _patch_create(monkeypatch, raiser)
    with pytest.raises(LLMError) as ei:
        await client.complete(system="s", user="u")
    assert ei.value.code == "llm_auth_error"
    assert ei.value.is_critical is True
    assert sent and "API key invalid" in sent[0]


@pytest.mark.asyncio
async def test_permission_denied_is_critical(client, monkeypatch):
    def raiser():
        return openai.PermissionDeniedError(
            "forbidden", response=_fake_response(403), body=None
        )
    _patch_create(monkeypatch, raiser)
    with pytest.raises(LLMError) as ei:
        await client.complete(system="s", user="u")
    assert ei.value.code == "llm_permission_denied"
    assert ei.value.is_critical is True


@pytest.mark.asyncio
async def test_not_found_is_critical(client, monkeypatch):
    def raiser():
        return openai.NotFoundError(
            "model not found", response=_fake_response(404), body=None
        )
    _patch_create(monkeypatch, raiser)
    with pytest.raises(LLMError) as ei:
        await client.complete(system="s", user="u")
    assert ei.value.code == "llm_model_not_found"
    assert ei.value.is_critical is True


@pytest.mark.asyncio
async def test_bad_request_plain(client, monkeypatch):
    def raiser():
        return openai.BadRequestError(
            "invalid params", response=_fake_response(400), body=None
        )
    _patch_create(monkeypatch, raiser)
    with pytest.raises(LLMError) as ei:
        await client.complete(system="s", user="u")
    assert ei.value.code == "llm_bad_request"


@pytest.mark.asyncio
async def test_bad_request_moderation_translates_specifically(client, monkeypatch):
    def raiser():
        return openai.BadRequestError(
            "blocked by content_filter policy", response=_fake_response(400), body=None
        )
    _patch_create(monkeypatch, raiser)
    with pytest.raises(LLMError) as ei:
        await client.complete(system="s", user="u")
    assert ei.value.code == "llm_moderation"


@pytest.mark.asyncio
async def test_402_no_credits_is_critical(client, monkeypatch):
    def raiser():
        return openai.APIStatusError(
            "out of credits", response=_fake_response(402), body=None
        )
    _patch_create(monkeypatch, raiser)
    with pytest.raises(LLMError) as ei:
        await client.complete(system="s", user="u")
    assert ei.value.code == "llm_no_credits"
    assert ei.value.is_critical is True


@pytest.mark.asyncio
async def test_502_upstream_down(client, monkeypatch):
    def raiser():
        return openai.APIStatusError(
            "bad gateway", response=_fake_response(502), body=None
        )
    _patch_create(monkeypatch, raiser)
    with pytest.raises(LLMError) as ei:
        await client.complete(system="s", user="u")
    assert ei.value.code == "llm_upstream_down"


@pytest.mark.asyncio
async def test_529_overloaded(client, monkeypatch):
    def raiser():
        return openai.APIStatusError(
            "overloaded", response=_fake_response(529), body=None
        )
    _patch_create(monkeypatch, raiser)
    with pytest.raises(LLMError) as ei:
        await client.complete(system="s", user="u")
    assert ei.value.code == "llm_overloaded"


# ── Успешный ответ
@pytest.mark.asyncio
async def test_complete_success(client, monkeypatch):
    class FakeMsg:
        content = "Hello there!"

    class FakeChoice:
        message = FakeMsg()

    class FakeUsage:
        prompt_tokens = 5
        completion_tokens = 3

    class FakeResp:
        choices = [FakeChoice()]
        usage = FakeUsage()

    async def fake_create(_c, **kw):
        return FakeResp()

    monkeypatch.setattr(llm, "_create_completion", fake_create)
    text = await client.complete(system="be helpful", user="hi")
    assert text == "Hello there!"


@pytest.mark.asyncio
async def test_complete_empty_response_fails(client, monkeypatch):
    class FakeMsg: content = ""
    class FakeChoice: message = FakeMsg()
    class FakeResp:
        choices = [FakeChoice()]
        usage = type("U", (), {"prompt_tokens": 0, "completion_tokens": 0})()

    async def fake_create(_c, **kw): return FakeResp()
    monkeypatch.setattr(llm, "_create_completion", fake_create)
    with pytest.raises(LLMError) as ei:
        await client.complete(system="s", user="u")
    assert ei.value.code == "llm_invalid_json"


# ── complete_json парсит и валидирует
@pytest.mark.asyncio
async def test_complete_json_parses(client, monkeypatch):
    class FakeMsg: content = json.dumps({"day": 1, "type": "engagement"})
    class FakeChoice: message = FakeMsg()
    class FakeResp:
        choices = [FakeChoice()]
        usage = type("U", (), {"prompt_tokens": 0, "completion_tokens": 0})()

    async def fake_create(_c, **kw): return FakeResp()
    monkeypatch.setattr(llm, "_create_completion", fake_create)
    data = await client.complete_json(system="s", user="u")
    assert data == {"day": 1, "type": "engagement"}


@pytest.mark.asyncio
async def test_complete_json_strips_markdown_fences(client, monkeypatch):
    """Anthropic-модели через OpenRouter иногда оборачивают JSON в ```json ... ```."""
    fenced = '```json\n{"day": 1, "title": "x"}\n```'

    class FakeMsg: content = fenced
    class FakeChoice: message = FakeMsg()
    class FakeResp:
        choices = [FakeChoice()]
        usage = type("U", (), {"prompt_tokens": 0, "completion_tokens": 0})()

    async def fake_create(_c, **kw): return FakeResp()
    monkeypatch.setattr(llm, "_create_completion", fake_create)
    data = await client.complete_json(system="s", user="u")
    assert data == {"day": 1, "title": "x"}


@pytest.mark.asyncio
async def test_complete_json_bad_json_fails(client, monkeypatch):
    class FakeMsg: content = "это не json {"
    class FakeChoice: message = FakeMsg()
    class FakeResp:
        choices = [FakeChoice()]
        usage = type("U", (), {"prompt_tokens": 0, "completion_tokens": 0})()

    async def fake_create(_c, **kw): return FakeResp()
    monkeypatch.setattr(llm, "_create_completion", fake_create)
    with pytest.raises(LLMError) as ei:
        await client.complete_json(system="s", user="u")
    assert ei.value.code == "llm_invalid_json"


# ── catch-all: неизвестная ошибка тоже не уходит наружу
@pytest.mark.asyncio
async def test_unknown_exception_is_caught(client, monkeypatch):
    def raiser(): return RuntimeError("unexpected boom")
    _patch_create(monkeypatch, raiser)
    with pytest.raises(LLMError) as ei:
        await client.complete(system="s", user="u")
    assert ei.value.code == "llm_unknown"
