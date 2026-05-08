"""Generation pipeline: URL → Scraper → Strategist → Copywriter (parallel) → DB.

Главная точка входа Phase 7. Бот-хендлер дёргает `generate_plan(...)` и получает
сохранённый `ContentPlan` с подгруженными постами.
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.copywriter import write_post as _default_write_post
from app.agents.scraper import scrape as _default_scrape
from app.agents.schemas import DayPlan, GeneratedPost, WeekPlan
from app.agents.strategist import plan_week as _default_plan_week
from app.db import crud
from app.db.models import ContentPlan, Platform, UserProfile

log = logging.getLogger(__name__)

_DEFAULT_CONCURRENCY = 5


class PipelineResult:
    """Результат прогона пайплайна — план + сколько постов реально сохранилось.

    Если часть платформо-дней упала на копирайтере, мы сохраняем то, что вышло,
    и сообщаем число failed. Полный отказ (scraper/strategist) — exception наружу.
    """

    __slots__ = ("plan", "failed_posts", "total_posts")

    def __init__(self, plan: ContentPlan, failed_posts: int, total_posts: int) -> None:
        self.plan = plan
        self.failed_posts = failed_posts
        self.total_posts = total_posts


async def generate_plan(
    session: AsyncSession,
    *,
    user_id: int,
    url: str,
    platforms: list[Platform],
    profile: UserProfile | None,
    concurrency: int = _DEFAULT_CONCURRENCY,
    scrape_fn: Callable[[str], Awaitable] = _default_scrape,
    plan_week_fn: Callable[..., Awaitable[WeekPlan]] = _default_plan_week,
    write_post_fn: Callable[..., Awaitable[GeneratedPost]] = _default_write_post,
) -> PipelineResult:
    """End-to-end генерация: scrape → strategist → 7×N copywriter → persist.

    Параметры `*_fn` нужны только для тестов — оверрайдят дефолтных агентов на моки.
    """
    if not platforms:
        raise ValueError("platforms must not be empty")

    log.info("pipeline: start user=%d url=%s platforms=%s", user_id, url, [p.value for p in platforms])

    scraped = await scrape_fn(url)
    week = await plan_week_fn(scraped, profile, [p.value for p in platforms])

    sem = asyncio.Semaphore(concurrency)

    async def _bounded(day: DayPlan, platform: Platform) -> GeneratedPost:
        async with sem:
            return await write_post_fn(
                day_plan=day, platform=platform, profile=profile, week_theme=week.theme
            )

    pairs: list[tuple[DayPlan, Platform]] = [
        (day, platform) for day in week.days for platform in platforms
    ]
    log.info("pipeline: generating %d posts (concurrency=%d)", len(pairs), concurrency)

    results = await asyncio.gather(
        *(_bounded(day, platform) for day, platform in pairs),
        return_exceptions=True,
    )

    plan = await crud.create_plan(
        session,
        user_id=user_id,
        source_url=scraped.url,
        source_summary=week.theme,
        platforms=[p.value for p in platforms],
    )

    failed = 0
    for (day, platform), result in zip(pairs, results, strict=True):
        if isinstance(result, BaseException):
            failed += 1
            log.warning(
                "pipeline: post failed day=%d platform=%s err=%s",
                day.day, platform.value, result,
            )
            continue
        await crud.add_post(
            session,
            plan_id=plan.id,
            day=day.day,
            platform=platform,
            post_type=day.post_type,
            content=result.content,
            hashtags=result.hashtags,
            cta=result.cta or None,
            rec_time=result.rec_time or None,
        )

    await session.commit()

    reloaded = await crud.get_plan_with_posts(session, plan.id)
    assert reloaded is not None  # только что закоммитили
    log.info(
        "pipeline: done plan=%s saved=%d/%d",
        reloaded.id, len(reloaded.posts), len(pairs),
    )
    return PipelineResult(plan=reloaded, failed_posts=failed, total_posts=len(pairs))
