#!/bin/bash
set -e

echo "======================================"
echo "Установка зависимостей для сервера"
echo "======================================"

# Обновление системы
echo "📦 Обновление системы..."
sudo apt-get update
sudo apt-get upgrade -y

# Установка необходимых пакетов
echo "📦 Установка базовых пакетов..."
sudo apt-get install -y \
    curl \
    wget \
    git \
    build-essential \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release \
    ufw

# Установка Docker
echo "🐳 Установка Docker..."
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo \
  "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Добавление пользователя в группу docker
echo "👤 Настройка прав для docker..."
sudo usermod -aG docker $USER
newgrp docker

# Проверка установки
echo "✅ Проверка установки Docker..."
docker --version
docker compose version

echo ""
echo "======================================"
echo "✅ Зависимости установлены успешно!"
echo "======================================"
echo ""
echo "⚠️  ВАЖНО: Перезагрузитесь чтобы применить права на docker:"
echo "    sudo reboot"
echo ""
