# 🔧 Полезные команды для управления

## 🐳 Docker команды

### Просмотр статуса

```bash
# Статус всех контейнеров
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml ps

# Статус одного контейнера
docker ps | grep content-agent

# Детальная информация
docker inspect content-agent-bot
```

### Логи

```bash
# Последние 100 строк
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml logs --tail=100 bot

# Постоянный поток логов
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml logs -f bot

# С временными метками
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml logs -f --timestamps bot

# Только ошибки
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml logs bot 2>&1 | grep -i error
```

### Управление

```bash
# Перезагрузить приложение
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml restart bot

# Остановить
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml stop

# Запустить
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml start

# Полный перезапуск (с переостановкой БД)
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml down
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml up -d

# Вход в контейнер
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml exec bot bash

# Вход в БД
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml exec postgres psql -U bot -d content_agent
```

### Очистка

```bash
# Очистить неиспользуемые образы
docker image prune -a

# Очистить неиспользуемые volumes
docker volume prune

# Полная очистка (осторожно!)
docker system prune -a --volumes
```

## 🗄️ PostgreSQL команды

### Подключение к БД

```bash
# Из контейнера
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml exec postgres \
  psql -U bot -d content_agent

# Или если ты внутри контейнера бота
psql -U bot -h postgres -d content_agent
```

### Полезные SQL запросы

```sql
-- Информация о БД
SELECT version();

-- Список таблиц
\dt

-- Информация о пользователях
SELECT * FROM users LIMIT 10;

-- Статистика использования
SELECT 
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Количество пользователей
SELECT COUNT(*) as total_users FROM users;

-- Активные подписки
SELECT COUNT(*) FROM subscriptions WHERE is_active = true;

-- Проверить лимиты переписей
SELECT user_id, generated_today FROM user_rewrite_limits LIMIT 5;
```

### Резервные копии

```bash
# Создание бэкапа
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml exec postgres \
  pg_dump -U bot content_agent > /opt/backups/backup_$(date +%Y%m%d_%H%M%S).sql

# Проверить размер бэкапа
ls -lh /opt/backups/

# Восстановление из бэкапа
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml exec -T postgres \
  psql -U bot content_agent < /opt/backups/backup_20240507_120000.sql

# Автоматический бэкап каждый день в 2:00 AM
# Добавь в crontab (sudo crontab -e):
# 0 2 * * * docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml exec postgres pg_dump -U bot content_agent > /opt/backups/daily_$(date +\%Y\%m\%d).sql
```

## 📊 Мониторинг

### Использование ресурсов

```bash
# Docker статистика (обновляется в реальном времени)
docker stats

# Память и CPU (один снимок)
docker stats --no-stream

# Размер БД
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml exec postgres \
  du -sh /var/lib/postgresql/data

# Размер контейнеров
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml exec bot \
  du -sh /app

# Дисковое пространство на сервере
df -h
```

### Проверка портов

```bash
# Какие порты слушают
sudo netstat -tlnp | grep LISTEN

# Или более новый способ
sudo ss -tlnp | grep LISTEN

# Проверка конкретного порта
sudo netstat -tlnp | grep :8080
sudo netstat -tlnp | grep :5432
```

## 🔄 Обновление кода

### Обновление приложения (из свежего коммита)

```bash
cd /opt/content-agent-bot

# Получить последние изменения
git pull origin main

# Пересобрать образ Docker
docker compose -f deploy/docker-compose.prod.yml build --no-cache bot

# Перезапустить с новым образом
docker compose -f deploy/docker-compose.prod.yml up -d bot

# Проверить логи
docker compose -f deploy/docker-compose.prod.yml logs -f bot
```

### Откат на предыдущую версию

```bash
cd /opt/content-agent-bot

# Показать последние коммиты
git log --oneline -10

# Откатиться на конкретный коммит
git reset --hard abc1234def

# Пересобрать и перезапустить
docker compose -f deploy/docker-compose.prod.yml build
docker compose -f deploy/docker-compose.prod.yml up -d
```

## 🔐 Безопасность

### Проверка безопасности

```bash
# Убедись что .env защищен
ls -la /opt/content-agent-bot/.env  # должен быть 640 и владелец bot

# Проверить открытые порты (только нужные 22, 80, 443)
sudo ufw status

# Проверить firewall правила
sudo iptables -L -n

# Скан портов (с другого компьютера)
nmap YOUR_VPS_IP
```

### Обновление системы

```bash
# Проверить обновления
sudo apt update
sudo apt list --upgradable

# Обновить (безопасно, когда бот запущен)
sudo apt upgrade -y

# Обновить критические пакеты
sudo apt full-upgrade -y

# Перезагрузиться при необходимости
sudo reboot
```

## 🐛 Отладка

### Если приложение не работает

```bash
# 1. Проверь статус
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml ps

# 2. Прочитай логи полностью (без -f)
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml logs bot | tail -200

# 3. Проверь .env
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml config | grep -A10 "environment:"

# 4. Проверь здоровье контейнеров
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml ps --no-trunc

# 5. Вход в контейнер и диагностика
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml exec bot bash

# Внутри контейнера:
python -c "import app; print('OK')"  # проверка импортов
env | grep TELEGRAM  # проверка переменных
curl http://localhost:8080/health  # проверка API
```

### Если БД проблема

```bash
# Проверить здоровье БД
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml exec postgres pg_isready

# Проверить что БД слушает на правильном порту
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml exec postgres \
  ss -tlnp | grep 5432

# Проверить логи БД
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml logs postgres | tail -100

# Пересоздать volume (ПОТЕРЯ ДАННЫХ!)
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml down -v
docker volume prune -f
docker compose -f /opt/content-agent-bot/deploy/docker-compose.prod.yml up -d postgres
```

## 📞 Помощь

Если команда не работает:

1. Убедись что ты в правильной папке: `pwd`
2. Убедись что Docker запущен: `docker ps`
3. Проверь логи Docker daemon: `journalctl -u docker -f`
4. Гугли ошибку + Docker
5. Откройте issue на GitHub

---

**Совет:** Сохраните этот файл в закладки! 🔖
