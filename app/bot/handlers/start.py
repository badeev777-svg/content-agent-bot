import logging

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot.keyboards import FORMAT_OPTIONS, formats_keyboard, skip_keyboard, tone_keyboard
from app.db import crud
from app.db.models import Tone
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)

NICHE, TONE, FORBIDDEN, FORMATS, EXAMPLES = range(5)

WELCOME = (
    "Привет! Я Content Agent Bot 👋\n\n"
    "Я помогу тебе писать посты в твоём стиле. Кидаешь URL конкурента — "
    "я анализирую контент и собираю недельный план постов под выбранные платформы.\n\n"
    "Сначала давай настроим твой стиль — это займёт минуту.\n\n"
    "<b>1/5</b> — О чём ты пишешь? (ниша, тематика)\n"
    "Например: «маркетинг для малого бизнеса», «детская психология», «крипта»"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user is None or update.message is None:
        return ConversationHandler.END

    is_edit = update.message.text and update.message.text.startswith("/style_edit")

    sm = get_sessionmaker()
    async with sm() as session:
        await crud.get_or_create_user(session, telegram_id=user.id, username=user.username)
        existing = await crud.get_profile(session, user.id)
        if is_edit and existing is not None:
            existing.niche = None
        await session.commit()

    if not is_edit and existing and existing.niche:
        await update.message.reply_text(
            "У тебя уже есть настроенный профиль стиля.\n\n"
            "/style — посмотреть\n"
            "/style_edit — пересоздать\n"
            "Или просто пришли URL — сразу сгенерирую план."
        )
        return ConversationHandler.END

    context.user_data.clear()
    if is_edit:
        await update.message.reply_text("Перезапускаю онбординг с нуля...")
    await update.message.reply_html(WELCOME)
    return NICHE


async def receive_niche(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if len(text) < 3:
        await update.message.reply_text("Слишком коротко. Опиши нишу одним предложением.")
        return NICHE
    context.user_data["niche"] = text[:300]
    await update.message.reply_html(
        "<b>2/5</b> — Какой у тебя тон?",
        reply_markup=tone_keyboard(),
    )
    return TONE


async def receive_tone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    value = query.data.split(":", 1)[1]
    context.user_data["tone"] = Tone(value)

    await query.edit_message_text(
        "<b>3/5</b> — Что ты <b>никогда</b> не пишешь? Темы, слова, форматы под запретом.\n\n"
        "Можно списком через запятую. Или нажми «Пропустить».",
        parse_mode="HTML",
        reply_markup=skip_keyboard("forbidden:skip"),
    )
    return FORBIDDEN


async def receive_forbidden_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    items = [x.strip() for x in text.split(",") if x.strip()]
    context.user_data["forbidden"] = items[:20]
    return await _ask_formats(update, context, edit=False)


async def receive_forbidden_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["forbidden"] = []
    return await _ask_formats(update, context, edit=True)


async def _ask_formats(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool) -> int:
    context.user_data["formats"] = set()
    text = (
        "<b>4/5</b> — Какие форматы ты любишь? Можно несколько.\n"
        "Жми, чтобы выбрать. Когда закончишь — «Готово»."
    )
    kb = formats_keyboard(context.user_data["formats"])
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await update.message.reply_html(text, reply_markup=kb)
    return FORMATS


async def receive_format_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    value = query.data.split(":", 1)[1]

    if value == "done":
        if not context.user_data.get("formats"):
            await query.answer("Выбери хотя бы один формат", show_alert=True)
            return FORMATS
        await query.edit_message_text(
            "<b>5/5</b> — Пришли 1–3 своих лучших поста, чтобы я мог уловить твой стиль.\n\n"
            "Просто отправь их одним сообщением (или несколькими подряд) — соберу автоматически.\n"
            "Если постов пока нет, нажми «Пропустить».",
            parse_mode="HTML",
            reply_markup=skip_keyboard("examples:skip"),
        )
        context.user_data["examples"] = []
        return EXAMPLES

    selected: set[str] = context.user_data.setdefault("formats", set())
    if value in selected:
        selected.remove(value)
    else:
        selected.add(value)
    await query.edit_message_reply_markup(reply_markup=formats_keyboard(selected))
    return FORMATS


async def receive_example_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    examples: list[str] = context.user_data.setdefault("examples", [])
    if len(examples) >= 3:
        return await _finish_onboarding(update, context, edit=False)
    examples.append(text[:4000])
    if len(examples) >= 3:
        await update.message.reply_text("Отлично, собрал 3 примера. Сохраняю профиль...")
        return await _finish_onboarding(update, context, edit=False)
    await update.message.reply_text(
        f"Пример {len(examples)}/3 принят. Можно ещё — или нажми «Пропустить».",
        reply_markup=skip_keyboard("examples:skip"),
    )
    return EXAMPLES


async def receive_examples_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    return await _finish_onboarding(update, context, edit=True)


async def _finish_onboarding(
    update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool
) -> int:
    user = update.effective_user
    data = context.user_data
    formats_list = sorted(data.get("formats", set()))
    formats_human = [name for key, name in FORMAT_OPTIONS if key in formats_list]

    sm = get_sessionmaker()
    async with sm() as session:
        await crud.upsert_profile(
            session,
            telegram_id=user.id,
            niche=data.get("niche"),
            tone=data.get("tone"),
            forbidden=data.get("forbidden", []),
            formats=formats_human,
            example_posts=data.get("examples", []),
        )
        await session.commit()

    log.info("user %s finished onboarding", user.id)

    summary = (
        "✅ Готово! Профиль стиля сохранён.\n\n"
        f"<b>Ниша:</b> {data.get('niche')}\n"
        f"<b>Тон:</b> {data.get('tone').value if data.get('tone') else '—'}\n"
        f"<b>Табу:</b> {', '.join(data.get('forbidden', [])) or 'нет'}\n"
        f"<b>Форматы:</b> {', '.join(formats_human) or '—'}\n"
        f"<b>Примеров:</b> {len(data.get('examples', []))}\n\n"
        "Теперь пришли URL любой публичной страницы — и я соберу недельный план постов.\n"
        "(Генерация контента появится в Phase 7. Сейчас уже можно тестировать /style.)"
    )
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(summary, parse_mode="HTML")
    else:
        await update.message.reply_html(summary)
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Онбординг отменён. /start — начать заново.")
    context.user_data.clear()
    return ConversationHandler.END


def build_onboarding_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start), CommandHandler("style_edit", start)],
        states={
            NICHE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_niche)],
            TONE: [CallbackQueryHandler(receive_tone, pattern=r"^tone:")],
            FORBIDDEN: [
                CallbackQueryHandler(receive_forbidden_skip, pattern=r"^forbidden:skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_forbidden_text),
            ],
            FORMATS: [CallbackQueryHandler(receive_format_toggle, pattern=r"^fmt:")],
            EXAMPLES: [
                CallbackQueryHandler(receive_examples_skip, pattern=r"^examples:skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_example_text),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="onboarding",
        persistent=False,
    )


def register(app: Application) -> None:
    app.add_handler(build_onboarding_handler())
