"""Phase 7.4: callback-хендлеры кнопок под постами (Переписать / Короче / Формальнее / Нравится)."""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from app.agents.copywriter import write_post
from app.agents.schemas import DayPlan
from app.bot.keyboards import post_actions_keyboard
from app.db import crud
from app.db.models import Feedback, Post
from app.db.session import get_sessionmaker
from app.services.llm import LLMError
from app.services.messages import REWRITES_LIMIT_HIT, get_user_message
from app.services.quota import RewriteLimitExceeded, check_rewrite_allowed, consume_rewrite

log = logging.getLogger(__name__)

MAX_REWRITES = 3

_DIRECTIVES: dict[str, str] = {
    "shorter": "Сделай пост в 2 раза короче. Убери воду, оставь только суть и самые сильные фразы.",
}


async def handle_post_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    parts = query.data.split(":", 2)
    if len(parts) != 3:
        return
    _, action, post_id = parts

    sm = get_sessionmaker()
    async with sm() as session:
        if action == "like":
            await _handle_like(query, session, post_id)
        elif action == "dislike":
            await _handle_dislike(query, session, post_id)
        elif action in ("rewrite", "shorter"):
            await _handle_rewrite(query, context, session, post_id, action)
        else:
            log.warning("unknown post action: %r", action)


async def _handle_like(query, session: AsyncSession, post_id: str) -> None:
    try:
        await crud.set_post_feedback(session, post_id, Feedback.LIKED)
        await session.commit()
    except ValueError:
        await query.answer("Пост не найден.", show_alert=True)
        return
    await query.answer("👍 Отмечено!", show_alert=False)


async def _handle_dislike(query, session: AsyncSession, post_id: str) -> None:
    try:
        await crud.set_post_feedback(session, post_id, Feedback.NONE)
        await session.commit()
    except ValueError:
        await query.answer("Пост не найден.", show_alert=True)
        return
    await query.answer("👎 Отмечено.", show_alert=False)


async def _handle_rewrite(
    query, context, session: AsyncSession, post_id: str, action: str
) -> None:
    post = await session.get(Post, post_id)
    if post is None:
        await query.answer("Пост не найден.", show_alert=True)
        return

    if post.rewrites_used >= MAX_REWRITES:
        await query.answer(REWRITES_LIMIT_HIT, show_alert=True)
        return

    from app.db.models import ContentPlan

    plan = await session.get(ContentPlan, post.plan_id)
    user_id = plan.user_id if plan else None

    try:
        await check_rewrite_allowed(session, user_id, max_rewrites_per_day=3)
    except RewriteLimitExceeded:
        await query.answer(
            "Лимит переписей на день исчерпан (max 3 в день). Попробуй завтра.",
            show_alert=True,
        )
        return

    # Reconstruct DayPlan from saved post fields (enough to drive copywriter)
    day_plan = DayPlan(
        day=post.day,
        post_type=post.post_type,
        angle=f"angle для дня {post.day}",
        hook=f"hook для дня {post.day}",
    )

    # Fetch ContentPlan for week_theme and user profile
    from app.agents.schemas import WeekPlan  # local import to avoid circular
    from app.db.models import ContentPlan

    plan = await session.get(ContentPlan, post.plan_id)
    week_theme = plan.source_summary or "" if plan else ""
    user_id = plan.user_id if plan else None

    profile = await crud.get_profile(session, user_id) if user_id else None

    extra_directive = _DIRECTIVES.get(action, "")

    # Edit message to show progress
    await query.edit_message_reply_markup(reply_markup=None)

    try:
        new_post = await write_post(
            day_plan=day_plan,
            platform=post.platform,
            profile=profile,
            week_theme=week_theme,
            extra_directive=extra_directive,
        )
    except LLMError as e:
        log.warning("rewrite LLMError post=%s action=%s: %s", post_id, action, e.log_message)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ " + e.user_message,
        )
        await query.edit_message_reply_markup(reply_markup=post_actions_keyboard(post_id))
        return
    except Exception:
        log.exception("rewrite failed post=%s", post_id)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ " + get_user_message("internal_error"),
        )
        await query.edit_message_reply_markup(reply_markup=post_actions_keyboard(post_id))
        return

    await crud.update_post_content(
        session,
        post_id,
        content=new_post.content,
        hashtags=new_post.hashtags,
        cta=new_post.cta or None,
        rec_time=new_post.rec_time or None,
    )
    await crud.increment_rewrites(session, post_id)
    await consume_rewrite(session, user_id)
    await session.commit()

    # Rebuild message text (same format as _send_post in generate.py)
    header = (
        f"<b>День {post.day} · "
        f"{post.platform.value} · {post.post_type.value}</b>\n\n"
    )
    body = new_post.content
    if new_post.hashtags:
        body += f"\n\n{' '.join(new_post.hashtags)}"
    extras: list[str] = []
    if new_post.cta:
        extras.append(f"<b>CTA:</b> {new_post.cta}")
    if new_post.rec_time:
        extras.append(f"<b>Время:</b> {new_post.rec_time}")
    if extras:
        body += "\n\n" + "\n".join(extras)

    text = header + body
    if len(text) > 4000:
        text = text[:4000] + "..."

    rewrites_left = MAX_REWRITES - (post.rewrites_used + 1)
    text += f"\n\n<i>Переписываний осталось: {rewrites_left}</i>"

    await query.edit_message_text(
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=post_actions_keyboard(post_id),
    )


def register(app: Application) -> None:
    app.add_handler(
        CallbackQueryHandler(handle_post_action, pattern=r"^post:(rewrite|shorter|like|dislike):")
    )
