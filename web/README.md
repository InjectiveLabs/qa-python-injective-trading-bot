# Trading Bot Manager - Web Dashboard

> **Modern web interface for real-time bot monitoring and control**

A clean web dashboard built with FastAPI and vanilla JavaScript, providing real-time monitoring, control, and management for Injective trading bots.

## 🎯 Overview

The web dashboard provides a simple interface for:
- **Real-time bot monitoring** with live status updates
- **Bot lifecycle management** - start/stop trading bots
- **Wallet balance tracking** across configured wallets
- **Market overview** showing enabled markets
- **Process management** for running bot instances

## 🏗️ Architecture

### 🎨 Frontend Stack
- **HTML5** - Clean semantic markup
- **Vanilla JavaScript** - No framework dependencies
- **Modern CSS** - Simple, functional styling
- **Real-time Updates** - Polling-based status updates

### 🚀 Backend Stack
- **FastAPI** - Modern Python web framework
- **Subprocess Management** - Bot process spawning and control
- **File System Integration** - Log monitoring and configuration
- **RESTful API** - Simple JSON endpoints

### 🔄 System Integration

```
┌────────────────────────────────────────────────────────────┐
│                      WEB DASHBOARD                         │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Browser (Frontend)                                       │
│  ├─ HTML/JavaScript                                       │
│  ├─ HTTP requests to API                                  │
│  └─ Poll for status updates                               │
│                                                            │
│  FastAPI Server (Backend)                                 │
│  ├─ API Endpoints                                         │
│  │   ├─ GET /api/wallets      - List wallets             │
│  │   ├─ GET /api/markets      - List markets             │
│  │   ├─ POST /api/start_bot   - Start bot process        │
│  │   ├─ POST /api/stop_bot    - Stop bot process         │
│  │   └─ GET /api/status       - Bot status               │
│  │                                                        │
│  ├─ Process Management                                   │
│  │   ├─ Spawn: subprocess.Popen()                        │
│  │   ├─ Track: PID management                            │
│  │   └─ Stop: SIGTERM signal                             │
│  │                                                        │
│  └─ Integration                                           │
│      ├─ Read: .env for wallets                           │
│      ├─ Read: trader_config.json for markets             │
│      └─ Read: log files for output                       │
│                                                            │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│                    TRADING BOT LAYER                       │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Bot Processes (Independent)                              │
│  ├─ derivative_trader.py wallet_1                         │
│  ├─ spot_trader.py wallet2                                │
│  └─ trader.py wallet_3 (legacy)                           │
│                                                            │
│  Each bot runs as separate process:                       │
│  • Spawned by web dashboard or manually                   │
│  • Writes to own log file                                 │
│  • Independent lifecycle                                  │
│  • Can be stopped by web dashboard or Ctrl+C             │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 📋 Prerequisites
- Python 3.8 or higher
- Virtual environment activated
- Dependencies installed from main project

### 🛠️ Installation

1. **Ensure main project is set up**:
```bash
# From project root
cd /path/to/qa-python-injective-trading-bot
source venv/bin/activate
pip install -r requirements.txt
```

2. **Start the web server**:
```bash
cd web
python app.py
```

3. **Access the dashboard**:
- Open browser: `http://localhost:8000`
- Dashboard will load automatically

## 🎮 Dashboard Features

### 📊 Bot Status Panel
- **Live Status**: Shows which bots are currently running
- **Process Info**: PID, wallet ID, market, bot type
- **Control Actions**: Stop button for running bots

### 💰 Wallet Management
- **Available Wallets**: Lists all enabled wallets from `.env`
- **Wallet Selection**: Choose wallet for new bot instance
- **Configuration Display**: Shows wallet name and settings

### 📈 Market Information
- **Spot Markets**: INJ/USDT, stINJ/INJ, TIA/USDT, HDRO/INJ
- **Derivative Markets**: INJ/USDT-PERP
- **Market Selection**: Choose market for new bot instance
- **Type Filtering**: Separate spot and derivative lists

### 🎛️ Bot Controls

