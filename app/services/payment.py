"""Phase 8.3: Telegram Payments helper — creates invoice for subscription."""
from telegram import Bot, LabeledPrice

SUBSCRIPTION_PAYLOAD = "subscription_30d"


async def send_invoice(bot: Bot, chat_id: int, price_rub: int, provider_token: str) -> None:
    await bot.send_invoice(
        chat_id=chat_id,
        title="Подписка Content Agent Bot",
        description="Безлимитные генерации на 30 дней без ограничений.",
        payload=SUBSCRIPTION_PAYLOAD,
        provider_token=provider_token,
        currency="RUB",
        prices=[LabeledPrice("Подписка на месяц", price_rub * 100)],
    )
