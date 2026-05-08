"""Copywriter Agent: маппинг платформ → промпты, валидация, нормализация."""
from typing import Any

import pytest
from pydantic import ValidationError

from app.agents import copywriter
from app.agents.copywriter import _build_user_prompt, _load_prompt, write_post
from app.agents.schemas import DayPlan, GeneratedPost
from app.db.models import Platform, PostType, Tone, UserProfile
from app.services.llm import LLMError


def _profile() -> UserProfile:
    return UserProfile(
        user_id=1,
        niche="фитнес для женщин 30+",
        tone=Tone.FRIENDLY,
        forbidden=["пластика", "диеты-голодовки"],
        formats=["Истории"],
    )


def _day_plan() -> DayPlan:
    return DayPlan(
        day=3,
        post_type=PostType.EXPERTISE,
        angle="миф о том, что силовые делают женщин «мужеподобными»",
        hook="«Я не хочу качаться» — самый дорогой миф фитнеса для женщин",
        rationale="развенчание мифа = доверие к экспертизе",
    )


# ── Все промпты существуют и грузятся
@pytest.mark.parametrize(
    "platform", [Platform.TELEGRAM, Platform.VK, Platform.STORIES]
)
def test_prompt_loads(platform: Platform) -> None:
    prompt = _load_prompt(platform)
    assert len(prompt) > 200
    assert "JSON" in prompt or "json" in prompt


# ── User-prompt: профиль и параметры дня попадают в текст
def test_user_prompt_contains_profile_and_day_data() -> None:
    p = _build_user_prompt(day_plan=_day_plan(), profile=_profile(), week_theme="Силовые без страха")
    assert "фитнес для женщин 30+" in p
    assert "friendly" in p
    assert "пластика" in p
    assert "силовые делают женщин" in p
    assert "expertise" in p
    assert "Силовые без страха" in p
    assert "День 3" in p


def test_user_prompt_works_without_profile() -> None:
    p = _build_user_prompt(day_plan=_day_plan(), profile=None, week_theme="Тема")
    assert "Профиль не настроен" in p
    assert "expertise" in p


# ── GeneratedPost: схема и нормализация хэштегов
def test_generated_post_normalizes_hashtags() -> None:
    post = GeneratedPost.model_validate({
        "content": "Это пост достаточной длины для прохождения валидации схемы.",
        "hashtags": ["smm", "#фитнес", "  ", "сила воли"],
        "cta": "напиши в комменты",
        "rec_time": "10:00",
    })
    assert post.hashtags == ["#smm", "#фитнес", "#силаволи"]


def test_generated_post_rejects_short_content() -> None:
    with pytest.raises(ValidationError):
        GeneratedPost.model_validate({"content": "ой"})


def test_generated_post_allows_empty_hashtags() -> None:
    post = GeneratedPost.model_validate({
        "content": "Слайд 1\n---\nСлайд 2\n---\nСлайд 3\n---\nСлайд 4\n---\nСлайд 5",
        "hashtags": [],
        "cta": "свайп вверх",
        "rec_time": "20:00",
    })
    assert post.hashtags == []


# ── write_post: успешный путь
class _FakeLLM:
    def __init__(self, response: dict[str, Any] | Exception) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    async def complete_json(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(kw)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _good_post_json() -> dict[str, Any]:
    return {
        "content": (
            "<b>«Я не хочу качаться»</b> — самый дорогой миф.\n\n"
            "На деле от силовых женщины не становятся мужеподобными — для этого нужна "
            "тестостероновая поддержка и годы специализации. А вот результат, к которому "
            "хочется большинство, — упругое тело, прямая осанка и энергия — именно от штанги."
        ),
        "hashtags": ["#фитнес30+", "#силовые", "#женскийфитнес"],
        "cta": "напиши в комментариях, какая твоя главная отговорка от силовых",
        "rec_time": "19:00",
    }


@pytest.mark.asyncio
async def test_write_post_returns_validated_post() -> None:
    llm = _FakeLLM(_good_post_json())
    post = await write_post(
        day_plan=_day_plan(),
        platform=Platform.TELEGRAM,
        profile=_profile(),
        week_theme="Силовые без страха",
        client=llm,  # type: ignore[arg-type]
    )
    assert isinstance(post, GeneratedPost)
    assert "Я не хочу качаться" in post.content
    assert all(h.startswith("#") for h in post.hashtags)


@pytest.mark.asyncio
async def test_write_post_uses_correct_prompt_per_platform() -> None:
    llm = _FakeLLM(_good_post_json())
    await write_post(
        day_plan=_day_plan(), platform=Platform.STORIES,
        profile=_profile(), week_theme="X", client=llm,  # type: ignore[arg-type]
    )
    sent_system = llm.calls[0]["system"]
    assert "5 слайдов" in sent_system or "слайда" in sent_system


@pytest.mark.asyncio
async def test_write_post_translates_validation_to_llm_error() -> None:
    llm = _FakeLLM({"content": "x", "hashtags": [], "cta": "", "rec_time": ""})  # too short
    with pytest.raises(LLMError) as ei:
        await write_post(
            day_plan=_day_plan(), platform=Platform.TELEGRAM,
            profile=_profile(), week_theme="X", client=llm,  # type: ignore[arg-type]
        )
    assert ei.value.code == "llm_invalid_schema"


@pytest.mark.asyncio
async def test_write_post_propagates_llm_error() -> None:
    llm = _FakeLLM(LLMError("llm_rate_limit", "fake"))
    with pytest.raises(LLMError) as ei:
        await write_post(
            day_plan=_day_plan(), platform=Platform.TELEGRAM,
            profile=_profile(), week_theme="X", client=llm,  # type: ignore[arg-type]
        )
    assert ei.value.code == "llm_rate_limit"
