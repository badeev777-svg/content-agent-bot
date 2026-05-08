#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
APP_DIR="/opt/content-agent-bot"

echo "======================================"
echo "Инициализация Content Agent Bot"
echo "======================================"
echo "Проект: $PROJECT_DIR"
echo "Целевая папка: $APP_DIR"
echo ""

# Проверка прав доступа
if [[ $EUID -ne 0 ]]; then
   echo "❌ Этот скрипт должен запускаться с sudo"
   exit 1
fi

# Создание папки приложения
echo "📁 Создание папки приложения..."
mkdir -p "$APP_DIR"

# Копирование файлов проекта
echo "📋 Копирование файлов проекта..."
cp -r "$PROJECT_DIR"/* "$APP_DIR/"
cd "$APP_DIR"

# Проверка наличия .env файла
if [ ! -f "$APP_DIR/.env" ]; then
    echo "⚠️  Файл .env не найден!"
    echo "📝 Копирование .env.example в .env..."
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo ""
    echo "❌ ВАЖНО: Отредактируйте файл $APP_DIR/.env"
    echo "   Замените значения на реальные:"
    echo "   - TELEGRAM_BOT_TOKEN"
    echo "   - OPENROUTER_API_KEY"
    echo "   - POSTGRES_PASSWORD"
    echo "   - ADMIN_TELEGRAM_CHAT_ID"
    echo "   - TELEGRAM_PAYMENT_TOKEN"
    echo ""
    echo "   nano $APP_DIR/.env"
    exit 1
fi

# Создание пользователя для бота (если не существует)
echo "👤 Настройка пользователя для сервиса..."
if ! id "bot" &>/dev/null; then
    useradd -r -s /bin/false -d "$APP_DIR" -m bot
    echo "✅ Пользователь 'bot' создан"
else
    echo "✅ Пользователь 'bot' уже существует"
fi

# Установка прав доступа
chown -R bot:bot "$APP_DIR"
chmod 750 "$APP_DIR"
chmod 640 "$APP_DIR/.env"

# Создание папки для логов
mkdir -p /var/log/content-agent-bot
chown bot:bot /var/log/content-agent-bot
chmod 755 /var/log/content-agent-bot

# Копирование systemd service (если не используется Docker)
echo "⚙️  Настройка systemd сервиса..."
cp "$APP_DIR/deploy/content-agent-bot.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable content-agent-bot

echo ""
echo "======================================"
echo "✅ Инициализация завершена!"
echo "======================================"
echo ""
echo "🚀 Далее:"
echo "   1. Отредактируйте файл .env: nano $APP_DIR/.env"
echo "   2. Для запуска с Docker: $SCRIPT_DIR/deploy-docker.sh"
echo "   3. Для запуска с systemd: sudo systemctl start content-agent-bot"
echo ""
