# Project Structure

Clean, professional project organization for the Injective testnet liquidity provision system.

## 🎯 Core Trading Bots

### **Main Trading Scripts**
```
derivative_trader.py        # Enhanced derivative trader (primary bot)
spot_trader.py             # Enhanced spot trader (primary bot)
trader.py                  # Original unified trader (legacy, basic strategy)
```

**Usage**:
```bash
# Derivative trading
python derivative_trader.py wallet_1
python derivative_trader.py wallet_1 --markets INJ/USDT-PERP

# Spot trading
python spot_trader.py wallet1
python spot_trader.py wallet1 INJ/USDT
```

## ⚙️ Configuration

### **Configuration Files**
```
config/
├── trader_config.json     # Main configuration (markets, wallets, parameters)
├── markets_config.json    # Alternative config (deprecated)
└── README.md              # Configuration documentation

.env                       # Wallet private keys (NOT in git)
env.example               # Environment template
```

**Critical Files**:
- `trader_config.json` - Market definitions and trading parameters
- `.env` - Wallet private keys (must be created from `env.example`)

## 🛠️ Management Scripts

### **Emergency & Maintenance Tools**
```
scripts/
├── __init__.py
├── manual_order_canceller.py  # Cancel orders across markets
└── position_closer.py         # Close derivative positions
```

**Usage**:
```bash
# Cancel all orders
python scripts/manual_order_canceller.py --wallet all --market all

# Close all positions
python scripts/position_closer.py
```

## 🔧 Utility Functions

### **Helper Utilities**
```
utils/
├── __init__.py
├── secure_wallet_loader.py        # Wallet loading from .env
├── balance_checker.py             # Check wallet balances
├── check_open_orders.py           # Monitor open orders
├── check_positions.py             # Monitor derivative positions
├── market_comparison_unified.py   # Compare testnet vs mainnet markets
├── health_checker.py              # Network health diagnostics
├── logger.py                      # Centralized logging
├── README.md                      # Utilities overview
└── HEALTH_CHECKER_README.md       # Health checker guide
```

**Common Utilities**:
```bash
# Check wallet balance
python utils/balance_checker.py wallet_1

# Check network health
python utils/health_checker.py
python utils/health_checker.py --network mainnet

# Compare markets
python utils/market_comparison_unified.py --compare-all
```

## 📚 Documentation

### **User Guides**
```
docs/
├── SPOT_TRADER_GUIDE.md           # Complete spot trading guide
├── SEQUENCE_MANAGEMENT_GUIDE.md   # Sequence error prevention
└── BEAUTIFUL_ORDERBOOK_EXAMPLE.md # Orderbook design theory
```

### **Project Documentation**
```
README.md                 # Main project documentation
ARCHITECTURE.md           # System architecture overview
PROJECT_STRUCTURE.md      # This file
```

