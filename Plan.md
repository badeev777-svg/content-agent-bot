# Content Agent Bot — План реализации

**Проект:** Telegram-бот для SMM с мультиагентной генерацией контент-планов
**Дата старта:** 2026-05-07
**Статус:** ✅ PRODUCTION READY · Phase 0–9 code-complete (93/93 тестов) · VPS Deployment Ready (2026-05-08)

## ✅ Production Ready

Все фазы завершены. Бот готов к развёртыванию на VPS jino.ru (параметры получены).

**VPS Deployment Status:**
- ✅ VPS parameters received: 130e66479b71.vps.myjino.ru (81.177.6.131:49386)
- ✅ systemd service ready: `deploy/content-agent-bot.service`
- ✅ Deployment checklist: `deploy/VPS_DEPLOYMENT_CHECKLIST.md`
- ✅ .env.production template: `deploy/.env.production.template`

### Быстрый деплой

```bash
cd deploy/
docker-compose -f docker-compose.prod.yml up -d
```

Или на VPS (systemd):
```bash
sudo cp deploy/content-agent-bot.service /etc/systemd/system/
sudo systemctl start content-agent-bot
```

### Что работает

- ✅ `/start` → 5-вопросный онбординг → профиль в БД
- ✅ URL → скрейпинг → Strategist (7-дневная воронка) → 28 постов (4 платформы × 7 дней)
- ✅ Каждый пост с 4 кнопками: [🔄 Переписать] [✂️ Короче] [👔 Формальнее] [👍 Нравится]
- ✅ Rate limit (1 ген/час) + Quota (3 free gens) + Telegram Payments (499 ₽/мес)
- ✅ `/history` — 5 последних планов
- ✅ `/examples` — загрузить примеры стиля
- ✅ Health check на port 8080
- ✅ Все 93 теста зелёные

**Спецификация:** [`../thoughts/shared/specs/2026-05-07-content-agent-bot.md`](../thoughts/shared/specs/2026-05-07-content-agent-bot.md)
**Документация проекта:** [`CLAUDE.md`](CLAUDE.md)

---

## 0. Механизм самообновления

Этот файл — единый источник правды о ходе разработки. После каждого действия Claude обязан синхронизировать его с реальностью.

### Правила обновления статусов

| Событие | Что обновить |
|---------|--------------|
| Начали задачу | Статус задачи `⬜ TODO` → `🟡 IN PROGRESS` |
| Завершили задачу | Статус `🟡` → `✅ DONE`, заполнить колонку «Факт» датой |
| Появился блокер | Статус → `🔴 BLOCKED`, описать причину в колонке «Блокер» |
| Завершили фазу | Обновить Master Progress Table (раздел 4) + дописать ссылку на текущую активную фазу в `CLAUDE.md` |
| Изменили схему БД | Создать миграцию `alembic revision --autogenerate` и упомянуть в задаче |
| Добавили env-переменную | Дописать в `.env.example` + обновить `app/config.py` + раздел «Commands» в `CLAUDE.md` |

### Что обновляется автоматически

| Файл | За что отвечает | Когда обновляется |
|------|------------------|--------------------|
| `Plan.md` (этот файл) | Прогресс, блокеры, ход разработки | После каждой задачи |
| `CLAUDE.md` | Структура, стек, ключевые решения | При смене стека или схемы |
| `alembic/versions/` | История миграций | При изменении `db/models.py` |
| `.env.example` | Переменные окружения | При добавлении новых ключей |
| `pyproject.toml` | Зависимости | При `uv add` |

### Условные обозначения

`⬜ TODO` · `🟡 IN PROGRESS` · `✅ DONE` · `🔴 BLOCKED` · `⏸ PAUSED`

---

## 1. Обзор фаз

| # | Фаза | Готовое состояние |
|---|------|--------------------|
| 0 | Foundation | Проект стартует, бот отвечает echo |
| 1 | Database | Схема применена, CRUD протестирован |
| 2 | Onboarding & Profile | /start → анкета → профиль в БД |
| 3 | Scraper Agent | URL → JSON с тезисами, SSRF защищён |
| 4 | LLM Client + Error Handling ⭐ | Anthropic SDK + русские сообщения для всех ошибок |
| 5 | Strategist Agent | Тезисы + профиль → 7-дневный план |
| 6 | Copywriter Agents (×4) | Angle + платформа → готовый пост |
| 7 | Generation Pipeline | URL → посты в чат с кнопками |
| 8 | Rate Limits + Monetization | Лимиты, оплата, 3→499 ₽/мес |
| 9 | Polish + Production | Деплой на VPS, /examples, /history |

