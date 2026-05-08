# Content Agent Bot

Telegram-бот с мультиагентной архитектурой для генерации контент-планов SMM-специалистов в личном стиле пользователя.

## Документация

- [`CLAUDE.md`](CLAUDE.md) — структура, стек, архитектура
- [`Plan.md`](Plan.md) — план разработки и текущий прогресс
- [`../thoughts/shared/specs/2026-05-07-content-agent-bot.md`](../thoughts/shared/specs/2026-05-07-content-agent-bot.md) — полная спецификация

## Быстрый старт

```bash
cp .env.example .env
# Заполнить TELEGRAM_BOT_TOKEN, OPENROUTER_API_KEY, и остальное

uv sync
python -m app.main
```

## Deployment

### Docker (рекомендуется)

```bash
cd deploy/
# Заполнить .env
docker-compose -f docker-compose.prod.yml up -d
```

**Требуется:** `POSTGRES_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`

Health check: `curl http://localhost:8080` → `OK`

### systemd (VPS)

1. **Клон репо:**
   ```bash
   git clone ... /opt/content-agent-bot
   cd /opt/content-agent-bot
   ```

2. **Зависимости:**
   ```bash
   uv sync --frozen
   sudo chown -R bot:bot /opt/content-agent-bot
   ```

3. **Переменные окружения:**
   ```bash
   cp .env.example .env
   nano .env  # заполнить
   ```

4. **Сервис:**
   ```bash
   sudo cp deploy/content-agent-bot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl start content-agent-bot
   sudo systemctl enable content-agent-bot
   ```

5. **Логи:**
   ```bash
   sudo journalctl -u content-agent-bot -f
   ```

## Commands

- `/start` — онбординг + профиль стиля
- `/style` — показать профиль, `/style_edit` — изменить
- `[URL]` — генерировать контент-план для этой статьи
- `/history` — последние 5 генераций
- `/examples` — добавить примеры постов в свой стиль
- `/subscribe` — оплатить подписку (2499 ₽/мес)

## Кнопки под каждым постом

- **🔄 Переписать** — полностью переписать пост (макс 3 в день для платных)
- **✂️ Короче** — сократить пост в 2 раза
- **👍 Нравится** — отметить как понравился
- **👎 Не нравится** — отметить как не понравился

## Архитектура

- **Scraper** → тезисы из URL (httpx + BeautifulSoup4)
- **Strategist** → 7-дневная воронка (engagement → expertise → trust → sale)
- **Copywriter** → посты для Telegram, VK, Stories (уникальные промпты на платформу)
- **Monetization** → 3 бесплатных ген + 2499 ₽/мес (безлимит + 3 переписи/день)
- **Telegram Payments** → встроенная оплата через BotFather
- **Health Check** → TCP на порт 8080 для health-check в Docker

См. [Plan.md](Plan.md) для полной спецификации.
