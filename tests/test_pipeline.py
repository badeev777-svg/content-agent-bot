"""Pipeline orchestrator: scrape → strategist → copywriter (parallel) → DB."""
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.scraper import ScrapedContent, ScraperError
from app.agents.schemas import DayPlan, GeneratedPost, WeekPlan
from app.db import crud
from app.db.models import Platform, PostType, Tone, UserProfile
from app.services.llm import LLMError
from app.services.pipeline import generate_plan


def _profile() -> UserProfile:
    return UserProfile(
        user_id=1,
        niche="фитнес для женщин 30+",
        tone=Tone.FRIENDLY,
        forbidden=[],
        formats=["Истории"],
    )


def _scraped() -> ScrapedContent:
    return ScrapedContent(
        url="https://example.com/article",
        title="Статья",
        theme="Силовые без страха",
        raw_text="x",
        theses=["тезис 1", "тезис 2"],
    )


def _week_plan() -> WeekPlan:
    return WeekPlan(
        theme="Силовые без страха",
        days=[
            DayPlan(
                day=d,
                post_type=PostType.EXPERTISE,
                angle=f"angle for day {d} ipsum lorem",
                hook=f"hook day {d}",
            )
            for d in range(1, 8)
        ],
    )


def _make_post(day: int, platform: Platform) -> GeneratedPost:
    return GeneratedPost(
        content=f"Пост дня {day} платформа {platform.value} — содержание",
        hashtags=[f"#день{day}"],
        cta="Подпишись",
        rec_time="10:00",
    )


# ── Happy path: всё сохраняется ровно 7 × N постов
@pytest.mark.asyncio
async def test_pipeline_happy_path(session: AsyncSession) -> None:
    await crud.get_or_create_user(session, telegram_id=42)
    await session.commit()

    async def fake_scrape(url: str) -> ScrapedContent:
        assert url == "https://example.com/article"
        return _scraped()

    async def fake_plan_week(scraped: Any, profile: Any, platforms: list[str]) -> WeekPlan:
        assert platforms == ["telegram", "vk"]
        return _week_plan()

    async def fake_write_post(
        *, day_plan: DayPlan, platform: Platform, profile: Any, week_theme: str
    ) -> GeneratedPost:
        assert week_theme == "Силовые без страха"
        return _make_post(day_plan.day, platform)

    result = await generate_plan(
        session,
        user_id=42,
        url="https://example.com/article",
        platforms=[Platform.TELEGRAM, Platform.VK],
        profile=_profile(),
        scrape_fn=fake_scrape,
        plan_week_fn=fake_plan_week,
        write_post_fn=fake_write_post,
    )

    assert result.total_posts == 14
    assert result.failed_posts == 0
    assert len(result.plan.posts) == 14
    assert result.plan.platforms == ["telegram", "vk"]
    assert result.plan.source_summary == "Силовые без страха"

    days = sorted({p.day for p in result.plan.posts})
    assert days == list(range(1, 8))


# ── Частичный отказ: 2 поста упали, остальные сохранены, exception не вылетает
@pytest.mark.asyncio
async def test_pipeline_partial_copywriter_failure(session: AsyncSession) -> None:
    await crud.get_or_create_user(session, telegram_id=42)
    await session.commit()

    async def fake_scrape(url: str) -> ScrapedContent:
        return _scraped()

    async def fake_plan_week(scraped: Any, profile: Any, platforms: list[str]) -> WeekPlan:
        return _week_plan()

    fail_days = {3, 5}

    async def fake_write_post(
        *, day_plan: DayPlan, platform: Platform, profile: Any, week_theme: str
    ) -> GeneratedPost:
        if day_plan.day in fail_days and platform == Platform.TELEGRAM:
            raise LLMError("llm_invalid_schema", "boom")
        return _make_post(day_plan.day, platform)

    result = await generate_plan(
        session,
        user_id=42,
        url="https://example.com/article",
        platforms=[Platform.TELEGRAM, Platform.VK],
        profile=_profile(),
        scrape_fn=fake_scrape,
        plan_week_fn=fake_plan_week,
        write_post_fn=fake_write_post,
    )

    assert result.total_posts == 14
    assert result.failed_posts == 2
    assert len(result.plan.posts) == 12

    saved_keys = {(p.day, p.platform) for p in result.plan.posts}
    assert (3, Platform.TELEGRAM) not in saved_keys
    assert (5, Platform.TELEGRAM) not in saved_keys
    assert (3, Platform.VK) in saved_keys
    assert (5, Platform.VK) in saved_keys


