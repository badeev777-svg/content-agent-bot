"""Phase 7.1 + 7.3: URL → выбор платформ → запуск pipeline → отправка постов с кнопками."""
import logging
import re

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.agents.scraper import ScraperError, validate_url
from app.bot.keyboards import platforms_keyboard, post_actions_keyboard, summary_keyboard
from app.config import get_settings
from app.db import crud
from app.db.models import Platform, Post
from app.db.session import get_sessionmaker
from app.services.llm import LLMError
from app.services.messages import LIMITS_EXCEEDED, RATE_LIMIT_HIT, get_user_message
from app.services.pipeline import generate_plan
from app.services.quota import QuotaExceeded, RateLimitExceeded, check_generation_allowed, consume_generation

log = logging.getLogger(__name__)

URL_PATTERN = re.compile(r"https?://\S+")
TG_MESSAGE_LIMIT = 4000  # фактический лимит 4096; берём с запасом

_PENDING_URL = "pending_url"
_PENDING_PLATFORMS = "pending_platforms"


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Принять сообщение с URL, проверить профиль, показать выбор платформ."""
    if update.message is None or update.effective_user is None:
        return

    text = (update.message.text or "").strip()
    match = URL_PATTERN.search(text)
    if not match:
        return

    url = match.group(0).rstrip(".,)")

    try:
        url = validate_url(url)
    except ScraperError as e:
        await update.message.reply_text(get_user_message(f"scraper_{e.code}"))
        return

    user_id = update.effective_user.id
    sm = get_sessionmaker()
    async with sm() as session:
        await crud.get_or_create_user(
            session, telegram_id=user_id, username=update.effective_user.username
        )
        profile = await crud.get_profile(session, user_id)
        await session.commit()

    if profile is None or not profile.niche:
        await update.message.reply_text(
            "Сначала настрой профиль стиля — это займёт минуту: /start"
        )
        return

    context.user_data[_PENDING_URL] = url
    context.user_data[_PENDING_PLATFORMS] = set()

    await update.message.reply_text(
        f"✓ Принял URL:\n{url}\n\nВыбери платформы для постов:",
        reply_markup=platforms_keyboard(set()),
    )


async def handle_platform_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle платформы / Запустить / Отмена."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    action = query.data.split(":", 1)[1]

    if action == "cancel":
        context.user_data.pop(_PENDING_URL, None)
        context.user_data.pop(_PENDING_PLATFORMS, None)
        await query.edit_message_text("Отменено. Пришли URL ещё раз, когда будешь готов.")
        return

    if action == "go":
        platforms: set[Platform] = context.user_data.get(_PENDING_PLATFORMS, set())
        if not platforms:
            await query.answer("Выбери хотя бы одну платформу", show_alert=True)
            return
        url = context.user_data.get(_PENDING_URL)
        if not url:
            await query.edit_message_text("Сессия устарела. Пришли URL ещё раз.")
            return
        ordered = sorted(platforms, key=lambda p: p.value)
        await _run_pipeline(update, context, url, ordered)
        return

    try:
        platform = Platform(action)
    except ValueError:
        log.warning("unknown platform callback: %r", query.data)
        return

    selected: set[Platform] = context.user_data.setdefault(_PENDING_PLATFORMS, set())
    if platform in selected:
        selected.remove(platform)
    else:
        selected.add(platform)
    await query.edit_message_reply_markup(reply_markup=platforms_keyboard(selected))


async def _run_pipeline(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    platforms: list[Platform],
) -> None:
    query = update.callback_query
    chat = update.effective_chat
    user = update.effective_user
    if query is None or chat is None or user is None:
        return

    plat_names = ", ".join(p.value for p in platforms)
    await query.edit_message_text(
        f"⏳ Генерирую план для <b>{plat_names}</b>...\n\n"
        f"Это займёт 1–3 минуты — собираю тезисы, "
        f"строю стратегию, пишу {7 * len(platforms)} постов.",
        parse_mode=ParseMode.HTML,
    )

    sm = get_sessionmaker()
    async with sm() as session:
        profile = await crud.get_profile(session, user.id)

        try:
            await check_generation_allowed(session, user.id, get_settings())
        except QuotaExceeded:
            await query.edit_message_text(LIMITS_EXCEEDED)
            return
        except RateLimitExceeded as e:
            mins = max(1, (e.retry_after_seconds + 59) // 60)
            await query.edit_message_text(
                f"⏳ {RATE_LIMIT_HIT}\n\nПопробуй через {mins} мин."
            )
            return

        try:
            result = await generate_plan(
                session,
                user_id=user.id,
                url=url,
                platforms=platforms,
                profile=profile,
            )
        except ScraperError as e:
            await query.edit_message_text("❌ " + get_user_message(f"scraper_{e.code}"))
            return
        except LLMError as e:
            log.warning("pipeline LLMError: %s", e.log_message)
            await query.edit_message_text("❌ " + e.user_message)
            return
        except Exception:
            log.exception("pipeline failed")
            await query.edit_message_text("❌ " + get_user_message("internal_error"))
            return

        await consume_generation(session, user.id)
        await session.commit()

    context.user_data.pop(_PENDING_URL, None)
    context.user_data.pop(_PENDING_PLATFORMS, None)

    posts = list(result.plan.posts)
    posts.sort(key=lambda p: (p.day, p.platform.value))

    summary = (
        f"✅ Готово!\n\n"
        f"<b>Тема недели:</b> {result.plan.source_summary}\n"
        f"<b>Постов:</b> {len(posts)} из {result.total_posts}"
    )
    if result.failed_posts:
        summary += f"\n⚠️ {result.failed_posts} постов не вышли — можно попросить переписать позже."

    await context.bot.send_message(
        chat_id=chat.id,
        text=summary,
        parse_mode=ParseMode.HTML,
        reply_markup=summary_keyboard(result.plan.id),
    )

    for post in posts:
        await _send_post(context, chat.id, post)


async def _send_post(context: ContextTypes.DEFAULT_TYPE, chat_id: int, post: Post) -> None:
    header = (
        f"<b>День {post.day} · "
        f"{post.platform.value} · {post.post_type.value}</b>\n\n"
    )
    body = post.content
    if post.hashtags:
        body += f"\n\n{' '.join(post.hashtags)}"
    extras: list[str] = []
    if post.cta:
        extras.append(f"<b>CTA:</b> {post.cta}")
    if post.rec_time:
        extras.append(f"<b>Время:</b> {post.rec_time}")
    if extras:
        body += "\n\n" + "\n".join(extras)

    text = header + body
    if len(text) > TG_MESSAGE_LIMIT:
        text = text[: TG_MESSAGE_LIMIT - 3] + "..."

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=post_actions_keyboard(post.id),
    )


async def handle_full_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправить все посты плана одним потоком plain-текста без кнопок."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    plan_id = query.data.split(":", 1)[1]
    chat = update.effective_chat
    if chat is None:
        return

    sm = get_sessionmaker()
    async with sm() as session:
        plan = await crud.get_plan_with_posts(session, plan_id)

    if plan is None or not plan.posts:
        await query.answer("План не найден или пуст.", show_alert=True)
        return

    posts = sorted(plan.posts, key=lambda p: (p.day, p.platform.value))

    blocks: list[str] = []
    for post in posts:
        header = f"📅 День {post.day} · {post.platform.value} · {post.post_type.value}"
        parts = [header, "", post.content]
        if post.hashtags:
            parts.append(" ".join(post.hashtags))
        if post.cta:
            parts.append(f"CTA: {post.cta}")
        if post.rec_time:
            parts.append(f"Время: {post.rec_time}")
        blocks.append("\n".join(parts))

    separator = "\n\n" + "─" * 20 + "\n\n"
    full_text = separator.join(blocks)

    # Split into ≤4096-char chunks on separator boundaries
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

    for chunk in chunks:
        await context.bot.send_message(chat_id=chat.id, text=chunk)


def register(app: Application) -> None:
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.Regex(URL_PATTERN),
            handle_url,
        )
    )
    app.add_handler(CallbackQueryHandler(handle_platform_callback, pattern=r"^plat:"))
    app.add_handler(CallbackQueryHandler(handle_full_plan_callback, pattern=r"^full_plan:"))
