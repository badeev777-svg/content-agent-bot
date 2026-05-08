"""Phase 9.2: /history — show 5 most recent content plans."""
import logging
from datetime import timezone

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from app.db import crud
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)


async def handle_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return

    user_id = update.effective_user.id
    sm = get_sessionmaker()
    async with sm() as session:
        plans = await crud.get_recent_plans(session, user_id, limit=5)

    if not plans:
        await update.message.reply_text(
            "Истории генераций пока нет. Пришли URL статьи, чтобы начать."
        )
        return

    lines: list[str] = ["<b>📚 Последние генерации:</b>\n"]
    for i, plan in enumerate(plans, 1):
        created = plan.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        date_str = created.strftime("%d.%m.%Y")

        url = plan.source_url
        if len(url) > 50:
            url = url[:47] + "..."

        platforms = ", ".join(plan.platforms) if plan.platforms else "—"
        count = len(plan.posts)
        lines.append(f"{i}. {date_str} · {url}\n   {platforms} · {count} постов")

    await update.message.reply_html("\n\n".join(lines))


def register(app: Application) -> None:
    app.add_handler(CommandHandler("history", handle_history))
