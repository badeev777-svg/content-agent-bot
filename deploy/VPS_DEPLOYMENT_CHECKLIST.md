# ✅ VPS Deployment Checklist — jino.ru

**VPS Parameters:**
- Хост: 130e66479b71.vps.myjino.ru
- IP: 81.177.6.131
- Порт SSH: 49386
- Логин: root
- Пароль: (установить в консоли jino.ru)

## 🚀 Quick Start (Systemd)

Рекомендуется использовать systemd для работы в production.

### 1️⃣ Подключение к VPS

```bash
ssh -p 49386 root@130e66479b71.vps.myjino.ru
```

### 2️⃣ Инициализация сервера

```bash
# Скачайте и запустите init скрипт
curl -fsSL https://raw.githubusercontent.com/badeev777-svg/content-agent-bot/main/deploy/init-server.sh | sudo bash

# Перезагрузитесь если требуется
sudo reboot
```

### 3️⃣ Клонирование проекта

```bash
cd /opt
sudo git clone https://github.com/badeev777-svg/content-agent-bot.git
cd content-agent-bot
sudo chown -R $USER:$USER .
```

### 4️⃣ Установка Python + зависимостей

```bash
apt update && apt install -y python3.11 python3.11-venv python3-pip postgresql postgresql-contrib
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### 5️⃣ Подготовка окружения

```bash
# Копируйте шаблон
cp deploy/.env.production.template .env.production

# Отредактируйте значения
nano .env.production
```

**Что нужно изменить:**
- `TELEGRAM_BOT_TOKEN` — токен от @BotFather
- `OPENROUTER_API_KEY` — ключ с https://openrouter.ai/keys
- `ADMIN_TELEGRAM_CHAT_ID` — ваш chat ID (от @userinfobot)
- `TELEGRAM_PAYMENT_TOKEN` — платежный токен от @BotFather
- Database пароль (сгенерируйте сильный пароль)

### 6️⃣ Инициализация БД

```bash
alembic upgrade head
```

### 7️⃣ Установка systemd сервиса

```bash
sudo cp deploy/content-agent-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable content-agent-bot
sudo systemctl start content-agent-bot
```

### 8️⃣ Проверка статуса

```bash
# Статус сервиса
sudo systemctl status content-agent-bot

# Логи (live)
sudo journalctl -u content-agent-bot -f

# Проверка бота
# Напишите в Telegram боту /start
```

## 📊 Мониторинг

```bash
# Статус
sudo systemctl status content-agent-bot

# Последние 50 строк логов
sudo journalctl -u content-agent-bot -n 50

# Поиск ошибок
sudo journalctl -u content-agent-bot | grep ERROR

# Следить в реальном времени
sudo journalctl -u content-agent-bot -f
```

## 🔧 Обслуживание

**Перезагрузить сервис:**
```bash
sudo systemctl restart content-agent-bot
```

**Остановить:**
```bash
sudo systemctl stop content-agent-bot
```

**Обновить код:**
```bash
cd /opt/content-agent-bot
git pull origin main
source venv/bin/activate
pip install -e .
alembic upgrade head
sudo systemctl restart content-agent-bot
```

## 🆘 Troubleshooting

**Бот не отвечает:**
1. Проверьте логи: `sudo journalctl -u content-agent-bot -n 50`
2. Проверьте .env: токены и API ключи должны быть валидны
3. Перезагрузитесь: `sudo systemctl restart content-agent-bot`

**PostgreSQL не стартует:**
```bash
sudo systemctl start postgresql
sudo systemctl status postgresql
```

**Недостаточно памяти:**
```bash
# Создать/увеличить swap
sudo dd if=/dev/zero of=/swapfile bs=1G count=2
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

**Проверить порты:**
```bash
# Смотрите какие порты занят
sudo netstat -tlnp | grep python
```

---

**Created:** 2026-05-08
**Status:** Ready for deployment
**Tests:** 93/93 passing ✅
