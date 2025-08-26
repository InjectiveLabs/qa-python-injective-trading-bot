# 🚀 Injective Multi-Wallet Trading Bot

A high-performance, multi-wallet market making bot for Injective testnet with real-time price correction, rich orderbook creation, and parallel wallet execution.

## ✨ Features

### 🎯 Core Trading Features
- **Multi-Wallet Parallel Execution** - Run 3 wallets simultaneously with independent sequence management
- **Real-Time Price Correction** - Automatically correct testnet prices to match mainnet prices
- **Rich Orderbook Creation** - Place randomized orders (0.1-10.0 INJ) across multiple price levels
- **Sequence Mismatch Protection** - Intelligent cooldown system to prevent transaction conflicts
- **Immediate Shutdown** - Responsive Ctrl+C handling for emergency stops

### 📊 Market Intelligence
- **Live Price Monitoring** - Real-time comparison between Injective mainnet and testnet prices
- **Price Movement Tracking** - Clear indicators showing price direction (UP/DOWN) and percentage differences
- **Mainnet Price Integration** - Fetch accurate market prices directly from Injective mainnet
- **Dynamic Order Sizing** - Randomized order sizes for natural-looking orderbook depth

### 🛡️ Risk Management
- **Cooldown System** - Automatic 10-second cooldown when sequence mismatches occur
- **Order Validation** - Comprehensive error handling and retry mechanisms
- **Balance Monitoring** - Real-time wallet balance and sequence tracking
- **Graceful Error Recovery** - Automatic sequence refresh and retry logic

## 🏗️ Architecture

```
multi_wallet_trader.py          # Main CLI trading system
├── WalletTrader Class         # Individual wallet management
├── Parallel Execution         # Multi-wallet coordination
├── Price Correction Logic     # Mainnet/testnet price alignment
└── Rich Orderbook Creation    # Randomized order placement

batch_cancel_orders.py         # Order cancellation utility
├── Multi-Wallet Support       # Cancel orders from all wallets
├── Spot & Derivative Orders   # Support for both market types
└── Batch Operations           # Efficient bulk cancellation

Infrastructure (Preserved):
├── core/                      # Client, markets, wallet management
├── strategies/                # Strategy framework for future expansion
├── api/                       # Web UI API endpoints
├── ui/                        # Web interface components
└── models/                    # Data models and configurations
```

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Injective testnet wallets with INJ tokens
- Virtual environment

### Installation

1. **Clone and Setup**
```bash
git clone <repository-url>
cd qa-python-injective-trading-bot
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure Wallets**
```bash
cp env.example .env
# Edit .env with your wallet private keys
```

3. **Update Wallet Configuration**
Edit `wallets_config.json`:
```json
{
  "wallets": [
    {
      "id": "wallet_1",
      "private_key": "your_private_key_1"
    },
    {
      "id": "wallet_2", 
      "private_key": "your_private_key_2"
    },
    {
      "id": "wallet_3",
      "private_key": "your_private_key_3"
    }
  ]
}
```

4. **Configure Markets**
Edit `markets_config.json`:
```json
{
  "markets": [
    {
      "market_id": "0x0611780ba69656949525013d947713300f56c37b6175e02f26bffa495c3208fe",
      "symbol": "INJ/USDT",
      "enabled": true,
      "type": "spot",
      "spread_percent": 0.5,
      "order_size": 10.0
    }
  ]
}
```

### Usage

#### 🎯 Start Multi-Wallet Trading
```bash
source venv/bin/activate
python3 multi_wallet_trader.py
```

**What happens:**
- All 3 wallets initialize independently
- Each wallet fetches current mainnet and testnet prices
- Price differences are calculated and displayed
- Rich orderbooks are created with randomized sizes
- Orders are placed with 5-second delays to prevent sequence conflicts
- Real-time price movement tracking shows progress

#### 🛑 Cancel All Orders
```bash
source venv/bin/activate
python3 batch_cancel_orders.py
```

**What happens:**
- All open orders from all wallets are identified
- Batch cancellation is executed for maximum efficiency
- Success/failure status is reported for each wallet

## 📊 System Output

### Trading Session Example
```
[wallet_1] 💰 INJ/USDT | Mainnet: $12.9600 | Testnet: $16.9320 | Diff: 30.65% | Need to push 📉 DOWN
[wallet_1] 📉 Price difference: 30.65% | Pushing price DOWN from $16.9320 → $12.9600
[wallet_1] 📤 Placing SELL order 1: 3.5 INJ at $16.9151 (moving price DOWN)
[wallet_1] ✅ SELL order 1 SUCCESS: 3.5 INJ at $16.9151
[wallet_1] 🔄 Sequence synced: 425

