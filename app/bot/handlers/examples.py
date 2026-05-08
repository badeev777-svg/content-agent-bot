"""Phase 9.1: /examples — add example posts to user profile."""
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.db import crud
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)

_WAITING_EXAMPLES = "waiting_examples"
_MAX_EXAMPLES = 3


async def handle_examples_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return

    sm = get_sessionmaker()
    async with sm() as session:
        profile = await crud.get_profile(session, update.effective_user.id)

    existing = len(profile.example_posts or []) if profile else 0
    hint = f"Сейчас сохранено: {existing} пример(а).\n\n" if existing else ""

    context.user_data[_WAITING_EXAMPLES] = True
    context.user_data["collected_examples"] = []

    await update.message.reply_text(
        f"{hint}"
        f"Пришли до {_MAX_EXAMPLES} примеров своих постов — по одному сообщению. "
        f"Когда закончишь, напиши /done.\n\n"
        "Бот будет учитывать эти примеры при генерации нового контента."
    )


async def handle_example_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not context.user_data.get(_WAITING_EXAMPLES):
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    examples: list[str] = context.user_data.setdefault("collected_examples", [])
    if len(examples) >= _MAX_EXAMPLES:
        await update.message.reply_text(
            f"Уже собрал {_MAX_EXAMPLES} примера. Напиши /done, чтобы сохранить."
        )
        return

    examples.append(text)
    remaining = _MAX_EXAMPLES - len(examples)
    if remaining > 0:
        await update.message.reply_text(
            f"✓ Принял ({len(examples)}/{_MAX_EXAMPLES}). "
            f"Можно добавить ещё {remaining} или напиши /done."
        )
    else:
        await _commit_examples(update, context)


async def handle_done_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not context.user_data.get(_WAITING_EXAMPLES):
        await update.message.reply_text(
            "Нет активного ввода. Используй /examples, чтобы добавить примеры."
        )
        return
    await _commit_examples(update, context)


async def _commit_examples(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    examples: list[str] = context.user_data.pop("collected_examples", [])
    context.user_data.pop(_WAITING_EXAMPLES, None)

    if not examples:
        await update.message.reply_text(
            "Нет примеров для сохранения. Попробуй снова: /examples"
        )
        return

    user_id = update.effective_user.id
    sm = get_sessionmaker()
    async with sm() as session:
        await crud.get_or_create_user(session, telegram_id=user_id)
        await crud.upsert_profile(session, user_id, example_posts=examples)
        await session.commit()

    await update.message.reply_text(
        f"✅ Сохранил {len(examples)} пример(а) постов. "
        "Буду учитывать стиль при следующей генерации."
    )
    log.info("examples saved user=%d count=%d", user_id, len(examples))


def register(app: Application) -> None:
    app.add_handler(CommandHandler("examples", handle_examples_cmd))
    app.add_handler(CommandHandler("done", handle_done_cmd))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_example_text),
        group=1,
    )
