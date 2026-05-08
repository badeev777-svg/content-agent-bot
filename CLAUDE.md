# Content Agent Bot — CLAUDE.md

Telegram-бот с мультиагентной архитектурой для SMM-специалистов. Принимает URL конкурента → парсит контент → генерирует недельный контент-план (7 дней × выбранные платформы) в личном стиле пользователя. Freemium: 3 бесплатных генерации → 2499 ₽/мес.

**Спецификация:** `../thoughts/shared/specs/2026-05-07-content-agent-bot.md`
**План разработки:** [`Plan.md`](Plan.md) — фазы, прогресс, обработка LLM-ошибок

---

## Структура проекта

```
content-agent-bot/
├── CLAUDE.md
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── alembic.ini
├── alembic/versions/
└── app/
    ├── main.py              # точка входа: запуск бота
    ├── config.py            # Pydantic Settings из .env
    ├── bot/
    │   ├── handlers/
    │   │   ├── start.py     # /start, онбординг-анкета
    │   │   ├── generate.py  # приём URL, выбор платформ, запуск генерации
    │   │   ├── style.py     # /style, /style edit, /examples
    │   │   └── history.py   # /history
    │   └── keyboards.py     # InlineKeyboard-фабрики
    ├── agents/
    │   ├── scraper.py       # Scraper Agent: httpx + BS4, fallback Playwright
    │   ├── strategist.py    # Strategist Agent: 7-дневная воронка
    │   └── copywriter.py    # Copywriter Agent × 4 платформы
    ├── db/
    │   ├── models.py        # SQLAlchemy ORM: User, UserProfile, ContentPlan, Post
    │   ├── session.py       # async engine + AsyncSession
    │   └── crud.py          # все DB-операции
    ├── services/
    │   ├── payment.py       # Telegram Payments API
    │   └── rate_limiter.py  # 1 генерация/час, 3 "Переписать"/пост
    └── tests/
        ├── test_scraper.py
        ├── test_agents.py
        └── test_db.py
```

---

## Tech Stack

| Компонент       | Технология                                      |
|-----------------|-------------------------------------------------|
| Язык            | Python 3.11+                                    |
| Telegram Bot    | python-telegram-bot v20+ (async)                |
| LLM             | OpenRouter → Claude Sonnet 4.6 (`anthropic/claude-sonnet-4.6`) + Prompt Caching |
| LLM SDK         | `openai` SDK с `base_url=https://openrouter.ai/api/v1` |
| Скрейпинг       | httpx + BeautifulSoup4, fallback: Playwright    |
| БД              | PostgreSQL + SQLAlchemy (async) + Alembic       |
| Платежи         | Telegram Payments API                           |
| Хостинг         | VPS, Docker + docker-compose                    |
| Конфигурация    | Pydantic Settings + .env                        |

---

## Архитектура

```
User → Telegram Bot (python-telegram-bot v20)
           │
    ┌──────▼──────┐
    │Scraper Agent│  httpx / Playwright → тезисы из URL (JSON)
    └──────┬──────┘
           │
    ┌──────▼────────┐
    │Strategist Agent│  Claude Opus → 7-дневная воронка (engagement/expertise/trust/sale)
    └──┬────┬────┬──┘
       ▼    ▼    ▼
    [TG] [VK] [Stories]   ← Copywriter Agent × платформа (отдельный system prompt)
                                   ← UserProfile инжектируется в каждый промпт
                                   ← все вызовы идут через OpenRouter (openai SDK + base_url)
           │
    PostgreSQL  ←→  ContentPlan + Post (UUID, feedback, hashtags, rec_time)
           │
    Telegram Payments API  (блокировка после 3 бесплатных генераций)
```

---

## 5 ключевых решений

| Решение | Почему |
|---------|--------|
| **OpenRouter + OpenAI SDK + cache_control** | Используем `openai` SDK с `base_url=openrouter.ai/api/v1`. Стандартный паттерн, работает со всеми моделями. Prompt Caching через `cache_control: {"type": "ephemeral"}` в content blocks — OpenRouter проксирует это для Anthropic-моделей. Снижает стоимость в 3–4× на повторных запросах |
| **Профиль стиля с первого запуска** | 5-вопросная анкета при /start + /examples. Без стиля — generic-контент. Стиль — главная ценность, не фича v2 |
| **Гибкие платформы, не жёсткие 21 пост** | Пользователь выбирает платформы сам → 7 дней × N платформ. Жёсткая формула убивала UX |
| **Freemium: 3 генерации, не "неделя бесплатно"** | "Неделя бесплатно" = пользователь берёт всё и уходит. 3 полных плана = конкретный лимит с конверсией |
| **Многопользовательская БД с нуля** | Архитектура с `telegram_id` как PK с первой строки. Без этого потребуется полный рефакторинг при публичном запуске |

