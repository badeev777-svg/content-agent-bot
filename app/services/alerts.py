"""CRITICAL-алерты в Telegram-чат админа.

Используется когда что-то по-настоящему сломалось:
- Невалидный ANTHROPIC/OPENROUTER ключ
- Закончились кредиты у LLM провайдера
- БД упала
- Permission denied у внешних API

Канал отдельный от bot.send_message чтобы не зависеть от Application и работать
даже если бот в момент ошибки занят.
"""
import logging

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


async def send_critical(text: str) -> None:
    """Отправить алерт админу. Молча игнорирует ошибки самой отправки."""
    settings = get_settings()
    chat_id = settings.admin_telegram_chat_id
    if not chat_id:
        log.warning("ADMIN_TELEGRAM_CHAT_ID не задан, алерт пропущен: %s", text[:120])
        return

    payload = {
        "chat_id": chat_id,
        "text": f"🚨 CRITICAL\n\n{text[:3800]}",
        "disable_web_page_preview": True,
    }
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                log.error(
                    "alert send failed: status=%d body=%s",
                    resp.status_code,
                    resp.text[:200],
                )
    except httpx.HTTPError as e:
        log.error("alert send exception: %s", e)