# ── Скрейпер упал — пайплайн пробрасывает исключение, ничего не сохранено
@pytest.mark.asyncio
async def test_pipeline_scraper_error_bubbles_up(session: AsyncSession) -> None:
    await crud.get_or_create_user(session, telegram_id=42)
    await session.commit()

    async def boom_scrape(url: str) -> ScrapedContent:
        raise ScraperError("not_found", "404")

    async def unused_plan(*a: Any, **k: Any) -> WeekPlan:
        raise AssertionError("strategist must not be called")

    async def unused_write(*a: Any, **k: Any) -> GeneratedPost:
        raise AssertionError("copywriter must not be called")

    with pytest.raises(ScraperError):
        await generate_plan(
            session,
            user_id=42,
            url="https://example.com/missing",
            platforms=[Platform.TELEGRAM],
            profile=None,
            scrape_fn=boom_scrape,
            plan_week_fn=unused_plan,
            write_post_fn=unused_write,
        )

    plans = await crud.get_recent_plans(session, telegram_id=42)
    assert plans == []


# ── Стратег упал — exception наружу
@pytest.mark.asyncio
async def test_pipeline_strategist_error_bubbles_up(session: AsyncSession) -> None:
    await crud.get_or_create_user(session, telegram_id=42)
    await session.commit()

    async def fake_scrape(url: str) -> ScrapedContent:
        return _scraped()

    async def boom_plan(*a: Any, **k: Any) -> WeekPlan:
        raise LLMError("llm_invalid_schema", "boom")

    async def unused_write(*a: Any, **k: Any) -> GeneratedPost:
        raise AssertionError("copywriter must not be called")

    with pytest.raises(LLMError):
        await generate_plan(
            session,
            user_id=42,
            url="https://example.com/article",
            platforms=[Platform.TELEGRAM],
            profile=None,
            scrape_fn=fake_scrape,
            plan_week_fn=boom_plan,
            write_post_fn=unused_write,
        )

    plans = await crud.get_recent_plans(session, telegram_id=42)
    assert plans == []


# ── Пустой список платформ — отказ на валидации
@pytest.mark.asyncio
async def test_pipeline_empty_platforms_raises(session: AsyncSession) -> None:
    await crud.get_or_create_user(session, telegram_id=42)
    await session.commit()

    async def unused(*a: Any, **k: Any) -> Any:
        raise AssertionError("must not be called")

    with pytest.raises(ValueError, match="platforms"):
        await generate_plan(
            session,
            user_id=42,
            url="https://example.com/article",
            platforms=[],
            profile=None,
            scrape_fn=unused,
            plan_week_fn=unused,
            write_post_fn=unused,
        )


# ── Concurrency: семафор реально ограничивает параллельность
@pytest.mark.asyncio
async def test_pipeline_respects_concurrency_limit(session: AsyncSession) -> None:
    import asyncio as _asyncio

    await crud.get_or_create_user(session, telegram_id=42)
    await session.commit()

    in_flight = 0
    peak = 0

    async def fake_scrape(url: str) -> ScrapedContent:
        return _scraped()

    async def fake_plan_week(*a: Any, **k: Any) -> WeekPlan:
        return _week_plan()

    async def fake_write_post(
        *, day_plan: DayPlan, platform: Platform, profile: Any, week_theme: str
    ) -> GeneratedPost:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await _asyncio.sleep(0.01)
        in_flight -= 1
        return _make_post(day_plan.day, platform)

    result = await generate_plan(
        session,
        user_id=42,
        url="https://example.com/article",
        platforms=[Platform.TELEGRAM, Platform.VK, Platform.STORIES],
        profile=None,
        concurrency=3,
        scrape_fn=fake_scrape,
        plan_week_fn=fake_plan_week,
        write_post_fn=fake_write_post,
    )

    assert result.total_posts == 21
    assert result.failed_posts == 0
    assert peak <= 3, f"concurrency exceeded: peak={peak}"
