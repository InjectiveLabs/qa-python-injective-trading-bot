# 🧪 Local Testing Guide - Docker Setup

## Overview

Test your Docker setup locally on your Mac **before** deploying to devnet-2. This ensures everything works correctly.

---

## ✅ Prerequisites

- [x] Docker Desktop installed and running
- [x] Docker images built (`./build-images.sh` completed successfully)
- [ ] Test wallet private keys (testnet wallets, not real money)

---

## 📝 Step 1: Create Local .env File

```bash
cd /Users/farook/dev/qa-python-injective-trading-bot

# Create .env from template
cp env.example .env

# Edit with your testnet wallet keys
nano .env
```

**Example `.env` for local testing:**
```bash
# Dashboard Authentication
WEB_AUTH_USERNAME=admin
WEB_AUTH_PASSWORD=test123
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=test123

# Testnet Wallet 1 (use your actual testnet private key)
WALLET_1_PRIVATE_KEY=0xYOUR_TESTNET_PRIVATE_KEY_HERE
WALLET_1_NAME=Local Test Wallet 1
WALLET_1_ENABLED=true
WALLET_1_MAX_ORDERS=5
WALLET_1_BALANCE_THRESHOLD=10

# Testnet Wallet 2 (optional, for testing multiple wallets)
WALLET_2_PRIVATE_KEY=0xYOUR_SECOND_TESTNET_KEY_HERE
WALLET_2_NAME=Local Test Wallet 2
WALLET_2_ENABLED=true
WALLET_2_MAX_ORDERS=5
WALLET_2_BALANCE_THRESHOLD=10
```

⚠️ **Important**: Use **testnet** private keys for local testing, not mainnet!

---

## 🚀 Step 2: Start Web Dashboard

```bash
cd /Users/farook/dev/qa-python-injective-trading-bot

# Start the web dashboard container
docker compose up -d web

# Check if it started successfully
docker compose ps
```

**Expected output:**
```
NAME                 IMAGE                                    STATUS
trading-bot-web      qa-python-injective-trading-bot-web      Up
```

---

## 🔍 Step 3: Verify Wallet Loading

```bash
# Check logs for wallet loading
docker compose logs web | grep -A 5 "Loaded wallet"
```

**Expected output:**
```
✅ Loaded wallet: Local Test Wallet 1 (enabled)
✅ Loaded wallet: Local Test Wallet 2 (enabled)
```

**If you see errors:**
```bash
# View full logs
docker compose logs web

# Common issues:
# - "No wallets found" → Check .env file has WALLET_*_PRIVATE_KEY
# - "Invalid private key" → Check key format (must start with 0x)
# - "Port already in use" → Stop other services on port 8000
```

---

## 🌐 Step 4: Access Dashboard

**Open your browser:**
```
http://localhost:8000
```

**Login credentials:**
- Username: `admin` (from WEB_AUTH_USERNAME in .env)
- Password: `test123` (from WEB_AUTH_PASSWORD in .env)

**You should see:**
- Dashboard with wallet selection
- Available markets dropdown
- "Start Bot" button
- Empty "Running Bots" section

---

## 🤖 Step 5: Test Starting a Bot

### **Via Web UI (Recommended):**

1. **Select a wallet** from the dropdown (e.g., "Local Test Wallet 1")
2. **Select a market** (e.g., "INJ/USDT" for spot)
3. **Click "Start Bot"**
4. **Verify bot appears** in "Running Bots" section

### **Via Terminal (Alternative):**

```bash
# Watch logs in real-time
docker compose logs -f web
```

In another terminal:
```bash
# List all containers (should see bot container)
docker ps | grep bot

# Expected output:
# spot-bot-wallet_1-INJ-USDT
# trading-bot-web
```

---

## 📊 Step 6: Verify Bot is Working

### **Check Bot Logs:**

```bash
# List running bot containers
docker ps --filter "label=app=trading-bot" --filter "label=component=bot"

# View specific bot logs (replace with your container name)
docker logs spot-bot-wallet_1-INJ-USDT --tail 50
```

