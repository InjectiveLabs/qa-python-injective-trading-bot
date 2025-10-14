# 🐳 Docker Deployment Guide

## 📋 Prerequisites

- ✅ Docker installed (version 20.10+)
- ✅ Docker Compose installed (version 2.0+)
- ✅ Server with 2GB+ RAM and 10GB+ disk space
- ✅ Access to Injective testnet/mainnet APIs

## 🚀 Quick Start (devnet-2)

### **Step 1: Navigate to Project Directory**

```bash
ssh root@injective-devnet-2
cd /root/injective/injective-testnet-liquidity-bot
```

### **Step 2: Build Docker Images**

```bash
# Build all images (takes 3-5 minutes first time)
docker compose build

# Verify images were created
docker images | grep -E 'web|spot-trader|derivative-trader'
```

### **Step 3: Configure Environment**

```bash
# Create .env file from example
cp env.example .env

# Edit with your wallet keys
nano .env

# Add your wallet private keys:
# WALLET_1_PRIVATE_KEY=0x...
# WALLET_2_PRIVATE_KEY=0x...
# WALLET_3_PRIVATE_KEY=0x...
```

### **Step 4: Start Web Dashboard**

```bash
# Start only the web dashboard
docker compose up -d web

# Check status
docker compose ps

# View logs
docker compose logs -f web
```

### **Step 5: Access Dashboard**

**Option A: Direct IP**
```
http://65.109.105.11:8000
```

**Option B: SSH Tunnel (secure)**
```bash
# On your local machine
ssh -L 8000:localhost:8000 root@injective-devnet-2

# Then open: http://localhost:8000
```

**Option C: Cloudflare Tunnel (team access)**
```bash
# On devnet-2
cloudflared tunnel --url http://localhost:8000
# Gives you: https://random-name.trycloudflare.com
```

---

## 📦 Docker Images

The system uses 3 Docker images:

### **1. Web Dashboard (`injective-testnet-liquidity-bot-web`)**
- FastAPI application
- Docker SDK for container management
- Port 8000 exposed

### **2. Spot Trader (`spot-trader:latest`)**
- Runs spot trading logic
- Created dynamically by web dashboard
- Shared volumes for logs/config

### **3. Derivative Trader (`derivative-trader:latest`)**
- Runs derivative trading logic
- Created dynamically by web dashboard
- Shared volumes for logs/config

---

## 🎮 Usage

### **Starting Bots via Web UI**

1. Open dashboard: `http://65.109.105.11:8000`
2. Login (default: admin/admin)
3. Select:
   - Bot Type: Spot or Derivative
   - Wallet: wallet_1, wallet_2, or wallet_3
   - Market: INJ/USDT, TIA/USDT, etc.
4. Click "Start Bot"

**What happens:**
- Web dashboard creates a new Docker container
- Container runs with specified wallet and market
- Bot starts trading automatically
- Container auto-restarts if it crashes

### **Stopping Bots**

1. Find running bot in dashboard
2. Click "Stop Bot"
3. Container stops and is removed
4. Wallet becomes available for reuse

---

## 📊 Monitoring

### **View All Containers**

```bash
# All trading bot containers
docker ps --filter label=app=trading-bot

# All containers (including web)
docker compose ps

# Container details
docker inspect <container-id>
```

### **View Logs**

```bash
# Web dashboard logs
docker compose logs -f web

# Specific bot container
docker logs -f <container-name>

# Example
docker logs -f spot-wallet_1-INJ-USDT

# All bot logs
docker logs -f $(docker ps -q --filter label=app=trading-bot)
```

### **Check Resource Usage**

```bash
# Real-time stats
docker stats

# Disk usage
docker system df
```

---

## 🔄 Updates & Maintenance

### **Update Code**

```bash
# Pull latest changes
git pull

# Rebuild images
docker compose build

# Restart web dashboard (keeps bots running)
docker compose up -d web

# Note: Existing bot containers continue running with old code
# Restart them via UI to use new code
```

### **Full Restart**

```bash
# Stop everything
docker compose down

# Stop all bot containers
docker stop $(docker ps -q --filter label=app=trading-bot)
docker rm $(docker ps -aq --filter label=app=trading-bot)

# Start fresh
docker compose up -d web
```

### **Clean Up**

```bash
# Remove stopped containers
docker container prune -f

# Remove unused images
docker image prune -a -f

# Remove unused volumes
docker volume prune -f

# Nuclear option (careful!)
docker system prune -a --volumes -f
```

