import asyncio
import logging

from telegram.ext import Application

from app.bot.handlers import examples as examples_handler
from app.bot.handlers import generate as generate_handler
from app.bot.handlers import history as history_handler
from app.bot.handlers import payment as payment_handler
from app.bot.handlers import post_actions as post_actions_handler
from app.bot.handlers import start as start_handler
from app.bot.handlers import style as style_handler
from app.config import get_settings


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def _run_health_server(log: logging.Logger, host: str = "0.0.0.0", port: int = 8080) -> None:
    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.read(1024)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(_handle, host, port)
    log.info("Health check listening on %s:%d", host, port)
    async with server:
        await server.serve_forever()


async def _post_init(application: Application, log: logging.Logger) -> None:
    asyncio.create_task(_run_health_server(log))


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    log = logging.getLogger(__name__)

    log.info("Starting Content Agent Bot...")

    async def post_init(application: Application) -> None:
        await _post_init(application, log)

    app = Application.builder().token(settings.telegram_bot_token).post_init(post_init).build()

    start_handler.register(app)
    style_handler.register(app)
    generate_handler.register(app)
    post_actions_handler.register(app)
    payment_handler.register(app)
    history_handler.register(app)
    examples_handler.register(app)

    log.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
