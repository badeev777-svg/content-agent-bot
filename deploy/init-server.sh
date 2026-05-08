#!/bin/bash
set -e

echo "======================================"
echo "Инициальная настройка сервера"
echo "======================================"
echo ""

# Проверка прав доступа
if [[ $EUID -ne 0 ]]; then
   echo "❌ Этот скрипт должен запускаться с sudo"
   exit 1
fi

# Обновление системного времени и часового пояса
echo "⏰ Настройка времени на UTC..."
timedatectl set-timezone UTC
timedatectl set-ntp yes
echo "✅ Время: $(date)"

# Настройка swap (если нужно, т.к. у нас 4GB RAM)
echo ""
echo "💾 Проверка swap..."
SWAP=$(free -h | grep -i swap | awk '{print $2}')
if [ "$SWAP" = "0B" ]; then
    echo "⚠️  Swap не настроен. Создаём 2GB swap..."
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "✅ Swap создан"
else
    echo "✅ Swap уже существует: $SWAP"
fi

# Настройка UFW (firewall)
echo ""
echo "🔒 Настройка firewall..."
ufw --force enable
ufw default deny incoming
ufw default allow outgoing

# Разрешение SSH
ufw allow 22/tcp
echo "✅ SSH (22) разрешён"

# Разрешение портов для приложения
echo "ℹ️  Разрешение портов для приложения..."
ufw allow 80/tcp  # HTTP (для LetsEncrypt)
ufw allow 443/tcp # HTTPS
echo "✅ HTTP (80) и HTTPS (443) разрешены"

# Сбор логов системы
echo ""
echo "📊 Включение persistent journalctl логирования..."
mkdir -p /var/log/journal
systemctl restart systemd-journald
echo "✅ Логи будут сохраняться в /var/log/journal"

# Настройка NTP для синхронизации времени
echo ""
echo "⏱️  Проверка синхронизации времени..."
systemctl enable systemd-timesyncd
systemctl start systemd-timesyncd
echo "✅ NTP синхронизация включена"

# Базовая оптимизация системы
echo ""
echo "🚀 Оптимизация системы..."

# Увеличение лимитов на открытые файлы
cat >> /etc/security/limits.conf << 'EOF'
*       soft    nofile  65535
*       hard    nofile  65535
*       soft    nproc   32768
*       hard    nproc   32768
EOF
echo "✅ Лимиты на открытые файлы увеличены"

echo ""
echo "======================================"
echo "✅ Инициальная настройка завершена!"
echo "======================================"
echo ""
echo "🔧 Далее:"
echo "   1. sudo $SCRIPT_DIR/install-dependencies.sh  — установка Docker"
echo "   2. Загрузить проект на сервер"
echo "   3. sudo $APP_DIR/deploy/setup.sh             — инициализация приложения"
echo "   4. Отредактировать $APP_DIR/.env"
echo "   5. sudo $APP_DIR/deploy/deploy-docker.sh     — развёртывание"
echo ""