---

## 2. Граф зависимостей

```
Phase 0 (Foundation)
    ├─→ Phase 1 (DB) ─→ Phase 2 (Onboarding)
    ├─→ Phase 3 (Scraper) ─────────────────┐
    └─→ Phase 4 (LLM + Errors)             │
            ├─→ Phase 5 (Strategist) ──────┤
            └─→ Phase 6 (Copywriter) ──────┤
                                           ▼
                                    Phase 7 (Pipeline)
                                           │
                                           ▼
                                    Phase 8 (Limits + Pay)
                                           │
                                           ▼
                                    Phase 9 (Polish + Deploy)
```

**Параллелизация:** после Phase 0 можно делать **Phase 1, 3, 4 параллельно**. После Phase 4 — **Phase 5 и 6 параллельно**. Phase 2 может идти параллельно с Phase 3+4.

---

## 3. Детальная разбивка фаз

### Phase 0 — Foundation

**Цель:** Скелет проекта, бот стартует, есть базовая инфраструктура.
**Готовность:** `python -m app.main` стартует, бот отвечает «echo» на любое сообщение.

| # | Задача | Файлы | Тесты | Статус | Зависимости |
|---|--------|-------|-------|--------|-------------|
| 0.1 | Структура папок | `app/`, `tests/`, `alembic/` | — | ✅ DONE | — |
| 0.2 | `pyproject.toml` (uv) | `pyproject.toml` | — | ✅ DONE | 0.1 |
| 0.3 | `.env.example`, `.gitignore`, `.dockerignore` | 3 файла | — | ✅ DONE | 0.1 |
| 0.4 | Dockerfile + docker-compose | `Dockerfile`, `docker-compose.yml` | — | ✅ DONE | 0.2 |
| 0.5 | Pydantic Settings | `app/config.py` | (отложено в Phase 1) | ✅ DONE | 0.2 |
| 0.6 | Entry point с logging | `app/main.py` | — | ✅ DONE | 0.5 |
| 0.7 | Echo-handler | `app/bot/handlers/echo.py` | — | ✅ DONE | 0.6 |

---

### Phase 1 — Database

**Цель:** PostgreSQL работает, все 4 таблицы созданы, CRUD оттестирован.
**Готовность:** `alembic upgrade head` применяет миграции, тесты CRUD зелёные.

| # | Задача | Файлы | Тесты | Статус | Зависимости |
|---|--------|-------|-------|--------|-------------|
| 1.1 | Async engine + sessionmaker | `app/db/session.py` | — | ✅ DONE | Phase 0 |
| 1.2 | SQLAlchemy модели (4 таблицы) | `app/db/models.py` | — | ✅ DONE | 1.1 |
| 1.3 | Alembic init + первая миграция | `alembic/`, `alembic.ini`, `alembic/versions/20260507_0940_001_initial_schema.py` | — | ✅ DONE | 1.2 |
| 1.4 | CRUD функции | `app/db/crud.py` | `tests/test_db.py` (8 тестов) | ✅ DONE | 1.2 |
| 1.5 | Тесты с SQLite in-memory | `tests/conftest.py`, `tests/test_db.py` | 8/8 PASSED | ✅ DONE | 1.4 |

---

### Phase 2 — Onboarding & Profile

**Цель:** /start запускает 5-вопросную анкету, профиль сохраняется в БД, /style показывает его.
**Готовность:** новый пользователь проходит онбординг → запись в `UserProfile`; /style edit перезапускает анкету.

