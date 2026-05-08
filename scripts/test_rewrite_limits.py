#!/usr/bin/env python
"""Test daily rewrite limits with time mocking."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings, get_settings
from app.db.models import Base, User
from app.services.quota import (
    RewriteLimitExceeded,
    check_rewrite_allowed,
    consume_rewrite,
)


async def test_rewrite_limits_daily_reset():
    """Test that rewrite counter resets at UTC midnight."""
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        telegram_bot_token="test",
        openrouter_api_key="test",
    )

    engine = create_async_engine(settings.database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sm = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sm() as session:
        # Create test user
        user = User(
            telegram_id=12345,
            subscription="FREE",
            gens_used=0,
            last_gen_at=None,
            rewrites_used_today=0,
            rewrites_reset_at=None,
        )
        session.add(user)
        await session.commit()
        user_id = user.telegram_id

    # Day 1: Use 3 rewrites
    print("[Day 1] Testing 3 rewrites...")
    day1_midnight = datetime(2026, 5, 8, 0, 0, 0, tzinfo=timezone.utc)
    day1_noon = day1_midnight.replace(hour=12)

    async with sm() as session:
        # First rewrite at noon
        await check_rewrite_allowed(session, user_id, max_rewrites_per_day=3)
        await consume_rewrite(session, user_id)
        await session.commit()
        print("  OK: Rewrite 1/3 allowed")

        # Second rewrite
        await check_rewrite_allowed(session, user_id, max_rewrites_per_day=3)
        await consume_rewrite(session, user_id)
        await session.commit()
        print("  OK: Rewrite 2/3 allowed")

        # Third rewrite
        await check_rewrite_allowed(session, user_id, max_rewrites_per_day=3)
        await consume_rewrite(session, user_id)
        await session.commit()
        print("  OK: Rewrite 3/3 allowed")

    # Day 1: Try 4th rewrite, should fail
    print("  Testing 4th rewrite (should fail)...")
    async with sm() as session:
        try:
            await check_rewrite_allowed(session, user_id, max_rewrites_per_day=3)
            print("  FAIL: Should have raised RewriteLimitExceeded")
            return False
        except RewriteLimitExceeded:
            print("  OK: 4th rewrite blocked as expected")

    # Day 2: Counter should reset
    print("\n[Day 2] Testing counter reset at midnight...")
    day2_midnight = day1_midnight + timedelta(days=1)
    day2_noon = day2_midnight.replace(hour=12)

    async with sm() as session:
        # Manually set time to next day (simulating)
        user = await session.get(User, user_id)
        user.rewrites_reset_at = day1_midnight  # Expired
        await session.commit()

    async with sm() as session:
        # First rewrite of day 2 should work
        await check_rewrite_allowed(session, user_id, max_rewrites_per_day=3, now=day2_noon)
        user = await session.get(User, user_id)
        assert user.rewrites_used_today == 0, f"Counter not reset: {user.rewrites_used_today}"
        print("  OK: Counter reset to 0")

        await consume_rewrite(session, user_id)
        await session.commit()
        print("  OK: Day 2: Rewrite 1/3 allowed")

    print("\nSUCCESS: All tests passed!")
    await engine.dispose()
    return True


if __name__ == "__main__":
    result = asyncio.run(test_rewrite_limits_daily_reset())
    exit(0 if result else 1)