**Documentation Structure**:
- **README.md** - Start here for overview and quick start
- **ARCHITECTURE.md** - Deep dive into system design
- **docs/** - Topic-specific guides and tutorials

## 🧪 Testing

### **Test Files**
```
tests/
└── test_enhanced_derivative_strategy.py  # Strategy validation tests
```

**Running Tests**:
```bash
python tests/test_enhanced_derivative_strategy.py
```

## 📊 Data & Analysis

### **Market Data**
```
data/
├── mainnet_derivative_market_data.json            # Mainnet derivative data
├── testnet_derivative_market_data.json            # Testnet derivative data
├── mainnet_spot_market_data.json                  # Mainnet spot data
├── testnet_spot_market_data.json                  # Testnet spot data
├── derivative_market_data_comparison_report.txt   # Analysis reports
└── spot_market_comparison_report.txt              # Analysis reports
```

**Purpose**: Snapshots of market data for analysis and comparison.

## 📝 Runtime Files

### **Logs**
```
logs/
├── derivative_trader.log      # Derivative trading logs
├── spot_trader.log           # Spot trading logs
├── spot_trader.log.YYYY-MM-DD # Rotated spot logs (daily)
├── trader.log                # General trading logs
└── enhanced_trading.log      # Enhanced strategy logs
```

**Log Rotation**:
- Spot trader: Daily rotation at midnight, keeps 7 days
- Other logs: Manual rotation or size-based

## 🌐 Web Dashboard (Optional)

### **Web Interface**
```
web/
├── app.py                 # FastAPI backend
├── README.md             # Web dashboard documentation
└── static/
    ├── index.html        # Dashboard UI
    └── script.js         # Frontend logic
```

**Launch**:
```bash
cd web
python app.py
# Open http://localhost:8000
```

**Features**:
- Real-time bot monitoring
- Start/stop bot controls
- Wallet balance tracking
- Live activity feed

## 📦 Dependencies

### **Python Environment**
```
requirements.txt          # All Python dependencies (single file)
venv/                    # Virtual environment (not in git)
```

**Setup**:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 🗂️ Complete File Tree

```
qa-python-injective-trading-bot/
│
├── 🤖 Trading Bots
│   ├── derivative_trader.py       ⭐ Primary derivative trader
│   ├── spot_trader.py            ⭐ Primary spot trader
│   └── trader.py                  Legacy unified trader
│
├── ⚙️ Configuration
│   ├── config/
│   │   ├── trader_config.json    ⭐ Main configuration
│   │   ├── markets_config.json    (Deprecated)
│   │   └── README.md
│   ├── .env                      ⭐ Private keys (create from env.example)
│   └── env.example                Template for .env
│
├── 🛠️ Management
│   └── scripts/
│       ├── manual_order_canceller.py
│       └── position_closer.py
│
├── 🔧 Utilities
│   └── utils/
│       ├── secure_wallet_loader.py
│       ├── balance_checker.py
│       ├── health_checker.py
│       ├── market_comparison_unified.py
│       ├── check_open_orders.py
│       ├── check_positions.py
│       ├── logger.py
│       ├── README.md
│       └── HEALTH_CHECKER_README.md
│
├── 📚 Documentation
│   ├── docs/
│   │   ├── SPOT_TRADER_GUIDE.md
│   │   ├── SEQUENCE_MANAGEMENT_GUIDE.md
│   │   └── BEAUTIFUL_ORDERBOOK_EXAMPLE.md
│   ├── README.md              ⭐ Start here
│   ├── ARCHITECTURE.md
│   └── PROJECT_STRUCTURE.md    (This file)
│
├── 🧪 Testing
│   └── tests/
│       └── test_enhanced_derivative_strategy.py
│
├── 📊 Data
│   └── data/
│       ├── mainnet_derivative_market_data.json
│       ├── testnet_derivative_market_data.json
│       ├── mainnet_spot_market_data.json
│       ├── testnet_spot_market_data.json
│       ├── derivative_market_data_comparison_report.txt
│       └── spot_market_comparison_report.txt
│
├── 📝 Logs
│   └── logs/
│       ├── derivative_trader.log
│       ├── spot_trader.log
│       ├── trader.log
│       └── enhanced_trading.log
│
├── 🌐 Web Dashboard
│   └── web/
│       ├── app.py
│       ├── README.md
│       └── static/
│           ├── index.html
│           └── script.js
│
└── 📦 Environment
    ├── requirements.txt        ⭐ All dependencies
    ├── venv/                   (Not in git)
    └── __pycache__/           (Not in git)
```

## 🗑️ Files Removed During Cleanup

### **Development Artifacts** ❌
- `debug_order_placement.py` - Temporary debugging script
- `quick_debug.py` - Development tool
- `integration_test.py` - Old integration tests
- `manager.py` - Superseded manager script

### **Old Multi-Wallet System** ❌
- `scripts/multi_wallet_trader.py` - Replaced by single-wallet architecture
- `scripts/enhanced_multi_wallet_trader.py` - Superseded implementation
- `scripts/batch_cancel_orders.py` - Functionality moved to manual_order_canceller.py

### **Old Test Files** ❌
- `test_derivative_pricing.py` - Debugging tests
- `test_derivative_trader.py` - Old trader tests
- `test_mainnet_price.py` - Price testing
- `test_mid_price_method.py` - Method testing
- `test_sequence_fix.py` - Sequence debugging
- `test_smart_derivative_pricing.py` - Old strategy tests
- `test_transaction_id_logging.py` - Logging tests
- `test_tx_response_format.py` - Format tests

### **Cache Files** ❌
- All `__pycache__/` directories (regenerated automatically)
- All `*.pyc` compiled files (regenerated automatically)

### **Deprecated Configuration** ❌
- `config/wallets_config.json` - Replaced by .env-based configuration

## 🚀 Quick Start Guide

### 1. Initial Setup
```bash
# Clone and setup environment
git clone <repository-url>
cd qa-python-injective-trading-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configuration
```bash
# Setup wallet keys
cp env.example .env
# Edit .env with your private keys

# Configure markets (optional)
# Edit config/trader_config.json
```

### 3. Run Bots
```bash
# Derivative trading
python derivative_trader.py wallet_1

# Spot trading
python spot_trader.py wallet1

# Or use web dashboard
cd web && python app.py
```

## 📊 Project Evolution

### **Before Cleanup** (V1 - Multi-Wallet Coordinator)
- Total files: ~40+ files
- Test files: 11 development test files
- Architecture: Central multi-wallet coordinator
- Complexity: High, difficult to maintain

### **After Cleanup** (V2 - Single-Wallet Independent)
- Core bots: 2 main trading bots + 1 legacy
- Test files: 1 comprehensive test
- Architecture: Single-wallet independent bots
- Complexity: Low, easy to maintain
- Documentation: Organized and comprehensive

### **Results** ✅
- **Cleaner codebase**: Removed 15+ obsolete files
- **Better organization**: Clear separation of concerns
- **Improved maintainability**: Simpler architecture
- **Professional structure**: Production-ready

## 📋 Component Relationships

```
Configuration Files → Trading Bots
    trader_config.json ─────► derivative_trader.py
    .env ──────────────────► spot_trader.py
                           └─► trader.py (legacy)

Trading Bots → Utilities
    All Bots ──────────────► secure_wallet_loader.py
               ├───────────► logger.py
               └───────────► health_checker.py

Management Scripts → Utilities
    manual_order_canceller ─► secure_wallet_loader.py
    position_closer ────────► secure_wallet_loader.py

Web Dashboard → Everything
    web/app.py ─────────────► All bots (spawns processes)
               ├───────────► Configuration files
               └───────────► Log files
```

## 🎯 Key Files by Use Case

### **I want to trade derivatives**
- `derivative_trader.py` - Main bot
- `config/trader_config.json` - Configure markets
- `.env` - Add wallet keys
- `docs/SEQUENCE_MANAGEMENT_GUIDE.md` - Understand error handling

### **I want to trade spot markets**
- `spot_trader.py` - Main bot
- `config/trader_config.json` - Configure markets
- `.env` - Add wallet keys
- `docs/SPOT_TRADER_GUIDE.md` - Complete guide

### **I want to monitor bots**
- `web/app.py` - Web dashboard
- `logs/*.log` - Log files
- `utils/balance_checker.py` - Check balances
- `utils/check_open_orders.py` - Check orders

### **I want to manage orders**
- `scripts/manual_order_canceller.py` - Cancel orders
- `scripts/position_closer.py` - Close positions
- `utils/check_positions.py` - Check positions

### **I want to analyze markets**
- `utils/market_comparison_unified.py` - Compare markets
- `data/*_market_data.json` - Market snapshots
- `data/*_comparison_report.txt` - Analysis reports

## 💡 Navigation Tips

1. **New to the project?** Start with `README.md`
2. **Want to understand architecture?** Read `ARCHITECTURE.md`
3. **Need to configure?** Check `config/README.md`
4. **Troubleshooting?** Look in `docs/` for specific guides
5. **Quick reference?** This file (PROJECT_STRUCTURE.md)

---

**Clean, professional project structure optimized for testnet liquidity provision mission.**

*Last updated: October 2025 - Reflects current production structure*