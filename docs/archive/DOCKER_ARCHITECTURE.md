# Docker Architecture Proposal - Trading Bot System

## 🎯 System Overview

The trading bot system consists of a web dashboard that dynamically manages multiple trading bot instances. Each bot trades on behalf of a specific wallet and market combination.

## 📊 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Docker Host Server                          │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                     Web Dashboard Container                 │    │
│  │                                                             │    │
│  │  - FastAPI Web Application                                 │    │
│  │  - User Interface (Start/Stop Bots)                        │    │
│  │  - Real-time Monitoring                                    │    │
│  │  - Docker SDK Integration                                  │    │
│  │                                                             │    │
│  │  Port 8000 exposed → [Reverse Proxy/Internet]             │    │
│  │                                                             │    │
│  │  Mounts:                                                   │    │
│  │    - /var/run/docker.sock (Docker control) ⚠️             │    │
│  │    - /logs (read logs)                                     │    │
│  │    - /config (read config)                                 │    │
│  └────────────────────────────────────────────────────────────┘    │
│                           │                                         │
│                           │ Docker API                              │
│                           │ (create/start/stop containers)          │
│                           ▼                                         │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              Bot Containers (Created Dynamically)            │  │
│  │                                                              │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │  │
│  │  │ Spot Trader  │  │ Spot Trader  │  │ Deriv Trader │      │  │
│  │  │              │  │              │  │              │      │  │
│  │  │ Wallet 1     │  │ Wallet 2     │  │ Wallet 3     │      │  │
│  │  │ INJ/USDT     │  │ TIA/USDT     │  │ INJ-PERP     │      │  │
│  │  │              │  │              │  │              │      │  │
│  │  │ Status:      │  │ Status:      │  │ Status:      │      │  │
│  │  │ Running      │  │ Running      │  │ Stopped      │      │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘      │  │
│  │                                                              │  │
│  │  Each bot:                                                   │  │
│  │    - Isolated process                                       │  │
│  │    - Auto-restart on crash                                  │  │
│  │    - Shares log & config volumes                            │  │
│  │    - Has wallet private key as env var                      │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                           │                                        │
│                           │ API Calls                              │
│                           ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                   Shared Volumes                             │  │
│  │                                                              │  │
│  │  📁 /logs/                                                   │  │
│  │     ├── spot_trader.log                                     │  │
│  │     ├── derivative_trader.log                               │  │
│  │     └── enhanced_trading.log                                │  │
│  │                                                              │  │
│  │  📁 /config/                                                 │  │
│  │     ├── trader_config.json                                  │  │
│  │     └── markets_config.json                                 │  │
│  │                                                              │  │
│  │  📁 /data/ (if needed)                                       │  │
│  │     └── market_data/                                        │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
                             │
                             │ HTTPS (outbound)
                             ▼
          ┌─────────────────────────────────────┐
          │    External APIs (Internet)         │
          │                                     │
          │  • Injective Testnet API            │
          │  • Injective Mainnet API            │
          │    (for price reference)            │
          └─────────────────────────────────────┘
```

## 🔄 User Workflow

```
User opens web dashboard
         │
         ▼
┌─────────────────────────────────────────────┐
│  Select:                                    │
│  - Wallet: [Wallet 2 ▼]                     │
│  - Market: [TIA/USDT ▼]                     │
│  - Type:   [Spot ▼]                         │
│                                             │
│  [Start Bot]                                │
└─────────────────────────────────────────────┘
         │
         ▼
Web dashboard calls Docker API:
docker run -d \
  --name spot-wallet2-tia \
  -e WALLET_ID=wallet_2 \
  -e MARKET=TIA/USDT \
  -e WALLET_PRIVATE_KEY=*** \
  -v /logs:/app/logs \
  spot-trader:latest
         │
         ▼
┌─────────────────────────────────────────────┐
│  Bot Container Running                      │
│  - Connects to Injective Testnet           │
│  - Fetches prices from Mainnet             │
│  - Places trades                            │
│  - Writes logs to shared volume             │
└─────────────────────────────────────────────┘
         │
         ▼