---

## 🐛 Troubleshooting

### **Image Not Found Error**

```bash
# Build missing images
docker compose build

# Or build specific image
docker build -f docker/spot-trader/Dockerfile -t spot-trader:latest .
```

### **Port 8000 Already in Use**

```bash
# Find what's using port 8000
sudo lsof -i :8000

# Change port in docker-compose.yml:
# ports:
#   - "8080:8000"  # Use 8080 instead
```

### **Permission Denied (Docker Socket)**

```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Logout and login again
exit
ssh root@injective-devnet-2
```

### **Container Crashes Immediately**

```bash
# Check logs for errors
docker logs <container-name>

# Common issues:
# - Missing .env file
# - Invalid wallet private key
# - Network connectivity issues
```

### **Cannot Connect to Injective API**

```bash
# Test connectivity
curl -I https://testnet.sentry.tm.injective.network

# Check DNS
nslookup testnet.sentry.chain.grpc.injective.network

# Test from inside container
docker run --rm spot-trader:latest curl -I https://testnet.sentry.tm.injective.network
```

---

## 🔐 Security Notes

### **Docker Socket Access**

The web dashboard has access to `/var/run/docker.sock` to manage containers.

**Security implications:**
- Can create/stop/manage any container
- Equivalent to root access
- Protected by HTTP Basic Auth

**Mitigations:**
- Dashboard protected by username/password
- Only accessible from trusted network
- Consider using Docker socket proxy for production

### **Secrets Management**

Wallet private keys are stored in `.env` file and injected as environment variables.

**Best practices:**
- Never commit `.env` to git (already in .gitignore)
- Use strong passwords for dashboard auth
- Rotate wallet keys periodically
- Consider using Docker secrets for production

---

## 📝 Environment Variables

### **Required:**
- `WALLET_1_PRIVATE_KEY` - Wallet 1 private key
- `WALLET_2_PRIVATE_KEY` - Wallet 2 private key  
- `WALLET_3_PRIVATE_KEY` - Wallet 3 private key

### **Optional:**
- `WEB_AUTH_USERNAME` - Dashboard username (default: admin)
- `WEB_AUTH_PASSWORD` - Dashboard password (default: admin)
- `WALLET_1_ENABLED` - Enable wallet 1 (default: true)
- `WALLET_2_ENABLED` - Enable wallet 2 (default: true)
- `WALLET_3_ENABLED` - Enable wallet 3 (default: true)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│       Docker Host (devnet-2)            │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  Web Dashboard Container         │  │
│  │  - Port 8000                     │  │
│  │  - Docker SDK                    │  │
│  │  - Controls other containers     │  │
│  └──────────────┬───────────────────┘  │
│                 │                       │
│                 │ Docker API            │
│                 ▼                       │
│  ┌──────────────────────────────────┐  │
│  │  Bot Containers (dynamic)        │  │
│  │  ┌────────┐ ┌────────┐ ┌──────┐ │  │
│  │  │ Spot   │ │ Spot   │ │ Deriv│ │  │
│  │  │ W1 INJ │ │ W2 TIA │ │ W3   │ │  │
│  │  └────────┘ └────────┘ └──────┘ │  │
│  └──────────────────────────────────┘  │
│                 │                       │
│                 │ Shared Volumes        │
│                 ▼                       │
│  ┌──────────────────────────────────┐  │
│  │  Persistent Storage              │  │
│  │  - logs/                         │  │
│  │  - config/                       │  │
│  │  - data/                         │  │
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

---

## 💡 Tips

1. **First deployment:** Build images locally first to catch errors
2. **Testing:** Use `docker compose up web` (no -d) to see logs in real-time
3. **Performance:** Pre-build images to avoid delays when starting bots
4. **Monitoring:** Set up log rotation for /var/lib/docker/containers
5. **Scaling:** Each bot needs ~128MB RAM, plan accordingly

---

## 📞 Support

**Issues:**
- Check logs: `docker compose logs`
- Check container status: `docker ps -a`
- Verify images: `docker images`
- Test connectivity: From inside container

**Common Commands:**
```bash
# Restart web dashboard
docker compose restart web

# View all bot containers
docker ps --filter label=app=trading-bot

# Stop all bots
docker stop $(docker ps -q --filter label=app=trading-bot)

# Clean everything and start fresh
docker compose down && docker compose up -d web
```

---

**🎉 You're all set! Access dashboard and start trading bots!**

