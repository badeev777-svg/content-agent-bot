import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import crud
from app.db.models import Feedback, Platform, PostType, Subscription, Tone


@pytest.mark.asyncio
async def test_create_user(session: AsyncSession) -> None:
    user = await crud.get_or_create_user(session, telegram_id=42, username="alice")
    await session.commit()

    assert user.telegram_id == 42
    assert user.username == "alice"
    assert user.subscription == Subscription.FREE
    assert user.gens_used == 0


@pytest.mark.asyncio
async def test_get_or_create_is_idempotent(session: AsyncSession) -> None:
    u1 = await crud.get_or_create_user(session, telegram_id=42, username="alice")
    await session.commit()
    u2 = await crud.get_or_create_user(session, telegram_id=42, username="alice2")
    await session.commit()

    assert u1.telegram_id == u2.telegram_id
    assert u2.username == "alice2"


@pytest.mark.asyncio
async def test_upsert_profile(session: AsyncSession) -> None:
    await crud.get_or_create_user(session, telegram_id=10)
    await session.commit()

    p = await crud.upsert_profile(
        session,
        telegram_id=10,
        niche="кулинария",
        tone=Tone.FRIENDLY,
        forbidden=["политика"],
        formats=["списки", "истории"],
    )
    await session.commit()

    assert p.niche == "кулинария"
    assert p.tone == Tone.FRIENDLY
    assert p.forbidden == ["политика"]
    assert p.formats == ["списки", "истории"]

    p2 = await crud.upsert_profile(session, telegram_id=10, niche="фитнес")
    await session.commit()

    assert p2.niche == "фитнес"
    assert p2.tone == Tone.FRIENDLY  # не перезаписан
    assert p2.forbidden == ["политика"]


@pytest.mark.asyncio
async def test_increment_gens_used(session: AsyncSession) -> None:
    await crud.get_or_create_user(session, telegram_id=7)
    await session.commit()

    assert await crud.increment_gens_used(session, 7) == 1
    assert await crud.increment_gens_used(session, 7) == 2
    assert await crud.increment_gens_used(session, 7) == 3


@pytest.mark.asyncio
async def test_subscription_activation(session: AsyncSession) -> None:
    await crud.get_or_create_user(session, telegram_id=1)
    await session.commit()

    assert not await crud.has_active_subscription(session, 1)

    user = await crud.activate_subscription(session, 1, days=30)
    await session.commit()

    assert user.subscription == Subscription.PAID
    assert user.sub_expires is not None
    assert await crud.has_active_subscription(session, 1)


@pytest.mark.asyncio
async def test_create_plan_with_posts(session: AsyncSession) -> None:
    await crud.get_or_create_user(session, telegram_id=99)
    await session.commit()

    plan = await crud.create_plan(
        session,
        user_id=99,
        source_url="https://example.com/article",
        source_summary="Тезисы о маркетинге",
        platforms=["telegram", "vk"],
    )
    await session.commit()

    assert plan.id is not None
    assert plan.platforms == ["telegram", "vk"]

    for day in range(1, 8):
        await crud.add_post(
            session,
            plan_id=plan.id,
            day=day,
            platform=Platform.TELEGRAM,
            post_type=PostType.ENGAGEMENT,
            content=f"Пост дня {day}",
            hashtags=["#smm"],
            cta="Подписывайся!",
            rec_time="10:00",
        )
    await session.commit()

    plans = await crud.get_recent_plans(session, telegram_id=99, limit=5)
    assert len(plans) == 1
    assert len(plans[0].posts) == 7
    assert plans[0].posts[0].day == 1
    assert plans[0].posts[-1].day == 7


@pytest.mark.asyncio
async def test_post_feedback_and_rewrites(session: AsyncSession) -> None:
    await crud.get_or_create_user(session, telegram_id=5)
    plan = await crud.create_plan(
        session, user_id=5, source_url="https://x.com", source_summary=None, platforms=["telegram"]
    )
    post = await crud.add_post(
        session,
        plan_id=plan.id,
        day=1,
        platform=Platform.TELEGRAM,
        post_type=PostType.SALE,
        content="купи",
    )
    await session.commit()

    updated = await crud.set_post_feedback(session, post.id, Feedback.LIKED)
    await session.commit()
    assert updated.feedback == Feedback.LIKED

    assert await crud.increment_rewrites(session, post.id) == 1
    assert await crud.increment_rewrites(session, post.id) == 2


@pytest.mark.asyncio
async def test_recent_plans_ordering_and_limit(session: AsyncSession) -> None:
    from datetime import datetime, timedelta, timezone

    await crud.get_or_create_user(session, telegram_id=3)
    await session.commit()

    base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
    for i in range(7):
        plan = await crud.create_plan(
            session,
            user_id=3,
            source_url=f"https://x.com/{i}",
            source_summary=None,
            platforms=["telegram"],
        )
        plan.created_at = base + timedelta(hours=i)
        await session.commit()

    plans = await crud.get_recent_plans(session, telegram_id=3, limit=5)
    assert len(plans) == 5
    urls = [p.source_url for p in plans]
    assert urls == [f"https://x.com/{i}" for i in (6, 5, 4, 3, 2)]