[wallet_2] 💰 INJ/USDT | Mainnet: $12.9600 | Testnet: $16.8790 | Diff: 30.24% | Need to push 📉 DOWN
[wallet_2] 📤 Placing SELL order 1: 5.0 INJ at $16.8621 (moving price DOWN)
[wallet_2] ✅ SELL order 1 SUCCESS: 5.0 INJ at $16.8621

[wallet_3] 🎯 Rich orderbook created: 10 orders, 34.9 INJ total
```

### Price Correction Progress
```
Initial: Testnet $16.93 → Mainnet $12.96 (30.65% difference)
After 1 cycle: Testnet $16.15 → Mainnet $12.96 (24.64% difference)
After 2 cycles: Testnet $15.40 → Mainnet $12.96 (18.82% difference)
```

## ⚙️ Configuration

### Order Sizing
- **Range**: 0.1 to 10.0 INJ per order
- **Randomization**: Each cycle uses different random combinations
- **Quantity**: 10 orders per cycle per wallet
- **Total Volume**: Up to 100 INJ per cycle across all wallets

### Price Levels
- **BUY Orders**: +0.1% to +1.0% above current price
- **SELL Orders**: -0.1% to -1.0% below current price
- **Correction Threshold**: 5% price difference triggers action

### Timing
- **Order Delay**: 5 seconds between orders
- **Cooldown**: 10 seconds when sequence mismatches occur
- **Cycle Interval**: 10 seconds between trading cycles

## 🔧 Advanced Features

### Sequence Management
- **Independent Sequences**: Each wallet maintains its own sequence number
- **Automatic Refresh**: Sequences are refreshed after each successful order
- **Mismatch Detection**: Intelligent detection and recovery from sequence errors
- **Cooldown System**: Automatic pause when conflicts are detected

### Price Correction Logic
- **Mainnet Integration**: Real-time price fetching from Injective mainnet
- **Dynamic Thresholds**: Configurable price difference thresholds
- **Directional Trading**: Automatic BUY/SELL based on price direction
- **Progress Tracking**: Real-time display of price movement progress

### Rich Orderbook Creation
- **Randomized Sizes**: Natural-looking order distribution
- **Multiple Levels**: Orders placed across 10 price levels
- **Volume Distribution**: Mix of small, medium, and large orders
- **Market Impact**: Significant price movement capability

## 🛠️ Development

### Project Structure
```
├── multi_wallet_trader.py     # Main trading system
├── batch_cancel_orders.py     # Order management utility
├── wallets_config.json        # Wallet configuration
├── markets_config.json        # Market configuration
├── core/                      # Infrastructure components
├── strategies/                # Strategy framework
├── api/                       # Web API endpoints
├── ui/                        # Web interface
├── models/                    # Data models
├── config/                    # Configuration management
├── utils/                     # Utility functions
└── legacy/                    # Archived redundant files
```

### Adding New Features
- **New Strategies**: Extend `strategies/base_strategy.py`
- **Web UI**: Use existing FastAPI setup in `main.py`
- **Perpetual Trading**: Leverage derivative support in `core/client.py`
- **Risk Management**: Add position limits and stop-losses

## 🚨 Important Notes

### Testnet Only
- This bot is configured for Injective **testnet** only
- Use testnet wallets and tokens
- Never use mainnet private keys

### Risk Disclaimer
- This is experimental software
- Use at your own risk
- Start with small amounts
- Monitor the bot continuously

### Performance
- **Order Success Rate**: ~95% (some timeout errors are normal)
- **Price Impact**: Can move prices 15-30% per cycle
- **Sequence Conflicts**: Rare with current timing settings
- **Resource Usage**: Low CPU/memory footprint

## 🔮 Future Enhancements

### Planned Features
- **Web Dashboard**: Real-time monitoring and control interface
- **Perpetual Trading**: Support for derivatives markets
- **Risk Management**: Position limits and stop-loss mechanisms
- **Performance Analytics**: Detailed P&L and success rate tracking
- **Multi-Market Support**: Trade multiple assets simultaneously

### Infrastructure Ready
- **Web UI Framework**: FastAPI backend with frontend components
- **Strategy Framework**: Extensible strategy system
- **Multi-Wallet Support**: Scalable wallet management
- **Market Data**: Comprehensive market data infrastructure

## 📞 Support

For issues, questions, or contributions:
- Check the `legacy/` folder for reference implementations
- Review the configuration files for customization options
- Monitor the console output for detailed error messages

---

**Built with ❤️ for the Injective ecosystem**