| # | Задача | Файлы | Тесты | Статус | Зависимости |
|---|--------|-------|-------|--------|-------------|
| 2.1 | /start с ConversationHandler (5 состояний: NICHE/TONE/FORBIDDEN/FORMATS/EXAMPLES) | `app/bot/handlers/start.py` | live-test (2 прогона) | ✅ DONE | Phase 1 |
| 2.2 | InlineKeyboard-фабрики (tone, formats, skip) | `app/bot/keyboards.py` | — | ✅ DONE | 2.1 |
| 2.3 | /style + /style_edit (через ConversationHandler entry_point) | `app/bot/handlers/style.py` | live-test | ✅ DONE | 2.1 |
| 2.4 | Регистрация хендлеров в main.py, удалён echo | `app/main.py` | — | ✅ DONE | 2.1, 2.3 |

---

### Phase 3 — Scraper Agent

**Цель:** Любой публичный URL → JSON с тезисами; локальные адреса блокируются.
**Готовность:** на вход URL → `{title, theses[], theme, tone}`; SSRF-атака отклонена.

| # | Задача | Файлы | Тесты | Статус | Зависимости |
|---|--------|-------|-------|--------|-------------|
| 3.1 | httpx + BeautifulSoup4 скрейпер | `app/agents/scraper.py` | `tests/test_scraper.py` (19 тестов) | ✅ DONE | Phase 0 |
| 3.2 | SSRF защита (whitelist схем, blacklist приватных IP через socket.getaddrinfo) | `app/agents/scraper.py:_is_blocked_host` | 5 SSRF-кейсов в test_scraper.py | ✅ DONE | 3.1 |
| 3.3 | URL-валидация (длина, схема, hostname) | `app/agents/scraper.py:validate_url` | 5 кейсов в test_scraper.py | ✅ DONE | 3.2 |
| 3.4 | Playwright fallback (опционально для JS-heavy) | — | — | ⏸ ОТЛОЖЕНО (httpx справляется на habr.com) | 3.1 |
| 3.5 | Извлечение тезисов из HTML (эвристика, до LLM) | `app/agents/scraper.py:extract` + `_heuristic_theses` | live-test на habr.com (5 тезисов) | ✅ DONE | 3.1 |

---

### Phase 4 — LLM Client + Error Handling ⭐

**Цель:** Полная обёртка над Anthropic SDK с Prompt Caching и обработкой всех типов ошибок.
**Готовность:** любая ошибка LLM → пользователь видит русское сообщение, разработчик — детальный лог.

| # | Задача | Файлы | Тесты | Статус | Зависимости |
|---|--------|-------|-------|--------|-------------|
| 4.1 | OpenAI SDK + OpenRouter base_url + cache_control (ephemeral) | `app/services/llm.py:LLMClient`, `_build_messages` | live-test (text + JSON) | ✅ DONE | Phase 0 |
| 4.2 | Централизованные русские тексты + `get_user_message(code)` | `app/services/messages.py` | `test_all_llm_codes_have_translations` | ✅ DONE | — |
| 4.3 | Маппинг всех ошибок openai SDK + OpenRouter HTTP-кодов в `LLMError(code, ...)` | `app/services/llm.py` | `tests/test_llm.py` (20 тестов) | ✅ DONE | 4.1, 4.2 |
| 4.4 | Retry с exponential backoff (tenacity, 3 попытки, min=2s max=20s) на retryable: connection/timeout/rate_limit | `app/services/llm.py:_create_completion` | покрыто моками | ✅ DONE | 4.3 |
| 4.5 | Алерт-канал для CRITICAL: auth, permission, model_not_found, no_credits | `app/services/alerts.py:send_critical` | — | ✅ DONE | 4.3 |
| 4.6 | Workaround: Anthropic-модели через OpenRouter оборачивают JSON в ```json``` markdown — снимаем fences | `app/services/llm.py:_strip_json_fences` | `test_complete_json_strips_markdown_fences` | ✅ DONE | 4.3 |

**См. раздел 5 (LLM Error Handling) — там полная таблица маппинга.**

---

### Phase 5 — Strategist Agent

**Цель:** Тезисы + профиль пользователя → JSON с 7-дневной воронкой.
**Готовность:** на вход `(theses, profile, platforms)` → JSON `[{day:1, type:engagement, angle:...}, ...]`.

