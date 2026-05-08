import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from app.db import crud
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)


async def show_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args and context.args[0].lower() == "edit":
        await update.message.reply_text(
            "Чтобы пересоздать профиль, отправь команду /style_edit (одной командой)."
        )
        return

    user = update.effective_user
    if user is None:
        return

    sm = get_sessionmaker()
    async with sm() as session:
        profile = await crud.get_profile(session, user.id)

    if profile is None or not profile.niche:
        await update.message.reply_text(
            "Профиль ещё не настроен. Нажми /start, чтобы пройти онбординг."
        )
        return

    text = (
        "<b>Твой профиль стиля</b>\n\n"
        f"<b>Ниша:</b> {profile.niche or '—'}\n"
        f"<b>Тон:</b> {profile.tone.value if profile.tone else '—'}\n"
        f"<b>Табу:</b> {', '.join(profile.forbidden) if profile.forbidden else 'нет'}\n"
        f"<b>Форматы:</b> {', '.join(profile.formats) if profile.formats else '—'}\n"
        f"<b>Примеров постов:</b> {len(profile.example_posts or [])}\n"
        f"<b>Заметки о стиле:</b> {profile.style_notes or '—'}\n\n"
        "/style_edit — пересоздать профиль с нуля\n"
        "/examples — добавить примеры постов\n"
        "/history — последние 5 генераций"
    )
    await update.message.reply_html(text)


def register(app: Application) -> None:
    app.add_handler(CommandHandler("style", show_style))
