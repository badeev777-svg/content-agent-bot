"""Phase 8.1/8.2: quota and rate-limiting tests."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import crud
from app.db.models import Subscription
from app.services.quota import (
    QuotaExceeded,
    RateLimitExceeded,
    check_generation_allowed,
    consume_generation,
)

_SETTINGS = Settings(
    telegram_bot_token="x",
    openrouter_api_key="x",
    free_generations=3,
    rate_limit_per_hour=1,
)


async def _make_user(session: AsyncSession, telegram_id: int) -> None:
    await crud.get_or_create_user(session, telegram_id=telegram_id)
    await session.commit()


# ── free user, first gen ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_free_user_first_gen_allowed(session: AsyncSession) -> None:
    await _make_user(session, 100)
    await check_generation_allowed(session, 100, _SETTINGS)  # must not raise


# ── quota exhausted ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_free_user_quota_exceeded(session: AsyncSession) -> None:
    await _make_user(session, 101)
    user = await session.get(__import__("app.db.models", fromlist=["User"]).User, 101)
    user.gens_used = 3
    await session.commit()

    with pytest.raises(QuotaExceeded):
        await check_generation_allowed(session, 101, _SETTINGS)


# ── rate limit: too soon ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limit_too_soon(session: AsyncSession) -> None:
    await _make_user(session, 102)
    user = await session.get(__import__("app.db.models", fromlist=["User"]).User, 102)
    user.last_gen_at = datetime.now(tz=timezone.utc) - timedelta(minutes=30)
    await session.commit()

    with pytest.raises(RateLimitExceeded) as exc_info:
        await check_generation_allowed(session, 102, _SETTINGS)

    assert exc_info.value.retry_after_seconds > 0
    assert exc_info.value.retry_after_seconds <= 3600


# ── rate limit: cooldown expired ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limit_expired(session: AsyncSession) -> None:
    await _make_user(session, 103)
    user = await session.get(__import__("app.db.models", fromlist=["User"]).User, 103)
    user.last_gen_at = datetime.now(tz=timezone.utc) - timedelta(hours=2)
    await session.commit()

    await check_generation_allowed(session, 103, _SETTINGS)  # must not raise


# ── paid user: unlimited ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_paid_user_no_limits(session: AsyncSession) -> None:
    await _make_user(session, 104)
    user = await session.get(__import__("app.db.models", fromlist=["User"]).User, 104)
    user.subscription = Subscription.PAID
    user.sub_expires = datetime.now(tz=timezone.utc) + timedelta(days=30)
    user.gens_used = 100
    user.last_gen_at = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
    await session.commit()

    await check_generation_allowed(session, 104, _SETTINGS)  # must not raise


# ── paid user: expired subscription ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_paid_user_expired_sub(session: AsyncSession) -> None:
    await _make_user(session, 105)
    user = await session.get(__import__("app.db.models", fromlist=["User"]).User, 105)
    user.subscription = Subscription.PAID
    user.sub_expires = datetime.now(tz=timezone.utc) - timedelta(days=1)
    user.gens_used = 3
    await session.commit()

    with pytest.raises(QuotaExceeded):
        await check_generation_allowed(session, 105, _SETTINGS)


# ── consume_generation ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_consume_generation(session: AsyncSession) -> None:
    await _make_user(session, 106)

    await consume_generation(session, 106)
    await session.commit()

    from app.db.models import User
    user = await session.get(User, 106)
    assert user.gens_used == 1
    assert user.last_gen_at is not None


# ── retry_after precision ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retry_after_precision(session: AsyncSession) -> None:
    await _make_user(session, 107)
    user = await session.get(__import__("app.db.models", fromlist=["User"]).User, 107)
    # 45 minutes ago → 15 minutes left
    user.last_gen_at = datetime.now(tz=timezone.utc) - timedelta(minutes=45)
    await session.commit()

    with pytest.raises(RateLimitExceeded) as exc_info:
        await check_generation_allowed(session, 107, _SETTINGS)

    # ~15 min remaining (900 s), allow ±5 s for test execution jitter
    assert 895 <= exc_info.value.retry_after_seconds <= 905