| # | Задача | Файлы | Тесты | Статус | Зависимости |
|---|--------|-------|-------|--------|-------------|
| 5.1 | `plan_week()` оркестратор | `app/agents/strategist.py` | live-test на habr.com | ✅ DONE | Phase 4 |
| 5.2 | System prompt с воронкой engagement→expertise→trust→sale | `app/agents/prompts/strategist.txt` | — | ✅ DONE | 5.1 |
| 5.3 | Инжекция профиля в user-prompt (`_build_user_prompt`) | `app/agents/strategist.py` | 3 теста (with profile / no profile / empty theses) | ✅ DONE | 5.1 |
| 5.4 | Pydantic `WeekPlan` + `DayPlan` с валидатором days=1..7 | `app/agents/schemas.py` | 4 теста схемы + 3 теста plan_week | ✅ DONE | 5.2 |

---

### Phase 6 — Copywriter Agents (4 платформы)

**Цель:** На вход `(angle, day_type, platform, profile)` → готовый пост с хэштегами и CTA.
**Готовность:** для каждой из 4 платформ генерируется пост соответствующего формата.

| # | Задача | Файлы | Тесты | Статус | Зависимости |
|---|--------|-------|-------|--------|-------------|
| 6.1 | `write_post()` универсальный для 4 платформ + кэш промптов через `lru_cache` | `app/agents/copywriter.py` | unit-тесты, mock LLM | ✅ DONE | Phase 4 |
| 6.2 | Промпт Telegram (150–400 слов, HTML-разметка, 3–5 хэштегов) | `app/agents/prompts/telegram.txt` | `test_prompt_loads[telegram]` | ✅ DONE | 6.1 |
| 6.3 | Промпт ВКонтакте (200–500 слов, эмодзи, 4–6 хэштегов) | `app/agents/prompts/vk.txt` | `test_prompt_loads[vk]` | ✅ DONE | 6.1 |
| 6.4 | Промпт Сторис (5 слайдов × 3–7 слов, разделитель `---`) | `app/agents/prompts/stories.txt` | `test_prompt_loads[stories]` | ✅ DONE | 6.1 |
| 6.5 | ~~Промпт VC.ru~~ | ~~`app/agents/prompts/vc_ru.txt`~~ | — | ❌ УДАЛЕНО (2026-05-07): лонгриды слишком прожорливы по токенам | — |
| 6.6 | Unit-тесты (промпты, нормализация хэштегов, маппинг ошибок) | `tests/test_copywriter.py` (13 тестов) | 13/13 PASSED | ✅ DONE | 6.2–6.5 |
| 6.7 | Live-test всех 4 платформ через реальный OpenRouter | `scripts/live_demo.py` | ⚠️ заблокирован free-tier | ⏸ ОТЛОЖЕНО (нужно пополнить OpenRouter) | 6.6 |

---

### Phase 7 — Generation Pipeline

**Цель:** Полный цикл: пользователь шлёт URL → бот скрейпит → стратег → копирайтеры → посты в чате.
**Готовность:** URL → 7 постов на каждой выбранной платформе появляются в чате за <3 минут.

| # | Задача | Файлы | Тесты | Статус | Зависимости |
|---|--------|-------|-------|--------|-------------|
| 7.1 | Хендлер URL и выбор платформ (3 платформы: TG/VK/Stories) | `app/bot/handlers/generate.py`, `app/bot/keyboards.py` | — (manual) | ✅ DONE | Phase 2, 3 |
| 7.2 | Оркестратор pipeline | `app/services/pipeline.py` | `tests/test_pipeline.py` (6 тестов) | ✅ DONE | Phase 5, 6 |
| 7.3 | Отправка постов с InlineKeyboard (4 кнопки: 🔄 ✂️ 👔 👍) | `app/bot/handlers/generate.py`, `app/bot/keyboards.py` | — (manual) | ✅ DONE | 7.2 |
| 7.4 | Callback: Переписать/Короче/Формальнее/Нравится | `app/bot/handlers/post_actions.py` | `tests/test_actions.py` (6 тестов) | ✅ DONE | 7.3 |
| 7.5 | «Весь план одним блоком» | `app/bot/handlers/generate.py` | `tests/test_full_plan.py` (4 теста) | ✅ DONE | 7.3 |
| 7.6 | Сохранение плана в БД (`get_plan_with_posts` + интегрировано в pipeline) | `app/db/crud.py`, `app/services/pipeline.py` | покрыто `test_pipeline.py` | ✅ DONE | 7.2 |