**Healthy bot logs should show:**
```
🚀 Starting Spot Trader Bot
💼 Wallet: wallet_1 (Local Test Wallet 1)
📈 Market: INJ/USDT
🔗 Connecting to Injective testnet...
✅ Connected to network
💰 Current balance: 123.45 INJ
📊 Market price: 25.67 USDT
🎯 Placing initial orders...
```

**Error indicators:**
```
❌ Connection failed
❌ Insufficient balance
❌ Invalid market
❌ Authentication failed
```

### **Check Container Status:**

```bash
# View all bot containers
docker compose ps

# Or with docker ps
docker ps -a | grep bot
```

**Status indicators:**
- `Up` → Bot running ✅
- `Exited (0)` → Bot stopped normally
- `Exited (1)` → Bot crashed ❌
- `Restarting` → Bot keep crashing ❌

---

## 🛑 Step 7: Test Stopping a Bot

### **Via Web UI:**

1. Find the bot in "Running Bots" section
2. Click "Stop" button
3. Bot should disappear from list

### **Via Terminal:**

```bash
# Stop via docker
docker stop spot-bot-wallet_1-INJ-USDT

# Verify it stopped
docker ps | grep spot-bot-wallet_1-INJ-USDT  # Should show nothing
```

---

## 🧹 Step 8: Cleanup

### **Stop everything:**

```bash
# Stop all containers
docker compose down

# Verify stopped
docker compose ps  # Should show nothing
```

### **View and clean up stopped containers:**

```bash
# List all bot containers (including stopped)
docker ps -a --filter "label=app=trading-bot"

# Remove specific stopped bot
docker rm spot-bot-wallet_1-INJ-USDT

# Remove ALL stopped bot containers
docker container prune -f --filter "label=app=trading-bot"
```

### **Clean up if you want to rebuild:**

```bash
# Remove images
docker rmi qa-python-injective-trading-bot-web
docker rmi qa-python-injective-trading-bot-spot-trader
docker rmi qa-python-injective-trading-bot-derivative-trader

# Rebuild
./build-images.sh
```

---

## 🔧 Troubleshooting

### **Problem: Dashboard not accessible at localhost:8000**

**Check if container is running:**
```bash
docker compose ps
```

**Check if port is bound:**
```bash
# macOS
lsof -i :8000

# If something else is using port 8000, change it in docker-compose.yml:
# ports:
#   - "8001:8000"  # Use 8001 on host instead
```

**Check container logs:**
```bash
docker compose logs web
```

---

### **Problem: "Could not connect to Docker daemon"**

**Solution:**
```bash
# Ensure Docker Desktop is running
open -a Docker

# Wait for Docker to start (whale icon in menu bar)
# Then try again
docker ps
```

---

### **Problem: Bot container exits immediately**

**Check bot logs:**
```bash
# Find the container (even if stopped)
docker ps -a | grep bot

# View logs
docker logs <container_name>
```

**Common causes:**
- Invalid private key format
- Wallet has no balance
- Invalid market ID
- Network connectivity issues
- Missing environment variables

---

### **Problem: "No wallets found in environment variables"**

**Solution:**
```bash
# Check .env file exists
ls -la .env

# Check it has wallet keys
cat .env | grep WALLET_1_PRIVATE_KEY

# Restart web dashboard to reload .env
docker compose restart web
docker compose logs web | grep "Loaded wallet"
```

---

### **Problem: Web dashboard loads but can't create bot containers**

**Check Docker socket mount:**
```bash
# Verify socket exists
ls -la /var/run/docker.sock

# Check docker-compose.yml has:
# volumes:
#   - /var/run/docker.sock:/var/run/docker.sock
```

**Check web container can access Docker:**
```bash
docker exec trading-bot-web docker ps
# Should list containers, not show error
```

---

## ✅ Local Testing Checklist

Before deploying to devnet-2, verify:

