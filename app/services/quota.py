"""Phase 8.1/8.2: Rate limiting and generation quota for free users."""
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import Subscription, User


class QuotaExceeded(Exception):
    pass


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"rate limit: retry after {retry_after_seconds}s")


class RewriteLimitExceeded(Exception):
    def __init__(self, rewrite_limit: int) -> None:
        self.rewrite_limit = rewrite_limit
        super().__init__(f"daily rewrite limit exceeded: {rewrite_limit}")


def _utc(dt: datetime) -> datetime:
    """Ensure datetime is UTC-aware (SQLite may return naive UTC)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _has_active_sub(user: User, now: datetime) -> bool:
    return (
        user.subscription == Subscription.PAID
        and user.sub_expires is not None
        and _utc(user.sub_expires) > now
    )


async def check_generation_allowed(
    session: AsyncSession,
    user_id: int,
    settings: Settings | None = None,
) -> None:
    """Raise QuotaExceeded or RateLimitExceeded if user may not generate now."""
    if settings is None:
        settings = get_settings()

    user = await session.get(User, user_id)
    if user is None:
        raise ValueError(f"user {user_id} not found")

    now = datetime.now(tz=timezone.utc)

    if _has_active_sub(user, now):
        return

    if user.gens_used >= settings.free_generations:
        raise QuotaExceeded()

    if user.last_gen_at is not None:
        elapsed = (now - _utc(user.last_gen_at)).total_seconds()
        cooldown = 3600.0 / settings.rate_limit_per_hour
        if elapsed < cooldown:
            raise RateLimitExceeded(retry_after_seconds=int(cooldown - elapsed))


async def consume_generation(session: AsyncSession, user_id: int) -> None:
    """Increment gens_used and stamp last_gen_at. Call after successful pipeline."""
    user = await session.get(User, user_id)
    if user is None:
        raise ValueError(f"user {user_id} not found")
    user.gens_used += 1
    user.last_gen_at = datetime.now(tz=timezone.utc)
    await session.flush()


async def check_rewrite_allowed(
    session: AsyncSession,
    user_id: int,
    max_rewrites_per_day: int = 3,
    now: datetime | None = None,
) -> None:
    """Raise RewriteLimitExceeded if user exceeded daily rewrite limit."""
    user = await session.get(User, user_id)
    if user is None:
        raise ValueError(f"user {user_id} not found")

    if now is None:
        now = datetime.now(tz=timezone.utc)

    if user.rewrites_reset_at is None or _utc(user.rewrites_reset_at) <= now:
        user.rewrites_used_today = 0
        user.rewrites_reset_at = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        await session.flush()

    if user.rewrites_used_today >= max_rewrites_per_day:
        raise RewriteLimitExceeded(max_rewrites_per_day)


async def consume_rewrite(session: AsyncSession, user_id: int) -> None:
    """Increment rewrites_used_today. Call after successful rewrite."""
    user = await session.get(User, user_id)
    if user is None:
        raise ValueError(f"user {user_id} not found")
    user.rewrites_used_today += 1
    await session.flush()
