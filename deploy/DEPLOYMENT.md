# 🚀 Развёртывание Content Agent Bot на jino.ru VPS

Полное руководство по развёртыванию бота на production сервере.

## Предварительные требования

- **VPS**: jino.ru Бета (599 ₽/мес)
  - 2 ядра × 2000 МГц
  - 4 GB RAM
  - 20 GB SSD
- **ОС**: Ubuntu 24.04 LTS
- **SSH доступ** к серверу
- **Заранее подготовленные**:
  - Telegram Bot Token (от @BotFather)
  - OpenRouter API Key
  - Пароль базы данных (безопасный)

## Пошаговое развёртывание

### Этап 0: Подключение к серверу

```bash
ssh root@YOUR_VPS_IP
```

### Этап 1: Инициальная настройка сервера

```bash
# Скачивание скрипта инициализации
curl -fsSL https://raw.githubusercontent.com/badeev777-svg/content-agent-bot/main/deploy/init-server.sh | sudo bash

# Перезагрузка сервера (если требуется)
sudo reboot
```

**Что делает скрипт:**
- ✅ Обновляет систему
- ✅ Настраивает время на UTC
- ✅ Создаёт 2GB swap (если нужна стабильность)
- ✅ Настраивает firewall (UFW)
- ✅ Разрешает SSH (22), HTTP (80), HTTPS (443)
- ✅ Включает журналирование логов

### Этап 2: Установка Docker

```bash
sudo bash /opt/content-agent-bot/deploy/install-dependencies.sh
```

После скрипта может потребоваться перезагрузка:

```bash
sudo reboot
```

Проверка установки:

```bash
docker --version
docker compose version
```

### Этап 3: Загрузка проекта на сервер

Если проект ещё не на сервере:

```bash
# Вариант 1: Клонирование из GitHub
cd /opt
sudo git clone https://github.com/badeev777-svg/content-agent-bot.git
cd content-agent-bot
sudo chown -R $USER:$USER .

# Вариант 2: Загрузка через SCP (с локального компьютера)
scp -r ./content-agent-bot/* root@YOUR_VPS_IP:/opt/content-agent-bot/
```

### Этап 4: Инициализация приложения

```bash
sudo /opt/content-agent-bot/deploy/setup.sh
```

Скрипт создаст:
- Пользователя `bot` для сервиса
- Папку для логов
- Systemd сервис

### Этап 5: Конфигурация переменных окружения

```bash
# Отредактируйте .env файл
sudo nano /opt/content-agent-bot/.env
```

**Необходимо изменить:**

```env
# Telegram
TELEGRAM_BOT_TOKEN=your_real_token_here

# OpenRouter API
OPENROUTER_API_KEY=sk-or-your_real_key_here

# Database Password (ОБЯЗАТЕЛЬНО ИЗМЕНИТЕ!)
POSTGRES_PASSWORD=STRONG_PASSWORD_HERE

# Admin Chat ID для ошибок
ADMIN_TELEGRAM_CHAT_ID=YOUR_TELEGRAM_ID

# Payment Token (если нужны платежи)
TELEGRAM_PAYMENT_TOKEN=your_payment_token
```

**Советы по безопасности:**
- Используйте сильный пароль для PostgreSQL (20+ символов)
- Не делитесь `.env` файлом
- Используйте разные токены для dev и prod
- Добавьте `.env` в `.gitignore`

### Этап 6: Развёртывание с Docker

```bash
sudo /opt/content-agent-bot/deploy/deploy-docker.sh
```

Скрипт автоматически:
- 🔨 Соберёт Docker образ
- 🚀 Запустит контейнеры (bot + postgres)
- 🔄 Применит миграции БД
- ✅ Проверит статус

### Этап 7: Проверка статуса

```bash
# Просмотр статуса контейнеров
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml ps

# Проверка логов
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml logs -f bot

# Тест здоровья
curl http://localhost:8080/health
```

## 🔧 Управление сервисом (Docker)

### Просмотр логов

```bash
# Последние 50 строк
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml logs --tail=50 bot

# Постоянный поток
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml logs -f bot

# Логи PostgreSQL
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml logs postgres
```

### Перезагрузка приложения

```bash
# Мягкая перезагрузка
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml restart bot

# Полная перезагрузка
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml restart

# Остановка
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml down
```

### Вход в контейнер

```bash
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml exec bot bash
```

### Обновление кода

```bash
cd /opt/content-agent-bot
git pull origin main
docker compose -f deploy/docker-compose.prod.yml build
docker compose -f deploy/docker-compose.prod.yml up -d
```

## 📊 Мониторинг

### Проверка использования ресурсов

```bash
# Docker статистика
docker stats

# Размер БД
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml exec postgres \
  psql -U bot -d content_agent -c "SELECT pg_size_pretty(pg_database_size('content_agent'));"

# Количество пользователей
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml exec postgres \
  psql -U bot -d content_agent -c "SELECT COUNT(*) as users FROM users;"
```

### Резервная копия БД

```bash
# Создание дампа БД
mkdir -p /opt/backups
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml exec postgres \
  pg_dump -U bot content_agent > /opt/backups/content_agent_$(date +%Y%m%d_%H%M%S).sql

# Восстановление из дампа
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml exec -T postgres \
  psql -U bot content_agent < /opt/backups/content_agent_YYYY-MM-DD.sql
```

## 🐛 Решение проблем

### БД не инициализируется

```bash
# Проверка логов PostgreSQL
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml logs postgres

# Проверка здоровья БД
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml exec postgres \
  pg_isready -U bot
```

### Приложение не запускается

```bash
# Проверка .env
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml config

# Проверка логов
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml logs bot

# Проверка портов
sudo netstat -tlnp | grep LISTEN
```

### Ошибки подключения к API

Проверьте переменные в `.env`:
- `OPENROUTER_API_KEY` — правильный ключ?
- `TELEGRAM_BOT_TOKEN` — актуален?
- `DATABASE_URL` — правильное имя контейнера (`postgres` для Docker)?

### Нехватка места на диске

```bash
# Проверка использования диска
df -h

# Очистка старых Docker слоёв
docker image prune -a
docker volume prune
```

## 📈 Масштабирование (на будущее)

Если потребуется больше мощности:

1. **Увеличить ресурсы VPS** (Гамма план: 8 GB RAM, 2 ядра)
2. **Добавить Redis** для кеша
3. **Использовать reverse proxy** (Nginx)
4. **Настроить автоскейлинг** (Kubernetes, но это сложно для MVP)

## 📞 Поддержка

Если что-то не работает:

1. Проверьте логи: `docker compose logs -f bot`
2. Убедитесь, что `.env` заполнен корректно
3. Проверьте доступ в интернет: `curl https://api.openrouter.ai`
4. Откройте issue на GitHub

---

**Поздравляем! 🎉 Ваш Content Agent Bot успешно развёрнут в production!**