- [ ] Dashboard accessible at http://localhost:8000
- [ ] Can log in with credentials from .env
- [ ] Wallets appear in dropdown
- [ ] Markets appear in dropdown
- [ ] Can start a bot via UI
- [ ] Bot container appears in `docker ps`
- [ ] Bot logs show successful connection
- [ ] Can view bot logs in UI
- [ ] Can stop bot via UI
- [ ] Bot container is removed after stopping
- [ ] Logs persist in `./logs/` directory
- [ ] Can start multiple bots simultaneously
- [ ] Bots restart automatically if they crash

---

## 🎯 Quick Test Script

Save this as `test-local-docker.sh` and run it:

```bash
#!/bin/bash
set -e

echo "🧪 Testing Docker Setup Locally..."

# 1. Check Docker is running
echo "1️⃣  Checking Docker..."
docker ps > /dev/null || { echo "❌ Docker not running"; exit 1; }
echo "   ✅ Docker is running"

# 2. Check .env file exists
echo "2️⃣  Checking .env file..."
[ -f .env ] || { echo "❌ .env file not found"; exit 1; }
grep -q "WALLET_1_PRIVATE_KEY" .env || { echo "❌ No wallet keys in .env"; exit 1; }
echo "   ✅ .env file configured"

# 3. Check images exist
echo "3️⃣  Checking Docker images..."
docker images | grep -q "qa-python-injective-trading-bot-web" || { echo "❌ Images not built. Run: ./build-images.sh"; exit 1; }
echo "   ✅ Docker images found"

# 4. Start dashboard
echo "4️⃣  Starting web dashboard..."
docker compose up -d web
sleep 5

# 5. Check dashboard is running
echo "5️⃣  Checking dashboard status..."
docker compose ps | grep -q "Up" || { echo "❌ Dashboard failed to start"; docker compose logs web; exit 1; }
echo "   ✅ Dashboard is running"

# 6. Check wallets loaded
echo "6️⃣  Checking wallet loading..."
docker compose logs web | grep -q "Loaded wallet" || { echo "❌ No wallets loaded"; docker compose logs web; exit 1; }
echo "   ✅ Wallets loaded successfully"

# 7. Check dashboard accessible
echo "7️⃣  Checking dashboard accessibility..."
curl -s http://localhost:8000 > /dev/null || { echo "❌ Dashboard not accessible"; exit 1; }
echo "   ✅ Dashboard accessible at http://localhost:8000"

echo ""
echo "🎉 All tests passed!"
echo ""
echo "📋 Next steps:"
echo "   1. Open http://localhost:8000 in your browser"
echo "   2. Login with credentials from .env"
echo "   3. Start a test bot"
echo "   4. Check logs: docker compose logs -f"
echo ""
echo "🧹 To cleanup: docker compose down"
```

Make it executable and run:
```bash
chmod +x test-local-docker.sh
./test-local-docker.sh
```

---

## 📚 Useful Commands Reference

```bash
# Start dashboard
docker compose up -d web

# View logs (follow mode)
docker compose logs -f web

# List all containers
docker ps -a

# List only bot containers
docker ps --filter "label=component=bot"

# View specific bot logs
docker logs <container-name> --tail 100 -f

# Stop dashboard
docker compose down

# Restart dashboard (reload .env)
docker compose restart web

# View dashboard resource usage
docker stats trading-bot-web

# Inspect network
docker network inspect trading-network

# Check volumes
docker volume ls

# Execute command in container
docker exec -it trading-bot-web bash
```

---

## 🚀 Ready for Production?

Once local testing passes:

1. ✅ Commit and push code changes
2. ✅ Deploy to devnet-2 (see DOCKER_DEPLOYMENT.md)
3. ✅ Create .env on server with production keys
4. ✅ Build images on server
5. ✅ Start dashboard
6. ✅ Access via server URL (see below)

See: **DEVNET2_ACCESS_GUIDE.md** (next guide) for accessing dashboard on server

