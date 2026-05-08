# ⚡ Быстрый старт (5 минут)

Если у вас уже есть сервер на jino.ru и вы хотите начать быстро.

## ✅ Предварительный чек-лист

- [ ] Сервер с Ubuntu 24.04 LTS заказан
- [ ] У вас есть SSH доступ (root)
- [ ] Готов Telegram Bot Token
- [ ] Готов OpenRouter API Key
- [ ] Придуман сильный пароль для БД

## 🚀 Запуск (скопируй и вставь)

```bash
# 1. Подключись к серверу
ssh root@YOUR_VPS_IP

# 2. Скачай и запусти инициализацию (автоматизирует первые шаги)
curl -fsSL https://raw.githubusercontent.com/badeev777-svg/content-agent-bot/main/deploy/init-server.sh | sudo bash

# 3. Перезагрузись (если требуется)
sudo reboot

# 4. Установи Docker
sudo bash /opt/content-agent-bot/deploy/install-dependencies.sh

# 5. Перезагрузись ещё раз
sudo reboot

# 6. Инициализируй приложение
sudo /opt/content-agent-bot/deploy/setup.sh

# 7. Открой .env и заполни значения
sudo nano /opt/content-agent-bot/.env
# Нажми Ctrl+X, Y, Enter для сохранения

# 8. Развёртывание!
sudo /opt/content-agent-bot/deploy/deploy-docker.sh
```

## 📋 Что нужно отредактировать в .env

```env
TELEGRAM_BOT_TOKEN=ваш_токен_от_botfather
OPENROUTER_API_KEY=sk-or-ваш_ключ
POSTGRES_PASSWORD=ОЧЕНЬ_СИЛЬНЫЙ_ПАРОЛЬ_20_СИМВОЛОВ
ADMIN_TELEGRAM_CHAT_ID=ваш_telegram_id
```

## ✅ Всё работает?

```bash
# Проверка контейнеров
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml ps

# Должно вывести:
# NAME                     STATUS
# content-agent-bot        Up
# content-agent-postgres   Up
```

## 🔍 Логи в реальном времени

```bash
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml logs -f bot
```

Если видишь "Polling started" — всё работает! 🎉

## 🛑 Если что-то не так

### Приложение падает сразу

```bash
# Проверь .env
sudo cat /opt/content-agent-bot/.env

# Убедись что все переменные заполнены:
# TELEGRAM_BOT_TOKEN=НЕ_пусто
# OPENROUTER_API_KEY=НЕ_пусто
# POSTGRES_PASSWORD=заполнено
```

### БД не инициализируется

```bash
# Пересоздай контейнеры
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml down -v
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml up -d
```

### Порт 8080 занят

```bash
# Проверь что занимает порт
sudo lsof -i :8080

# Если что-то другое, останови это
# или используй другой порт в docker-compose.prod.yml
```

## 📚 Дальше

После успешного развёртывания читай полное руководство: [DEPLOYMENT.md](./DEPLOYMENT.md)

---

**Готово! Бот должен быть онлайн в Telegram. Отправь ему сообщение и проверь. 🤖**