---

## Схема данных (4 таблицы)

```
User           UserProfile         ContentPlan         Post
──────         ────────────        ───────────         ────
telegram_id PK user_id FK          id UUID PK          id UUID PK
username       niche TEXT          user_id FK           plan_id FK
subscription   tone ENUM           source_url TEXT      day INT (1-7)
gens_used INT  forbidden TEXT[]    source_summary TEXT  platform ENUM
sub_expires    formats TEXT[]      platforms TEXT[]     post_type ENUM
               example_posts TEXT[]created_at           content TEXT
               style_notes TEXT    (max 30/user)        hashtags TEXT[]
               updated_at                               cta TEXT
                                                        rec_time TEXT
                                                        feedback ENUM
```

---

## Тестирование

| Что тестируем | Файл | Метод |
|---------------|------|-------|
| Scraper Agent | `tests/test_scraper.py` | Реальный httpx по тестовым URL |
| Агенты → Claude | `tests/test_agents.py` | Моки Anthropic SDK |
| DB CRUD | `tests/test_db.py` | SQLite in-memory через SQLAlchemy |
| Rate limiter | внутри test_agents | Проверка блокировки после N запросов |

**Чек-лист перед деплоем:**
- [ ] /start → анкета → профиль сохранён в БД
- [ ] URL → план сгенерирован < 3 мин
- [ ] 3 генерации → блокировка → предложение подписки
- [ ] /style edit → профиль обновлён → следующий план использует новый стиль
- [ ] /history → 5 последних планов
- [ ] Rate limit: 4-й запрос в течение часа заблокирован
- [ ] SSRF защита: localhost → отклонён

---

## Документация

| Файл | Содержит | Когда обновлять |
|------|----------|-----------------|
| `CLAUDE.md` | Ориентация в проекте | При смене стека, новых агентах, смене схемы данных |
| `Plan.md` | Фазы разработки, прогресс, LLM error handling | После каждой задачи (статус), после каждой фазы (Master Table) |
| `specs/2026-05-07-content-agent-bot.md` | Полная спецификация P0/P1/P2 | При изменении бизнес-логики или пользовательского сценария |
| `.env.example` | Все переменные окружения | При добавлении новых сервисов/ключей |
| `alembic/versions/` | История миграций БД | Автоматически при `alembic revision` |
| `pyproject.toml` | Зависимости | При добавлении/удалении пакетов |

---

## Commands

```bash
# Установка
uv sync                              # или: pip install -e ".[dev]"

# Разработка
cp .env.example .env                 # заполнить TELEGRAM_TOKEN, ANTHROPIC_API_KEY, DATABASE_URL
alembic upgrade head                 # применить миграции
python -m app.main                   # запустить бота

# Тесты
pytest tests/ -v

# Docker (прод)
docker-compose up -d --build
docker-compose logs -f bot

# Миграции
alembic revision --autogenerate -m "описание"
alembic upgrade head
```

---

## Самообновление (какой файл за что отвечает)

| Событие | Что обновить |
|---------|-------------|
| Начало/завершение задачи | `Plan.md` §3 (статус задачи) |
| Завершение фазы | `Plan.md` §4 (Master Progress Table) + журнал §8 |
| Новый агент или платформа | `app/agents/`, промпты в `copywriter.py`, `CLAUDE.md` §Архитектура |
| Изменение схемы БД | `app/db/models.py` → `alembic revision` → `CLAUDE.md` §Схема данных |
| Новая переменная окружения | `.env.example` + `app/config.py` + `CLAUDE.md` §Commands |
| Изменение тарифа/лимитов | `app/services/payment.py` + `app/services/rate_limiter.py` + спецификация |
| Смена LLM модели | `MODEL_NAME` в `.env` (формат `provider/model-name`) + `CLAUDE.md` §Tech Stack |
| Смена LLM провайдера | `OPENROUTER_BASE_URL` + `OPENROUTER_API_KEY` в `.env` (можно подключить любой OpenAI-совместимый endpoint) |
| P1/P2 фичи | Создать новую спецификацию или дополнить существующую, обновить CLAUDE.md |

> **Правило:** если что-то работает не так, как описано в CLAUDE.md — обнови CLAUDE.md первым.