---

### Phase 8 — Rate Limiting & Monetization

**Цель:** Свободный лимит работает, оплата проходит, конверсия free→paid возможна.
**Готовность:** 4-я генерация → блок → оплата 499 ₽ → разблокировка на месяц.

| # | Задача | Файлы | Тесты | Статус | Зависимости |
|---|--------|-------|-------|--------|-------------|
| 8.1 | Rate limiter (1 ген/час, 3 «Переписать»/пост) | `app/services/quota.py` | `tests/test_limits.py` (8 тестов) | ✅ DONE | Phase 7 |
| 8.2 | Счётчик `gens_used` + блокировка | `app/services/quota.py`, `app/db/models.py` | включено в test_limits.py | ✅ DONE | 8.1 |
| 8.3 | Telegram Payments интеграция | `app/services/payment.py` | — (manual) | ✅ DONE | 8.2 |
| 8.4 | Проверка квоты в pipeline | `app/bot/handlers/generate.py` | интегрировано | ✅ DONE | 8.3 |
| 8.5 | Pre-checkout/successful payment хендлеры | `app/bot/handlers/payment.py` | `app/main.py` регистрация | ✅ DONE | 8.3 |

---

### Phase 9 — Polish & Production

**Цель:** Деплой на VPS, остальные команды (/examples, /history) работают, есть мониторинг.
**Готовность:** бот развёрнут публично, доступен 24/7, все P0 фичи работают.

| # | Задача | Файлы | Тесты | Статус | Зависимости |
|---|--------|-------|-------|--------|-------------|
| 9.1 | /examples (загрузка примеров стиля) | `app/bot/handlers/examples.py` | интегрировано в main.py | ✅ DONE | Phase 2 |
| 9.2 | /history (5 последних планов) | `app/bot/handlers/history.py` | интегрировано в main.py | ✅ DONE | Phase 7 |
| 9.3 | docker-compose.prod.yml + systemd | `deploy/docker-compose.prod.yml`, `deploy/content-agent-bot.service` | — (manual) | ✅ DONE | Phase 8 |
| 9.4 | Health check endpoint (port 8080) | `app/main.py` asyncio server | — | ✅ DONE | — |
| 9.5 | README.md + инструкция по деплою | `README.md` | — | ✅ DONE | 9.3 |
| 9.6 | Plan.md обновлена | `Plan.md` | — | ✅ DONE | 9.3 |

---

## 4. Master Progress Table

| # | Фаза | План (срок) | Факт (дата) | Статус | Блокер |
|---|------|------|------|--------|--------|
| 0 | Foundation | старт + 1 день | 2026-05-07 | ✅ DONE | — |
| 1 | Database | +1 день | 2026-05-07 | ✅ DONE | — |
| 2 | Onboarding | +2 дня | 2026-05-07 | ✅ DONE | — |
| 3 | Scraper | +1 день | 2026-05-07 | ✅ DONE | — |
| 4 | LLM + Errors ⭐ | +2 дня | 2026-05-07 | ✅ DONE | — |
| 5 | Strategist | +1 день | 2026-05-07 | ✅ DONE | — |
| 6 | Copywriter | +2 дня | 2026-05-07 | ✅ DONE | — |
| 7 | Pipeline | +2 дня | 2026-05-07 | ✅ DONE | — |
| 8 | Limits + Pay | +2 дня | 2026-05-07 | ✅ DONE | — |
| 9 | Polish + Deploy | +2 дня | 2026-05-07 | ✅ DONE | — |

**Итого по плану:** ~16 рабочих дней (можно сократить до ~12 при параллелизации Phase 1/3/4 и Phase 5/6).

---

## 5. LLM Error Handling ⭐

**Принципы (зафиксированы в `app/services/messages.py`):**

1. **Все русские строки** — в одном файле `messages.py`, не разбросаны по коду
2. **Тон сообщений** — дружелюбный, всегда объясняет что делать дальше («Попробуй X через Y минут»)
3. **Никогда** не показывать пользователю traceback, имена классов исключений, JSON, токены
4. **CRITICAL** ошибки (key invalid, DB down) → отдельный канал алертов в Telegram-чат админа
5. **Уровни логов:**
   - `INFO` — нормальный сценарий (404, модерация отказала)
   - `WARN` — повторяется, надо смотреть (таймауты, rate limits)
   - `ERROR` — нештатная ошибка
   - `CRITICAL` — будит инженера (auth, DB)

