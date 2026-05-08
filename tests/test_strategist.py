"""Strategist Agent: схема, инжекция профиля, обработка плохих ответов LLM."""
from typing import Any

import pytest
from pydantic import ValidationError

from app.agents import strategist
from app.agents.scraper import ScrapedContent
from app.agents.schemas import WeekPlan
from app.agents.strategist import _build_user_prompt, plan_week
from app.db.models import Tone, UserProfile
from app.services.llm import LLMError


def _make_profile(niche: str = "маркетинг") -> UserProfile:
    p = UserProfile(
        user_id=1,
        niche=niche,
        tone=Tone.FRIENDLY,
        forbidden=["политика"],
        formats=["Списки", "Истории"],
        example_posts=["Пример моего поста."],
        style_notes="люблю короткие предложения",
    )
    return p


def _make_scraped() -> ScrapedContent:
    return ScrapedContent(
        url="https://example.com/post",
        title="Гайд по найму",
        theme="как нанимать в небольшую команду",
        raw_text="полный текст...",
        theses=["Найм — это маркетинг", "Скорость > идеал", "Тестовое только в крайнем случае"],
    )


def _good_plan_json() -> dict[str, Any]:
    return {
        "theme": "Найм без боли",
        "days": [
            {"day": 1, "post_type": "engagement", "angle": "миф о тестовом задании", "hook": "Тестовое — зло. Почему?"},
            {"day": 2, "post_type": "engagement", "angle": "найм как маркетинг", "hook": "Ваш джоб-постинг — это лендинг"},
            {"day": 3, "post_type": "expertise", "angle": "чек-лист собеседования", "hook": "5 вопросов которые экономят месяц"},
            {"day": 4, "post_type": "expertise", "angle": "разбор плохого описания вакансии", "hook": "Почему на ваше «гибкость и драйв» никто не идёт"},
            {"day": 5, "post_type": "trust", "angle": "история провального найма", "hook": "Я нанял не того человека за 200к"},
            {"day": 6, "post_type": "trust", "angle": "результат после изменений", "hook": "Срок найма с 3 месяцев до 3 недель"},
            {"day": 7, "post_type": "sale", "angle": "приглашение на консультацию", "hook": "Распакую ваш найм за час"},
        ],
    }


# ── _build_user_prompt: профиль попадает в текст
def test_user_prompt_includes_profile() -> None:
    prompt = _build_user_prompt(_make_scraped(), _make_profile(), ["telegram", "vk"])
    assert "маркетинг" in prompt
    assert "friendly" in prompt
    assert "политика" in prompt
    assert "Списки" in prompt
    assert "telegram" in prompt and "vk" in prompt
    assert "Найм" in prompt
    assert "Скорость > идеал" in prompt


def test_user_prompt_handles_no_profile() -> None:
    prompt = _build_user_prompt(_make_scraped(), None, ["telegram"])
    assert "Профиль не настроен" in prompt


def test_user_prompt_handles_empty_theses() -> None:
    scraped = ScrapedContent(url="https://x", title="", theses=[])
    prompt = _build_user_prompt(scraped, _make_profile(), ["telegram"])
    assert "тезисы не извлечены" in prompt


# ── WeekPlan: Pydantic-валидация
def test_week_plan_valid() -> None:
    plan = WeekPlan.model_validate(_good_plan_json())
    assert len(plan.days) == 7
    assert [d.day for d in plan.days] == [1, 2, 3, 4, 5, 6, 7]
    assert plan.days[0].post_type.value == "engagement"
    assert plan.days[6].post_type.value == "sale"


def test_week_plan_rejects_wrong_day_count() -> None:
    bad = _good_plan_json()
    bad["days"] = bad["days"][:5]
    with pytest.raises(ValidationError):
        WeekPlan.model_validate(bad)


def test_week_plan_rejects_duplicate_days() -> None:
    bad = _good_plan_json()
    bad["days"][1]["day"] = 1  # два дня с day=1
    with pytest.raises(ValidationError):
        WeekPlan.model_validate(bad)


def test_week_plan_rejects_bad_post_type() -> None:
    bad = _good_plan_json()
    bad["days"][0]["post_type"] = "lulz"
    with pytest.raises(ValidationError):
        WeekPlan.model_validate(bad)


# ── plan_week: успешный путь
class _FakeLLM:
    def __init__(self, response: dict[str, Any] | Exception) -> None:
        self._response = response

    async def complete_json(self, **kw: Any) -> dict[str, Any]:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


@pytest.mark.asyncio
async def test_plan_week_returns_validated_plan() -> None:
    llm = _FakeLLM(_good_plan_json())
    plan = await plan_week(_make_scraped(), _make_profile(), ["telegram"], client=llm)  # type: ignore[arg-type]
    assert isinstance(plan, WeekPlan)
    assert len(plan.days) == 7
    assert plan.theme == "Найм без боли"


@pytest.mark.asyncio
async def test_plan_week_translates_validation_to_llm_error() -> None:
    bad = _good_plan_json()
    bad["days"] = bad["days"][:3]  # неполный массив
    llm = _FakeLLM(bad)
    with pytest.raises(LLMError) as ei:
        await plan_week(_make_scraped(), _make_profile(), ["telegram"], client=llm)  # type: ignore[arg-type]
    assert ei.value.code == "llm_invalid_schema"


@pytest.mark.asyncio
async def test_plan_week_propagates_llm_error() -> None:
    llm = _FakeLLM(LLMError("llm_timeout", "fake"))
    with pytest.raises(LLMError) as ei:
        await plan_week(_make_scraped(), _make_profile(), ["telegram"], client=llm)  # type: ignore[arg-type]
    assert ei.value.code == "llm_timeout"
