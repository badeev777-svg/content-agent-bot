#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="/opt/content-agent-bot"

echo "======================================"
echo "Развёртывание Content Agent Bot (Docker)"
echo "======================================"
echo ""

# Проверка Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker не установлен. Запустите: sudo $SCRIPT_DIR/install-dependencies.sh"
    exit 1
fi

# Проверка наличия .env файла
if [ ! -f "$APP_DIR/.env" ]; then
    echo "❌ Файл .env не найден в $APP_DIR"
    exit 1
fi

cd "$APP_DIR"

# Остановка старых контейнеров
echo "🛑 Остановка существующих контейнеров..."
docker compose -f deploy/docker-compose.prod.yml down || true

# Сборка образа
echo "🔨 Сборка Docker образа..."
docker compose -f deploy/docker-compose.prod.yml build

# Запуск контейнеров
echo "🚀 Запуск контейнеров..."
docker compose -f deploy/docker-compose.prod.yml up -d

# Ожидание инициализации БД
echo "⏳ Ожидание инициализации PostgreSQL..."
sleep 5

# Проверка статуса
echo ""
echo "======================================"
echo "✅ Развёртывание завершено!"
echo "======================================"
echo ""
echo "📊 Статус контейнеров:"
docker compose -f deploy/docker-compose.prod.yml ps
echo ""
echo "📋 Последние логи:"
docker compose -f deploy/docker-compose.prod.yml logs --tail=20 bot
echo ""
echo "🔍 Команды для управления:"
echo "   Просмотр логов:     docker compose -f deploy/docker-compose.prod.yml logs -f bot"
echo "   Остановка:          docker compose -f deploy/docker-compose.prod.yml down"
echo "   Перезагрузка:       docker compose -f deploy/docker-compose.prod.yml restart bot"
echo "   Вход в контейнер:   docker compose -f deploy/docker-compose.prod.yml exec bot bash"
echo ""
