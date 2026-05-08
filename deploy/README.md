# Deployment Guide — VPS jino.ru

## Quick Start

```bash
# 1. SSH to VPS
ssh -p 49386 root@130e66479b71.vps.myjino.ru

# 2. Clone and setup
git clone https://github.com/badeev777-svg/content-agent-bot.git
cd content-agent-bot
cp deploy/.env.production.template .env.production
# Edit .env.production with actual values (tokens, passwords, etc.)

# 3. Install Python + dependencies
apt update && apt install -y python3.11 python3.11-venv python3-pip
python3 -m venv venv
source venv/bin/activate
pip install -e .

# 4. Setup database
alembic upgrade head

# 5. Install systemd service
sudo cp deploy/content-agent-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable content-agent-bot
sudo systemctl start content-agent-bot

# 6. Check status
sudo systemctl status content-agent-bot
sudo journalctl -u content-agent-bot -f
```

## Environment Variables

Edit `.env.production` and fill in:
- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `OPENROUTER_API_KEY` — from https://openrouter.ai/keys
- `ADMIN_TELEGRAM_CHAT_ID` — your chat ID for alerts
- `TELEGRAM_PAYMENT_TOKEN` — from @BotFather payments
- Database password (strong!)

## Monitoring

```bash
# Check if service is running
sudo systemctl status content-agent-bot

# View logs
sudo journalctl -u content-agent-bot -n 50 -f

# Database health
sudo -u postgres psql -d content_agent -c "SELECT NOW();"

# Health check endpoint
curl http://localhost:8080/health
```

## Troubleshooting

**Bot not responding:**
```bash
sudo systemctl restart content-agent-bot
sudo journalctl -u content-agent-bot -n 100
```

**Database connection failed:**
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check credentials in .env.production
grep DATABASE_URL .env.production
```

**Out of disk space:**
```bash
df -h
# Clean Docker images if using docker-compose:
docker system prune -a
```