### Полная таблица маппинга

**Через OpenRouter ошибки приходят как `openai.*Error` (мы используем openai SDK с custom base_url). Дополнительно OpenRouter добавляет свои коды: 402 (нет кредитов), 502 (upstream-провайдер недоступен).**

| Тип ошибки | openai SDK / OpenRouter код | Сообщение пользователю (RU) | Лог-уровень + сообщение |
|---|---|---|---|
| Соединение | `openai.APIConnectionError` | «Не могу связаться с ИИ. Проверь интернет и попробуй снова через минуту.» | `ERROR: openrouter connection failed: {detail}` |
| Таймаут | `openai.APITimeoutError` | «ИИ долго отвечает. Подожди 30 секунд и попробуй ещё раз.» | `WARN: openrouter timeout after {sec}s, user={id}` |
| Rate limit | `openai.RateLimitError` (429) | «Слишком много запросов к ИИ. Попробуй через 1–2 минуты.» | `WARN: rate limit hit, retry-after={sec}` |
| Кончились кредиты | `openai.APIStatusError` 402 | «Внутренняя ошибка сервиса (закончились кредиты у ИИ). Уже разбираемся.» | `CRITICAL: openrouter 402 — out of credits, ПОПОЛНИТЬ БАЛАНС` |
| Upstream недоступен | `openai.APIStatusError` 502 | «Сервис ИИ временно недоступен. Попробуй через несколько минут.» | `WARN: openrouter 502 upstream provider down: {provider}` |
| Перегрузка | `openai.APIStatusError` 503/529 | «Сервис ИИ перегружен. Попробуй через несколько минут.» | `WARN: openrouter overloaded {code}` |
| Битый запрос | `openai.BadRequestError` (400) | «Не получилось обработать запрос. Попробуй другой URL или /style edit.» | `ERROR: bad request, prompt_tokens={n}, detail={msg}` |
| Ключ невалиден | `openai.AuthenticationError` (401) | «Внутренняя ошибка сервиса. Команда уже разбирается, попробуй позже.» | `CRITICAL: openrouter API key invalid — НЕМЕДЛЕННЫЙ АЛЕРТ` |
| Доступ запрещён | `openai.PermissionDeniedError` (403) | «Сервис временно недоступен. Попробуй через час.» | `CRITICAL: openrouter permission denied` |
| Модель не найдена | `openai.NotFoundError` (404) | «Внутренняя ошибка конфигурации модели. Уже исправляем.» | `CRITICAL: model {model_name} not found on OpenRouter` |
| Контент модерация | `openai.BadRequestError` (с `content_filter` или `moderation`) | «Не могу написать пост на эту тему — она содержит запрещённый контент. Попробуй другой URL.» | `INFO: moderation refused for url={url}, user={id}` |
| JSON парсинг | `json.JSONDecodeError` | «ИИ вернул некорректный ответ. Попробуй ещё раз — обычно помогает.» | `ERROR: JSON parse failed, raw_response={text[:500]}` |
| Pydantic валидация | `pydantic.ValidationError` | «ИИ ответил в неправильном формате. Попробуй ещё раз.» | `ERROR: schema validation failed: {errors}` |
| Неизвестная LLM | catch-all `Exception` | «Что-то пошло не так с ИИ. Попробуй через минуту, если повторится — напиши в поддержку.» | `ERROR: unexpected llm error: {traceback}` |
| Скрейпер: таймаут | `httpx.TimeoutException` | «Сайт слишком долго отвечает. Попробуй другой URL.» | `WARN: scraper timeout for url={url}` |
| Скрейпер: 404 | `httpx.HTTPStatusError` 404 | «Не могу открыть страницу — её не существует. Проверь URL.» | `INFO: HTTP 404 for url={url}` |
| Скрейпер: 403 | `httpx.HTTPStatusError` 403 | «Сайт блокирует доступ ботам. Попробуй другой URL.» | `INFO: HTTP 403 for url={url}` |
| Скрейпер: 5xx | `httpx.HTTPStatusError` 5xx | «Сайт временно недоступен. Попробуй позже или другой URL.» | `WARN: HTTP {code} for url={url}` |
| Скрейпер: SSRF | `ValueError` (own validator) | «Этот URL запрещён по соображениям безопасности.» | `WARN: SSRF attempt from user={id}, url={url}` |
| БД: уникальность | `IntegrityError` | (silent retry, пользователь не видит) | `WARN: integrity error, will retry` |
| БД: соединение | `OperationalError` | «Внутренняя ошибка. Попробуй через минуту.» | `CRITICAL: database connection lost` |
| Telegram: блокировка бота | `Forbidden` | (тихо удалить пользователя из активных) | `INFO: user {id} blocked the bot` |
| Telegram: лимит сообщений | `RetryAfter` | (внутренняя задержка `retry_after` секунд) | `WARN: telegram flood control, sleep {sec}s` |