Dashboard shows:
┌─────────────────────────────────────────────┐
│  Running Bots:                              │
│  ┌───────────────────────────────────────┐ │
│  │ Wallet 2 - TIA/USDT (Spot)            │ │
│  │ Container: abc123de                   │ │
│  │ Uptime: 01:23:45                      │ │
│  │ Balance: TIA: 1,234.56 | USDT: 890.12│ │
│  │ Price: Testnet $15.23 | Main $15.20  │ │
│  │ [Stop] [View Logs]                    │ │
│  └───────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

## 📦 Container Details

### Web Dashboard Container
- **Base Image**: `python:3.11-slim`
- **Port**: 8000
- **Special Access**: Docker socket (`/var/run/docker.sock`)
- **Purpose**: UI and bot orchestration
- **Always Running**: Yes

### Bot Containers (Dynamically Created)
- **Base Images**: 
  - `spot-trader:latest`
  - `derivative-trader:latest`
- **Networking**: Docker bridge network
- **Restart Policy**: `unless-stopped` (auto-restart on crash)
- **Created**: On-demand via web dashboard
- **Destroyed**: When user stops bot

## 🔐 Secrets Management

```
.env file (on host):
├── WALLET_1_PRIVATE_KEY=0x...
├── WALLET_2_PRIVATE_KEY=0x...
├── WALLET_3_PRIVATE_KEY=0x...
├── DASHBOARD_USERNAME=admin
└── DASHBOARD_PASSWORD=***

Injected into containers as environment variables
```

## 🔒 Security Considerations

### ⚠️ Docker Socket Access
- Web dashboard needs `/var/run/docker.sock` to manage bot containers
- **Risk**: Full Docker control from web container
- **Mitigation Options**:
  1. HTTP auth on dashboard (current)
  2. Docker socket proxy (restricts API access)
  3. Read-only dashboard + manual bot management

### 🔐 Secrets
- Wallet private keys stored in `.env` (git-ignored)
- Alternative: Docker secrets or external secrets manager

### 🌐 Network
- Only web dashboard exposed to network (port 8000)
- Bot containers not directly accessible
- All containers need outbound internet for Injective APIs

## 📊 Resource Requirements (Estimated)

### Per Container:
- **Web Dashboard**: ~256MB RAM, 0.5 CPU
- **Bot (Spot)**: ~128MB RAM, 0.25 CPU
- **Bot (Derivative)**: ~128MB RAM, 0.25 CPU

### Total (3 wallets, 3 bots running):
- **Memory**: ~1GB
- **CPU**: ~1.5 cores
- **Disk**: 
  - Logs: ~500MB (with 5-day rotation)
  - Images: ~1GB
  - Config: <10MB

### Scaling:
- +128MB RAM per additional bot
- +0.25 CPU per additional bot

## 🚀 Deployment Flow

```
1. DevOps: Prepare server with Docker & Docker Compose

2. DevOps: Clone repository & configure secrets
   git clone <repo>
   cd qa-python-injective-trading-bot
   cp env.example .env
   # Edit .env with actual keys

3. DevOps: Build images
   docker-compose build

4. DevOps: Start web dashboard
   docker-compose up -d web

5. Users: Access dashboard at https://trading-bot.company.com

6. Users: Start/stop bots via web interface

7. Updates:
   git pull
   docker-compose build
   docker-compose up -d web  # Restarts web, bots continue
```

## 🔄 Lifecycle Management

### Normal Operation:
- Web dashboard always running
- Bots started/stopped on demand by users
- Auto-restart if bot crashes (not on user stop)

### Updates:
- Pull new code
- Rebuild images
- Restart web container
- Existing bots continue running (not interrupted)

### Monitoring:
- Dashboard shows bot status in real-time
- Log files accessible via UI or server filesystem
- Container health via `docker ps` or monitoring tools

## ❓ Questions for DevOps

See accompanying questions document for infrastructure requirements and preferences.

---

**Document Version**: 1.0  
**Date**: October 7, 2025  
**Status**: Proposal - Awaiting DevOps Review
