# 🔐 Environment File (.env) Setup Guide

## Overview

The `.env` file contains sensitive credentials (wallet private keys, dashboard passwords) that are **NEVER committed to git**. This guide explains how it works with Docker.

---

## 🔄 How .env Works in Docker

### **1. File Location**

```
/root/injective/injective-testnet-liquidity-bot/
├── .env              ← ACTUAL CREDENTIALS (never in git)
├── env.example       ← TEMPLATE with fake values (in git)
├── docker-compose.yml
└── ...
```

### **2. Docker Compose Reads .env Automatically**

```yaml
# docker-compose.yml
services:
  web:
    env_file:
      - .env  ← Docker Compose loads this file
    environment:
      - DASHBOARD_USERNAME=${DASHBOARD_USERNAME:-admin}
      - DASHBOARD_PASSWORD=${DASHBOARD_PASSWORD:-changeme}
```

### **3. Data Flow**

```
.env file on server
    ↓
Docker Compose loads variables
    ↓
Web Dashboard Container (has ALL wallet keys)
    ↓
Creates Bot Container (passes SPECIFIC wallet key)
    ↓
Bot runs with single wallet
```

---

## 📝 Setup Instructions

### **On Your Local Machine (Mac)**

1. **Create .env file locally for testing:**
   ```bash
   cd /Users/farook/dev/qa-python-injective-trading-bot
   cp env.example .env
   nano .env  # Edit with your real values
   ```

2. **VERIFY .env is ignored by git:**
   ```bash
   git status  # .env should NOT appear
   ```

3. **Test locally (if Docker installed):**
   ```bash
   docker compose up -d web
   docker compose logs web  # Check for wallet loading
   ```

---

### **On devnet-2 Server**

1. **SSH to server:**
   ```bash
   ssh root@injective-devnet-2
   cd /root/injective/injective-testnet-liquidity-bot
   ```

2. **Create .env file:**
   ```bash
   # Copy template
   cp env.example .env
   
   # Edit with real credentials
   nano .env
   ```

3. **Fill in your actual values:**
   ```bash
   # Dashboard auth
   WEB_AUTH_USERNAME=admin
   WEB_AUTH_PASSWORD=your_secure_password_here
   DASHBOARD_USERNAME=admin
   DASHBOARD_PASSWORD=your_secure_password_here
   
   # Wallet 1
   WALLET_1_PRIVATE_KEY=0xYOUR_ACTUAL_PRIVATE_KEY_HERE
   WALLET_1_NAME=Primary Market Maker
   WALLET_1_ENABLED=true
   WALLET_1_MAX_ORDERS=5
   WALLET_1_BALANCE_THRESHOLD=100
   
   # Wallet 2 (if you have it)
   WALLET_2_PRIVATE_KEY=0xYOUR_SECOND_PRIVATE_KEY_HERE
   WALLET_2_NAME=Secondary Market Maker
   WALLET_2_ENABLED=true
   # ... etc
   ```

4. **Verify file permissions (security):**
   ```bash
   chmod 600 .env  # Only root can read/write
   ls -la .env     # Should show: -rw------- 1 root root
   ```

5. **Test it works:**
   ```bash
   # Build images
   ./build-images.sh
   
   # Start web dashboard
   docker compose up -d web
   
   # Check logs for wallet loading
   docker compose logs web | grep "Loaded wallet"
   ```

   You should see:
   ```
   ✅ Loaded wallet: Primary Market Maker (enabled)
   ✅ Loaded wallet: Secondary Market Maker (enabled)
   ```

---

## 🔍 How Bots Access Wallet Keys

### **Web Dashboard (web/app.py)**

```python
from utils.secure_wallet_loader import load_wallets_from_env

# Load ALL wallets from .env
wallets_config = load_wallets_from_env()
# Returns: {'wallets': [wallet1, wallet2, wallet3, ...]}
```

### **Bot Container Creation**

When you start a bot via UI, the web dashboard does:

```python
# web/app.py (Docker SDK)
container = docker_client.containers.run(
    image="qa-python-injective-trading-bot-spot-trader:latest",
    name=f"spot-bot-{wallet_id}-{market}",
    environment={
        "WALLET_ID": wallet_id,
        "MARKET": market,
        # Pass ONLY this wallet's private key
        f"WALLET_{wallet_id}_PRIVATE_KEY": wallet_config['private_key'],
        f"WALLET_{wallet_id}_NAME": wallet_config['name'],
    },
    # ... other config
)
```

**Security**: Each bot container only receives **ONE** wallet's private key, not all of them.

---

## 🚨 Security Best Practices

### ✅ DO:
- Keep .env file **ONLY on the server**, never in git
- Use strong passwords for dashboard auth
- Set file permissions: `chmod 600 .env`
- Use different passwords for dev/staging/prod
- Rotate private keys periodically

### ❌ DON'T:
- Never commit .env to git
- Never share .env via Slack/email
- Never use same password as your personal accounts
- Never screenshot .env contents
- Never push .env to any repository

---

## 🔧 Troubleshooting

### **Problem: "No wallets found in environment variables!"**

**Cause**: .env file not loaded or missing WALLET_*_PRIVATE_KEY variables

**Fix**:
```bash
# Check if .env exists
ls -la .env

# Check if it has wallet keys
grep "WALLET_1_PRIVATE_KEY" .env

# Verify Docker Compose is reading it
docker compose config | grep WALLET
```

---

### **Problem: Bot starts but can't sign transactions**

**Cause**: Private key format incorrect or not passed to container

**Fix**:
```bash
# Check key format in .env (should start with 0x)
grep "WALLET_1_PRIVATE_KEY" .env

# Check container environment
docker exec trading-bot-web env | grep WALLET
```

---

### **Problem: "Dashboard login not working"**

**Cause**: WEB_AUTH_USERNAME/PASSWORD not set or mismatch

**Fix**:
```bash
# Check dashboard credentials
grep "WEB_AUTH" .env
grep "DASHBOARD" .env

# Restart web container to reload .env
docker compose restart web
```

---

## 📚 Reference: Environment Variables

### **Required Variables**

| Variable | Example | Description |
|----------|---------|-------------|
| `WEB_AUTH_USERNAME` | `admin` | Dashboard username |
| `WEB_AUTH_PASSWORD` | `secure123` | Dashboard password |
| `WALLET_1_PRIVATE_KEY` | `0x1234...` | Wallet 1 private key |
| `WALLET_1_NAME` | `Primary MM` | Wallet 1 display name |

### **Optional Variables**

| Variable | Default | Description |
|----------|---------|-------------|
| `WALLET_*_ENABLED` | `true` | Enable/disable wallet |
| `WALLET_*_MAX_ORDERS` | `5` | Max orders per market |
| `WALLET_*_BALANCE_THRESHOLD` | `100` | Min balance (INJ) |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `LOG_RETENTION_DAYS` | `5` | How long to keep logs |

---

## 🎯 Quick Checklist

Before deploying to devnet-2:

- [ ] `.env` file created on server
- [ ] All `WALLET_*_PRIVATE_KEY` filled with real keys
- [ ] Dashboard username/password set
- [ ] File permissions set to 600
- [ ] Verified .env is NOT in git (`git status`)
- [ ] Tested docker compose reads .env correctly
- [ ] Web dashboard starts and loads wallets

---

## 📞 Need Help?

If you're stuck, check:
1. Docker Compose logs: `docker compose logs web`
2. Environment variables: `docker compose config`
3. File permissions: `ls -la .env`
4. Git status: `git status` (should NOT show .env)