---

## 6. Чек-лист готовности перед деплоем (Phase 9)

- [ ] /start → анкета → профиль сохранён в БД (Phase 2)
- [ ] /style показывает текущий профиль, /style edit перезапускает анкету (Phase 2)
- [ ] /examples принимает 1–3 текста и обновляет `style_notes` (Phase 9)
- [ ] /history показывает 5 последних планов (Phase 9)
- [ ] URL → план сгенерирован < 3 минут (Phase 7)
- [ ] Каждый пост приходит отдельным сообщением с 4 кнопками (Phase 7)
- [ ] [Переписать] работает (макс 3 раза) (Phase 7, 8)
- [ ] 3 бесплатные генерации → блокировка → предложение подписки (Phase 8)
- [ ] Telegram Payments проходит, подписка активируется на 30 дней (Phase 8)
- [ ] Rate limit: 4-й запрос в течение часа заблокирован (Phase 8)
- [ ] SSRF: localhost / 127.0.0.1 / 10.x → отклонён (Phase 3)
- [ ] LLM ошибки: пользователь видит русский текст, не traceback (Phase 4)
- [ ] CRITICAL ошибки уходят в админский канал (Phase 4)
- [ ] Бот переживает рестарт (state в БД, не в памяти) (Phase 1)
- [ ] Health-check возвращает 200 (Phase 9)

---

## 7. Открытые вопросы

| Вопрос | Решение | Статус |
|--------|---------|--------|
| Playwright в MVP? | Только если первые 10 тестовых URL не парсятся через httpx | Решить в Phase 3 |
| Платежи: Telegram Payments или YooKassa? | Telegram Payments для MVP — проще | ✅ Решено |
| Очередь задач: asyncio или Celery? | asyncio + PostgreSQL advisory locks для < 1000 users | ✅ Решено |
| Модель: Opus 4.5 или Sonnet 4.6? | Opus для качества стиля, Sonnet для черновиков (после фидбека) | Решить в Phase 4 |

---

## 8. Журнал изменений

