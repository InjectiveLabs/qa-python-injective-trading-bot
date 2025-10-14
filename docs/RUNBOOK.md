# Injective Trading Bot - RUNBOOK

## Overview
- Web dashboard (FastAPI) manages bots as Docker containers
- Bots: `spot` and `derivative` (now in `scripts/bots/`)
- Persistent host mounts: `logs/`, `config/`, `data/`

## Prerequisites
- Docker Desktop (Mac) or Docker Engine (Linux)
- `.env` in project root with wallet keys and dashboard auth

## Quickstart (Local)
```bash
# Build images
./build-images.sh

# Start dashboard
docker compose up -d web
open http://localhost:8000
```
Login: `WEB_AUTH_USERNAME` / `WEB_AUTH_PASSWORD` from `.env`.

## .env essentials
- Dashboard auth: `WEB_AUTH_USERNAME`, `WEB_AUTH_PASSWORD`
- Wallets:
  - `WALLET_1_PRIVATE_KEY=0x...`
  - `WALLET_1_NAME=...`
  - Duplicate for `WALLET_2_...`, `WALLET_3_...`
- Optional network overrides not required for default testnet.

## Start/Stop via Dashboard
- Start: select wallet + market → Start Bot
- Reuse behavior: If a container with the same name exists, dashboard reuses it (starts if stopped)
- Stop: Stop Bot → container stopped and removed
- Rediscovery: On dashboard restart, running bots are rediscovered and shown

## Direct CLI (no dashboard)
Start bot directly:
```bash
# Spot
./scripts/run-bot-docker.sh spot wallet_1 INJ/USDT

# Derivative
./scripts/run-bot-docker.sh derivative wallet_2 INJ/USDT-PERP
```
Manage bots:
```bash
./scripts/manage-bots.sh list
./scripts/manage-bots.sh logs spot-wallet_1-INJ-USDT
./scripts/manage-bots.sh stop spot-wallet_1-INJ-USDT
./scripts/manage-bots.sh cleanup
```

## Development Workflow
- Fast dev: use venv to iterate logic
```bash
python scripts/bots/spot_trader.py wallet_1 INJ/USDT
python scripts/bots/derivative_trader.py wallet_2 --markets INJ/USDT-PERP
```
- Validate in Docker before deploy:
```bash
./build-images.sh
open http://localhost:8000
```

## Deploy to devnet-2
```bash
# Push code
git push

# On server
ssh root@injective-devnet-2
cd /root/injective/injective-testnet-liquidity-bot
git pull
cp env.example .env   # or create if missing
nano .env             # set real keys
./build-images.sh
Docker compose up -d web
```
Access options: SSH tunnel or public IP via DevOps firewall rule.

## Logs
- System logs: `logs/trader.log`, `logs/spot_trader.log`, `logs/derivative_trader.log`
- Dashboard: System Logs panel and View Logs per bot
- CLI: `docker logs <container>` or `./scripts/manage-bots.sh logs <name>`

## Troubleshooting
- 409 Conflict when starting bot:
  - Already running or container exists. Dashboard reuses automatically; otherwise remove:
  ```bash
  docker rm -f spot-wallet_1-INJ-USDT
  ```
- No wallets loaded:
  - `.env` missing `WALLET_*_PRIVATE_KEY`
- Dashboard can’t create containers on Mac:
  - Ensure Docker Desktop is running
- Prices showing 0.0:
  - Check network connectivity; try Refresh Status
- Volume path errors on Mac:
  - We pass host paths via env; ensure `logs/`, `config/`, `data/` exist

## Structure
```
.
├─ docker/                    # Dockerfiles
├─ web/                       # Dashboard backend + static UI
├─ scripts/
│  ├─ bots/                   # spot_trader.py, derivative_trader.py
│  ├─ run-bot-docker.sh       # start bot directly
│  └─ manage-bots.sh          # list/stop/logs helpers
├─ config/                    # configs (mounted read-only)
├─ data/                      # market data (mounted read-only)
├─ logs/                      # logs (persisted)
├─ docker-compose.yml         # web service
├─ build-images.sh            # builds all images
└─ .env                       # secrets (not in git)
```

## Upgrading bots
```bash
# After code changes
./build-images.sh
# Restart specific bot from dashboard or CLI
```

## Safety
- Never commit `.env`
- Use testnet keys locally; rotate production keys periodically