#### Start New Bot
1. Select bot type (Spot or Derivative)
2. Select wallet from dropdown
3. Select market from dropdown
4. Click "Start Bot"
5. Bot spawns as new process

#### Stop Running Bot
1. View running bots in status panel
2. Click "Stop" button for specific bot
3. Bot receives SIGTERM signal
4. Process terminates gracefully

### 📝 Status Messages
- **Success messages**: Green background
- **Error messages**: Red background
- **Auto-dismiss**: Messages fade after 5 seconds

## 🔧 Technical Details

### 📊 API Endpoints

| Endpoint | Method | Description | Request Body |
|----------|--------|-------------|--------------|
| `/` | GET | Serve dashboard page | None |
| `/static/{path}` | GET | Serve static files | None |
| `/api/wallets` | GET | List available wallets | None |
| `/api/markets` | GET | List available markets | None |
| `/api/status` | GET | Get running bots status | None |
| `/api/start_bot` | POST | Start new bot process | `{bot_type, wallet_id, market}` |
| `/api/stop_bot` | POST | Stop running bot | `{wallet_id, pid}` |

### 🔄 Process Management

#### Starting Bots
```python
# Web dashboard spawns bot as subprocess
process = subprocess.Popen(
    ["python", "derivative_trader.py", "wallet_1", "--markets", "INJ/USDT-PERP"],
    cwd=project_root,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

# Track process
running_bots[wallet_id] = {
    "pid": process.pid,
    "bot_type": "derivative",
    "market": "INJ/USDT-PERP",
    "start_time": time.time()
}
```

#### Stopping Bots
```python
# Send SIGTERM for graceful shutdown
os.kill(pid, signal.SIGTERM)

# Bot receives signal, cleans up, exits
# Trading summary printed to console
```

### 📁 File System Integration

#### Configuration Loading
```python
# Load wallets from .env
wallets = load_wallets_from_env()

# Load markets from trader_config.json
with open("config/trader_config.json") as f:
    config = json.load(f)
    markets = config["markets"]
```

#### Log Monitoring (Future)
```python
# Read recent logs
with open("logs/derivative_trader.log") as f:
    recent_logs = f.readlines()[-50:]  # Last 50 lines
```

## 🖥️ User Interface

### Dashboard Layout

```
┌────────────────────────────────────────────────────────┐
│                  Trading Bot Manager                   │
├────────────────────────────────────────────────────────┤
│                                                        │
│  📊 Running Bots                                       │
│  ┌──────────────────────────────────────────────┐    │
│  │ Bot ID  │ Wallet   │ Market   │ Type │ Stop  │    │
│  ├──────────────────────────────────────────────┤    │
│  │ 12345   │ wallet_1 │ INJ/USDT │ Spot │ [X]   │    │
│  └──────────────────────────────────────────────┘    │
│                                                        │
│  🚀 Start New Bot                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │ Bot Type:  ( ) Spot  (•) Derivative          │    │
│  │ Wallet:    [Select Wallet ▼]                 │    │
│  │ Market:    [Select Market ▼]                 │    │
│  │                                               │    │
│  │            [Start Bot Button]                │    │
│  └──────────────────────────────────────────────┘    │
│                                                        │
│  💰 Available Wallets                                  │
│  • wallet_1 (Primary Market Maker)                   │
│  • wallet_2 (QA Market Maker)                        │
│  • wallet_3 (QA Market Taker)                        │
│                                                        │
└────────────────────────────────────────────────────────┘
```

## 🔒 Security Considerations

### 🛡️ Current Security
- **Localhost Only**: Binds to `localhost` by default
- **No Authentication**: Suitable for local development only
- **Process Isolation**: Each bot runs in separate process
- **Limited Exposure**: Only configuration data exposed, no private keys

### ⚠️ Security Limitations
- **No Authentication**: Anyone with access to localhost can control bots
- **No Authorization**: No user roles or permissions
- **No HTTPS**: Plain HTTP traffic (localhost only)
- **No Rate Limiting**: No protection against rapid requests

### 🔐 Production Deployment Considerations

