"""Phase 8.3–8.5: /subscribe, pre_checkout_query, successful_payment handlers."""
import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, PreCheckoutQueryHandler, filters

from app.config import get_settings
from app.db import crud
from app.db.session import get_sessionmaker
from app.services.messages import SUBSCRIPTION_ACTIVE
from app.services.payment import SUBSCRIPTION_PAYLOAD, send_invoice

log = logging.getLogger(__name__)


async def handle_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_chat is None:
        return

    settings = get_settings()
    user_id = update.effective_user.id

    sm = get_sessionmaker()
    async with sm() as session:
        user = await crud.get_or_create_user(session, telegram_id=user_id)
        await session.commit()

    if (
        user.subscription.value == "paid"
        and user.sub_expires is not None
        and user.sub_expires > datetime.now(tz=timezone.utc)
    ):
        expires_str = user.sub_expires.strftime("%d.%m.%Y")
        await update.message.reply_text(SUBSCRIPTION_ACTIVE.format(expires=expires_str))
        return

    if not settings.telegram_payment_token:
        await update.message.reply_text(
            "Оплата временно недоступна. Попробуй позже или напиши администратору."
        )
        return

    await send_invoice(
        bot=context.bot,
        chat_id=update.effective_chat.id,
        price_rub=settings.subscription_price_rub,
        provider_token=settings.telegram_payment_token,
    )


async def handle_pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    if query is None:
        return
    if query.invoice_payload != SUBSCRIPTION_PAYLOAD:
        await query.answer(ok=False, error_message="Неверный платёж.")
        return
    await query.answer(ok=True)


async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    user_id = update.effective_user.id

    sm = get_sessionmaker()
    async with sm() as session:
        user = await crud.activate_subscription(session, telegram_id=user_id, days=30)
        await session.commit()

    expires_str = user.sub_expires.strftime("%d.%m.%Y")
    await update.message.reply_text(SUBSCRIPTION_ACTIVE.format(expires=expires_str))
    log.info("subscription activated user=%d expires=%s", user_id, expires_str)


def register(app: Application) -> None:
    app.add_handler(CommandHandler("subscribe", handle_subscribe))
    app.add_handler(PreCheckoutQueryHandler(handle_pre_checkout))
    app.add_handler(
        MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment)
    )