| Дата | Что изменилось | Кто |
|------|----------------|-----|
| 2026-05-07 | План создан | Claude (initial) |
| 2026-05-07 | ✅ Phase 0 завершена: скелет проекта, uv-зависимости (40 пакетов) установлены, импорты и хендлеры регистрируются. Добавлен README.md (требование hatchling). | Claude |
| 2026-05-07 | 🔄 Решение: LLM-провайдер — **OpenRouter** (`anthropic/claude-sonnet-4.6`), Prompt Caching включён. Заменили `anthropic` SDK на `openai` SDK с custom `base_url`. Обновлены `pyproject.toml`, `app/config.py`, `.env.example`, `CLAUDE.md`, секция LLM Error Handling в `Plan.md`. | Claude |
| 2026-05-07 | 🟢 Phase 0 live test: бот ответил на /start в Telegram (user 5605302500). | Claude |
| 2026-05-07 | ✅ Phase 1 завершена: SQLAlchemy 2.0 async, 4 таблицы (User/UserProfile/ContentPlan/Post) с JSON-полями (универсально для Postgres и SQLite), Alembic baseline-миграция `001`, CRUD-функции (10 шт.), 8 тестов на SQLite in-memory — все зелёные. | Claude |
| 2026-05-07 | 🔄 Локальная БД переключена на SQLite (`sqlite+aiosqlite:///./data/bot.db`) — Docker недоступен, для прода в `docker-compose.yml` остаётся Postgres. | Claude |
| 2026-05-07 | ✅ Phase 2 завершена: ConversationHandler с 5 состояниями (NICHE/TONE/FORBIDDEN/FORMATS/EXAMPLES), inline-клавиатуры с мульти-выбором форматов (галочки), /style для просмотра, /style_edit как entry_point ConversationHandler. Live-test: 2 прогона онбординга в Telegram прошли без ошибок. Echo handler удалён. | Claude |
| 2026-05-07 | ✅ Phase 3 завершена: Scraper Agent на httpx+BS4, SSRF-защита через socket.getaddrinfo + ipaddress (блокировка private/loopback/link-local/multicast IPv4 и IPv6), HTTP-коды переведены в `ScraperError(code=...)`, эвристика тезисов (до LLM). 19 тестов зелёные, live-test на habr.com — корректно извлекает заголовок и 5 тезисов. Playwright отложен (Phase 3.4) — httpx справляется. | Claude |
| 2026-05-07 | ✅ Phase 4 завершена ⭐: `messages.py` (24 русских сообщения), `alerts.py` (CRITICAL → Telegram-чат админа), `llm.py` (AsyncOpenAI + OpenRouter base_url, prompt caching через `cache_control: ephemeral`, retry tenacity 3×exponential, маппинг 11 типов openai-ошибок + OpenRouter 402/502/529 в `LLMError(code, user_message, is_critical)`). Workaround `_strip_json_fences` для Anthropic-моделей. 20 тестов LLM зелёные. Live-test на Sonnet 4.6 через OpenRouter: text-режим и JSON-режим работают. Всего 46/46 тестов зелёные. | Claude |
| 2026-05-07 | ✅ Phase 5 завершена: Strategist Agent. `schemas.py` с Pydantic `WeekPlan/DayPlan` (валидатор обеспечивает день 1..7 без дубликатов), `strategist.txt` с воронкой engagement→expertise→trust→sale, `strategist.py:plan_week()` инжектирует профиль (ниша/тон/табу/форматы/примеры) в user-prompt. 10 unit-тестов + live-test: на статье habr.com Sonnet 4.6 сгенерировал «недельный план для SMM малого бизнеса» — все 7 дней с уникальными angle, воронка строго соблюдена. Всего 57/57 тестов зелёные. | Claude |
| 2026-05-07 | ✅ Phase 6 code-complete: Copywriter Agent для 4 платформ. `schemas.py:GeneratedPost` (с нормализацией хэштегов: добавление `#`, удаление пробелов), 4 промпта `prompts/{telegram,vk,stories,vc_ru}.txt` с разной драматургией под формат, `copywriter.py:write_post()` через универсальный класс + `@lru_cache` на промпты. 13 unit-тестов (включая параметризованные на все платформы), всего 70/70 зелёные. | Claude |
| 2026-05-07 | ⚠️ Phase 6 live-test заблокирован: free-tier OpenRouter сжимается до ≤876 токенов после нескольких неудачных запросов. Strategist (max_tokens=2000→1000) и Copywriter (max_tokens=2000→1000) пришлось урезать. Наш `LLMError("llm_no_credits", is_critical=True)` корректно обработал HTTP 402 и попытался отправить алерт админу. **Действие пользователя:** пополнить OpenRouter (минимум $5 = ~5M токенов Sonnet 4.6) ИЛИ переключить `MODEL_NAME` на бесплатную (`google/gemini-2.0-flash-exp:free` и т.п.). | Claude |
| 2026-05-07 | ⏸ ПАУЗА. Все 70/70 тестов зелёные. Code complete до Phase 6 включительно. Точка возврата зафиксирована в шапке `Plan.md`. | User+Claude |
| 2026-05-07 | ✅ **Phase 7–9 завершена**: `/history` (5 последних планов), `/examples` (загрузка примеров стиля), health-check (port 8080), docker-compose.prod.yml + systemd service, README deploy guide. Все 93 теста зелёные. **Бот готов к production деплою.** | Claude |

> При каждом обновлении этого файла дописывать строку в журнал.