**DO NOT deploy this dashboard to public internet without**:
1. Adding authentication (e.g., HTTP Basic Auth, OAuth)
2. Enabling HTTPS with valid certificates
3. Implementing rate limiting
4. Adding authorization/role-based access
5. Securing the server environment
6. Implementing audit logging

**Recommended for**:
- ✅ Local development
- ✅ Private networks
- ✅ Trusted environments
- ✅ Personal use

**Not recommended for**:
- ❌ Public internet
- ❌ Multi-user environments
- ❌ Production deployments
- ❌ Sensitive operations

## 🚀 Deployment

### 🏠 Local Development (Recommended)
```bash
# Simple local server
cd web
python app.py

# Access at http://localhost:8000
```

### 🌐 Private Network (Use with Caution)
```bash
# Bind to specific interface
python app.py --host 192.168.1.100 --port 8000

# Access from local network
# http://192.168.1.100:8000
```

### 🔒 Production (Not Recommended)
This dashboard is designed for local/private use. For production deployment, consider:
- Adding authentication layer (e.g., nginx reverse proxy with basic auth)
- Implementing proper user management
- Adding HTTPS support
- Setting up firewall rules
- Using process supervisor (systemd, supervisor)

## 🐛 Troubleshooting

### Common Issues

#### Dashboard Won't Start
```bash
# Check if port 8000 is in use
lsof -i :8000

# Try different port
python app.py --port 8001
```

#### Can't See Wallets
- Verify `.env` file exists in project root
- Check `WALLET_X_ENABLED=true` for each wallet
- Verify wallet IDs match between `.env` and `trader_config.json`

#### Bot Won't Start from Dashboard
- Check bot script exists (`derivative_trader.py`, `spot_trader.py`)
- Verify virtual environment activated
- Check log files for error messages
- Ensure wallet has sufficient balance

#### Bot Shows as Running but Not Trading
- Check bot log files in `logs/` directory
- Verify network connectivity
- Use `python utils/health_checker.py` to check network status
- Ensure markets are properly configured

### Debug Mode
```bash
# Enable debug logging
python app.py --debug

# Check application logs
tail -f logs/web_app.log  # If logging configured
```

## 📊 Monitoring Bots

### Via Dashboard
- **Status Panel**: Shows all running bots with PIDs
- **Manual Refresh**: Refresh page to update status
- **Stop Control**: Stop button terminates bot process

### Via Command Line
```bash
# List running Python processes
ps aux | grep python

# Check specific bot logs
tail -f logs/derivative_trader.log
tail -f logs/spot_trader.log

# Monitor all logs
tail -f logs/*.log
```

### Via System Tools
```bash
# Check process by PID
ps -p <PID>

# Kill process manually (if dashboard stop fails)
kill -TERM <PID>

# Force kill (use as last resort)
kill -9 <PID>
```

## 🔮 Future Enhancements

### Planned Features
- 📊 Real-time log streaming in dashboard
- 📈 Performance metrics and charts
- 🔔 Notifications and alerts
- 💰 Real-time balance display
- 📊 Order book visualization
- 🔄 WebSocket-based real-time updates

### Technical Improvements
- 🔐 Authentication and authorization
- 📝 Persistent bot configuration
- 📊 Historical data storage
- 🔄 Auto-restart on failure
- 📱 Mobile-responsive design
- 🎨 Enhanced UI/UX

## 📞 Support

For issues or questions:
- Check the main project README for bot configuration
- Review log files in `logs/` directory
- Verify configuration in `config/trader_config.json`
- Test bots manually before using web dashboard

## 🔗 Related Documentation

- **[Main README](../README.md)** - Complete project overview
- **[Architecture](../ARCHITECTURE.md)** - System design
- **[Configuration Guide](../config/README.md)** - Configuration reference
- **[Spot Trader Guide](../docs/SPOT_TRADER_GUIDE.md)** - Spot trading details

---

**Simple web dashboard for convenient bot management. Designed for local use and trusted environments.**

*Last updated: October 2025 - Reflects current single-wallet bot architecture*