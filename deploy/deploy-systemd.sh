#!/bin/bash
set -e

APP_DIR="/opt/content-agent-bot"

echo "======================================"
echo "Развёртывание Content Agent Bot (systemd)"
echo "======================================"
echo ""

# Проверка прав доступа
if [[ $EUID -ne 0 ]]; then
   echo "❌ Этот скрипт должен запускаться с sudo"
   exit 1
fi

# Проверка наличия .env файла
if [ ! -f "$APP_DIR/.env" ]; then
    echo "❌ Файл .env не найден в $APP_DIR"
    exit 1
fi

cd "$APP_DIR"

# Остановка сервиса если он запущен
echo "🛑 Остановка существующего сервиса..."
systemctl stop content-agent-bot || true

# Создание виртуального окружения
echo "🔧 Создание виртуального окружения..."
if [ ! -d "$APP_DIR/.venv" ]; then
    python3 -m venv "$APP_DIR/.venv"
fi

# Активация venv и установка зависимостей
echo "📦 Установка зависимостей..."
source "$APP_DIR/.venv/bin/activate"
pip install --upgrade pip
pip install -e .

# Изменение прав доступа
chown -R bot:bot "$APP_DIR"
chmod 750 "$APP_DIR"
chmod 640 "$APP_DIR/.env"

# Запуск миграций БД
echo "🔄 Запуск миграций базы данных..."
"$APP_DIR/.venv/bin/alembic" upgrade head || echo "⚠️  Миграции уже применены"

# Запуск сервиса
echo "🚀 Запуск сервиса..."
systemctl start content-agent-bot
systemctl enable content-agent-bot

# Проверка статуса
sleep 2
echo ""
echo "======================================"
echo "✅ Развёртывание завершено!"
echo "======================================"
echo ""
echo "📊 Статус сервиса:"
systemctl status content-agent-bot
echo ""
echo "📋 Последние логи:"
journalctl -u content-agent-bot -n 20 --no-pager
echo ""
echo "🔍 Команды для управления:"
echo "   Статус:         sudo systemctl status content-agent-bot"
echo "   Логи:           sudo journalctl -u content-agent-bot -f"
echo "   Перезагрузка:   sudo systemctl restart content-agent-bot"
echo "   Остановка:      sudo systemctl stop content-agent-bot"
echo ""
