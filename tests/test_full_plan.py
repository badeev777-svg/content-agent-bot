"""Phase 7.5: summary_keyboard + get_plan_with_posts chunk logic."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import summary_keyboard
from app.bot.handlers.generate import handle_full_plan_callback
from app.db import crud
from app.db.models import Platform, PostType


def test_summary_keyboard_has_button() -> None:
    kb = summary_keyboard("abc-123")
    assert kb.inline_keyboard[0][0].callback_data == "full_plan:abc-123"
    assert "текстом" in kb.inline_keyboard[0][0].text.lower()


@pytest.mark.asyncio
async def test_get_plan_with_posts_returns_posts(session: AsyncSession) -> None:
    await crud.get_or_create_user(session, telegram_id=20)
    plan = await crud.create_plan(
        session,
        user_id=20,
        source_url="https://example.com",
        source_summary="тест",
        platforms=["telegram"],
    )
    for day in range(1, 4):
        await crud.add_post(
            session,
            plan_id=plan.id,
            day=day,
            platform=Platform.TELEGRAM,
            post_type=PostType.EXPERTISE,
            content=f"пост {day}",
        )
    await session.commit()

    fetched = await crud.get_plan_with_posts(session, plan.id)
    assert fetched is not None
    assert len(fetched.posts) == 3
    assert fetched.source_summary == "тест"


@pytest.mark.asyncio
async def test_get_plan_with_posts_none_for_missing(session: AsyncSession) -> None:
    result = await crud.get_plan_with_posts(session, "nonexistent-plan-id")
    assert result is None


def test_chunk_logic_splits_on_boundary() -> None:
    """Verify chunking algorithm never splits in the middle of a block."""
    separator = "\n\n" + "─" * 20 + "\n\n"
    blocks = [f"Block {i}: " + "x" * 200 for i in range(20)]

    chunks: list[str] = []
    current = ""
    for block in blocks:
        piece = (separator + block) if current else block
        if len(current) + len(piece) > 4096:
            if current:
                chunks.append(current)
            current = block
        else:
            current += piece
    if current:
        chunks.append(current)

    assert all(len(c) <= 4096 for c in chunks)
    # every block must appear in exactly one chunk
    for i, block in enumerate(blocks):
        found = sum(1 for c in chunks if block in c)
        assert found == 1, f"Block {i} appears in {found} chunks"
