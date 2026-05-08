"""Phase 7.4: crud.update_post_content + copywriter extra_directive."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.copywriter import _build_user_prompt
from app.agents.schemas import DayPlan, GeneratedPost
from app.db import crud
from app.db.models import Feedback, Platform, PostType, Tone, UserProfile
from app.services.llm import LLMError


def _day_plan() -> DayPlan:
    return DayPlan(
        day=3,
        post_type=PostType.EXPERTISE,
        angle="как автоматизировать рутину — 5 конкретных шагов",
        hook="Ты тратишь 3 часа на то, что можно сделать за 10 минут",
    )


def _profile() -> UserProfile:
    return UserProfile(
        user_id=1,
        niche="SMM для малого бизнеса",
        tone=Tone.FRIENDLY,
        forbidden=[],
        formats=["Истории"],
    )


# ── extra_directive попадает в user-prompt
def test_extra_directive_in_prompt() -> None:
    prompt = _build_user_prompt(
        day_plan=_day_plan(),
        profile=_profile(),
        week_theme="Автоматизация",
        extra_directive="Сделай в 2 раза короче.",
    )
    assert "Сделай в 2 раза короче." in prompt
    assert "Дополнительная директива" in prompt


def test_no_directive_no_section() -> None:
    prompt = _build_user_prompt(
        day_plan=_day_plan(),
        profile=_profile(),
        week_theme="Автоматизация",
    )
    assert "Дополнительная директива" not in prompt


# ── update_post_content обновляет поля и не трогает другие
@pytest.mark.asyncio
async def test_update_post_content(session: AsyncSession) -> None:
    await crud.get_or_create_user(session, telegram_id=10)
    plan = await crud.create_plan(
        session,
        user_id=10,
        source_url="https://x.com",
        source_summary="тема",
        platforms=["telegram"],
    )
    post = await crud.add_post(
        session,
        plan_id=plan.id,
        day=1,
        platform=Platform.TELEGRAM,
        post_type=PostType.EXPERTISE,
        content="старый текст",
        hashtags=["#old"],
        cta="старый CTA",
        rec_time="09:00",
    )
    await session.commit()

    updated = await crud.update_post_content(
        session,
        post.id,
        content="новый текст",
        hashtags=["#new1", "#new2"],
        cta="новый CTA",
        rec_time="11:00",
    )
    await session.commit()

    assert updated.content == "новый текст"
    assert updated.hashtags == ["#new1", "#new2"]
    assert updated.cta == "новый CTA"
    assert updated.rec_time == "11:00"
    # неизменённые поля сохранились
    assert updated.day == 1
    assert updated.platform == Platform.TELEGRAM
    assert updated.rewrites_used == 0


@pytest.mark.asyncio
async def test_update_post_content_not_found(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="not found"):
        await crud.update_post_content(
            session,
            "nonexistent-id",
            content="x",
            hashtags=[],
            cta=None,
            rec_time=None,
        )


# ── rewrites_used инкрементируется независимо
@pytest.mark.asyncio
async def test_rewrite_counter(session: AsyncSession) -> None:
    await crud.get_or_create_user(session, telegram_id=11)
    plan = await crud.create_plan(
        session, user_id=11, source_url="https://x.com", source_summary=None, platforms=["vk"]
    )
    post = await crud.add_post(
        session,
        plan_id=plan.id,
        day=2,
        platform=Platform.VK,
        post_type=PostType.ENGAGEMENT,
        content="текст",
    )
    await session.commit()

    assert post.rewrites_used == 0
    assert await crud.increment_rewrites(session, post.id) == 1
    assert await crud.increment_rewrites(session, post.id) == 2
    assert await crud.increment_rewrites(session, post.id) == 3


# ── set_post_feedback + update_post_content не конфликтуют
@pytest.mark.asyncio
async def test_like_and_rewrite_independent(session: AsyncSession) -> None:
    await crud.get_or_create_user(session, telegram_id=12)
    plan = await crud.create_plan(
        session, user_id=12, source_url="https://x.com", source_summary=None, platforms=["telegram"]
    )
    post = await crud.add_post(
        session,
        plan_id=plan.id,
        day=1,
        platform=Platform.TELEGRAM,
        post_type=PostType.TRUST,
        content="текст",
    )
    await session.commit()

    await crud.set_post_feedback(session, post.id, Feedback.LIKED)
    await crud.update_post_content(
        session, post.id, content="новый", hashtags=[], cta=None, rec_time=None
    )
    await session.commit()

    refreshed = await session.get(type(post), post.id)
    assert refreshed.feedback == Feedback.LIKED
    assert refreshed.content == "новый"
