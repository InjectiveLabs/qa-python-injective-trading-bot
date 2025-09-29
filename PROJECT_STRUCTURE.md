# 📁 Clean Project Structure

## 🎯 Core Trading Files

### **Main Trading Bots**
```
derivative_trader.py        # ⭐ Enhanced derivative trader (main bot)
trader.py                  # 📊 Original unified trader (spot + basic derivatives)
```

### **Configuration**
```
config/
├── trader_config.json     # 🔧 Main trading configuration
├── markets_config.json    # 📈 Market definitions  
└── README.md              # 📋 Config documentation
```

### **Environment**
```
.env                       # 🔐 Private keys (not in repo)
env.example               # 📝 Environment template
requirements.txt          # 📦 Python dependencies
```

## 🛠️ Utilities & Scripts

### **Management Scripts**
```
scripts/
├── manual_order_canceller.py  # 🗑️ Emergency order cancellation
└── position_closer.py         # 📊 Position management
```

### **Utility Functions**
```
utils/
├── secure_wallet_loader.py    # 🔐 Wallet management
├── balance_checker.py         # 💰 Account balance checking
├── check_open_orders.py       # 📋 Order monitoring
├── check_positions.py         # 📊 Position monitoring
├── market_comparison_unified.py # 📈 Market analysis
└── logger.py                  # 📝 Logging utilities
```

## 📚 Documentation

### **User Guides**
```
docs/
├── SEQUENCE_MANAGEMENT_GUIDE.md      # 🛡️ Sequence error prevention
├── BEAUTIFUL_ORDERBOOK_EXAMPLE.md    # 🎨 Orderbook design guide
├── AGGRESSIVE_LIQUIDITY_CONFIG.md    # ⚡ Performance optimization
└── README_manual_canceller.md       # 🗑️ Order cancellation guide
```

### **Project Documentation**
```
README.md                 # 🏠 Main project documentation
ARCHITECTURE.md           # 🏗️ System architecture overview
PROJECT_STRUCTURE.md      # 📁 This file
```

## 🧪 Testing

### **Test Files**
```
tests/
└── test_enhanced_derivative_strategy.py  # 🧪 Strategy validation
```

## 📊 Data & Analysis

### **Market Data**
```
data/
├── mainnet_derivative_market_data.json      # 🌐 Mainnet derivative data
├── testnet_derivative_market_data.json      # 🧪 Testnet derivative data
├── mainnet_spot_market_data.json           # 🌐 Mainnet spot data
├── testnet_spot_market_data.json           # 🧪 Testnet spot data
├── derivative_market_data_comparison_report.txt  # 📊 Analysis report
└── spot_market_comparison_report.txt       # 📊 Analysis report
```

## 📝 Runtime Files

### **Logs**
```
logs/
├── derivative_trader.log   # 📝 Derivative trading logs
├── trader.log             # 📝 General trading logs  
└── enhanced_trading.log   # 📝 Enhanced strategy logs
```

### **Web Dashboard** (Optional)
```
web/
├── app.py                 # 🌐 FastAPI web interface
├── requirements.txt       # 📦 Web dependencies
├── README.md             # 📋 Web setup guide
└── static/
    ├── index.html        # 🎨 Dashboard UI
    └── script.js         # ⚡ Frontend logic
```

## 🗑️ Files Removed During Cleanup

### **Development Artifacts** ❌
- `debug_order_placement.py` - Temporary debugging
- `quick_debug.py` - Development tool
- `integration_test.py` - Old integration tests
- `manager.py` - Superseded manager

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
- All `__pycache__/` directories
- All `*.pyc` compiled files

### **Superseded Scripts** ❌
- `scripts/enhanced_multi_wallet_trader.py` - Old implementation

## 🚀 Quick Start

### **Run Main Bot**
```bash
# Enhanced derivative trader (recommended)
python derivative_trader.py wallet_1

# Original unified trader
python trader.py wallet_1
```

### **Emergency Controls**
```bash
# Cancel all orders
python scripts/manual_order_canceller.py --wallet all --market all

# Check account status
python utils/balance_checker.py wallet_1
```

### **Testing**
```bash
# Test enhanced strategy
python tests/test_enhanced_derivative_strategy.py
```

## 📊 Project Statistics

### **Before Cleanup**
- **Total Files**: ~40+ files
- **Test Files**: 11 development test files
- **Documentation**: Scattered across root directory
- **Cache Files**: Multiple `__pycache__` directories

### **After Cleanup**
- **Core Files**: 2 main trading bots
- **Test Files**: 1 comprehensive test
- **Documentation**: Organized in `docs/` directory
- **Structure**: Clean, professional organization

**Result**: 🧹 **Clean, professional project structure ready for production!**
