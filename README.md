# QA Injective Trading Bot - Testnet Liquidity Provision System

> **Professional liquidity provision for Injective Protocol testnet markets**

A sophisticated single-wallet trading system that mirrors mainnet prices on testnet, creating realistic orderbooks and sufficient liquidity depth for paper trading. This bot ensures testnet prices closely match mainnet for an authentic trading experience.

## 🎯 Mission

**Make Injective testnet indistinguishable from mainnet for paper traders.**

This bot provides:
- **Price accuracy**: Testnet prices mirror mainnet prices in real-time
- **Deep liquidity**: Professional-grade orderbook depth across all price levels
- **Realistic conditions**: Paper traders experience mainnet-quality markets
- **Infrastructure support**: Essential testnet ecosystem infrastructure

This is infrastructure building, not profit-focused trading. The goal is creating a realistic testnet environment for the Injective community.

## 🏗️ System Architecture

### Core Components

```
Trading Bots (Single-Wallet Architecture)
├── derivative_trader.py    # Enhanced derivative market trader
├── spot_trader.py          # Enhanced spot market trader  
└── trader.py              # Original unified trader (legacy)

Configuration
├── config/trader_config.json   # Market definitions & parameters
└── .env                        # Wallet private keys (secure)

Management Tools
├── scripts/manual_order_canceller.py  # Emergency order cancellation
├── scripts/position_closer.py         # Position management
└── utils/*                            # Balance checking, health monitoring

Web Interface (Optional)
└── web/app.py                 # Trading bot management dashboard
```

### Trading Strategy

The bots use an intelligent **two-phase strategy** optimized for price convergence:

#### Phase 1: Market Moving (Large Price Gaps >15%)
- **Goal**: Quickly move price toward mainnet
- **Action**: Aggressive directional orders with larger sizes
- **Focus**: Price convergence speed over orderbook aesthetics

#### Phase 2: Orderbook Building (Small Price Gaps <5%)
- **Goal**: Create professional-grade orderbook depth
- **Action**: Build beautiful staircase orderbook with 28-66 orders
- **Focus**: Realistic liquidity depth and natural appearance

#### Phase 3: Maintenance (Price Aligned)
- **Goal**: Keep orderbook fresh and responsive
- **Action**: Gradual updates with depth stage cycling
- **Focus**: Maintain quality without flooding the book

## 🚀 Quick Start

### Prerequisites
- **Python 3.8+**
- **Injective testnet wallet(s)** with INJ tokens (get from faucet)
- **Virtual environment** (recommended)

### Installation

1. **Clone and setup**:
```bash
git clone <repository-url>
cd qa-python-injective-trading-bot
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure wallets**:
```bash
cp env.example .env
# Edit .env with your wallet private keys
```

Your `.env` should look like:
```bash
# Wallet 1 - Primary Market Maker
WALLET_1_PRIVATE_KEY=0xYOUR_PRIVATE_KEY_HERE
WALLET_1_NAME=Primary Market Maker
WALLET_1_ENABLED=true

# Wallet 2 - QA Market Maker  
WALLET_2_PRIVATE_KEY=0xYOUR_PRIVATE_KEY_HERE
WALLET_2_NAME=QA Market Maker
WALLET_2_ENABLED=true

# Wallet 3 - QA Market Taker
WALLET_3_PRIVATE_KEY=0xYOUR_PRIVATE_KEY_HERE
WALLET_3_NAME=QA Market Taker
WALLET_3_ENABLED=true
```

3. **Configure markets** (optional):

Edit `config/trader_config.json` to enable/disable markets or adjust parameters.

### Running the Bots

#### Derivative Trading
```bash
# Trade all enabled derivative markets
python derivative_trader.py wallet_1

# Trade specific derivative market
python derivative_trader.py wallet_1 --markets INJ/USDT-PERP

# List available markets
python derivative_trader.py wallet_1 --list-markets
```

#### Spot Trading
```bash
# Trade all enabled spot markets
python spot_trader.py wallet1

# Trade specific spot market
python spot_trader.py wallet1 INJ/USDT
python spot_trader.py wallet1 stINJ/INJ
```

#### Multiple Wallets (Parallel Execution)
Run separate terminal sessions for each wallet:
```bash
# Terminal 1
python derivative_trader.py wallet_1

# Terminal 2  
python derivative_trader.py wallet_2

# Terminal 3
python spot_trader.py wallet3
```

## 🌐 Web Dashboard (Optional)

A modern web interface for monitoring and controlling trading bots.

### Launch Dashboard
```bash
cd web
python app.py
# Open browser to http://localhost:8000
```

### Features
- Real-time bot status monitoring
- Wallet balance tracking
- Live activity feed
- Start/stop bot controls
- Market information display

## 📊 How It Works

### Price Discovery Flow

```
1. Fetch Mainnet Price → Get real market price from Injective mainnet
2. Fetch Testnet Price → Get current testnet price
3. Calculate Gap → Determine percentage difference
4. Select Strategy → Choose phase based on gap size
5. Execute Orders → Place/cancel orders in batch transaction
6. Wait & Repeat → 15-second cycle, continuous operation
```

### Orderbook Building Example

When building depth, the bot creates natural-looking orderbooks:

```
Price      Size     Type
24.5654    16.3     Tight (0.01% from center)
24.5623    19.8     Tight
24.5592    15.7     Tight
24.5561    21.4     Tight
24.5530    18.2     Tight

24.5499    23.6     Medium (0.1% from center)
24.5468    27.1     Medium
24.5437    22.9     Medium
24.5406    25.8     Medium
24.5375    20.4     Medium

--- MAINNET PRICE: $24.5623 ---

24.5685    24.7     Medium
24.5716    28.3     Medium
24.5747    23.1     Medium
...
```

**Result**: 28-66 orders per market creating smooth, professional depth.

## ⚙️ Configuration

### Market Configuration

Edit `config/trader_config.json`:

```json
{
  "wallets": {
    "wallet_1": {
      "markets": ["INJ/USDT", "stINJ/INJ", "INJ/USDT-PERP"],
      "trading_params": {
        "spread_percent": 0.5,
        "order_size": 15,
        "orders_per_market": 3
      }
    }
  },
  "markets": {
    "INJ/USDT": {
      "testnet_market_id": "0x0611780ba69656949525013d947713300f56c37b6175e02f26bffa495c3208fe",
      "mainnet_market_id": "0xa508cb32923323679f29a032c70342c147c17d0145625922b0ef22e955c844c0",
      "type": "spot",
      "spread_percent": 0.5,
      "order_size": 15
    },
    "INJ/USDT-PERP": {
      "testnet_market_id": "0x17ef48032cb24375ba7c2e39f384e56433bcab20cbee9a7357e4cba2eb00abe6",
      "mainnet_market_id": "0x9b9980167ecc3645ff1a5517886652d94a0825e54a77d2057cbbe3ebee015963",
      "type": "derivative",
      "spread_percent": 0.3,
      "order_size": 8
    }
  }
}
```

### Key Parameters
- `type`: "spot" or "derivative"
- `spread_percent`: Base spread for orders
- `order_size`: Base order size
- `testnet_market_id`: Market ID on testnet
- `mainnet_market_id`: Market ID on mainnet (for price reference)

## 🛠️ Management Tools

### Emergency Order Cancellation
```bash
python scripts/manual_order_canceller.py --wallet all --market all
```

### Position Closing
```bash
python scripts/position_closer.py
```

### Balance Checking
```bash
python utils/balance_checker.py wallet_1
```

### Health Monitoring
```bash
# Check testnet status
python utils/health_checker.py

# Check mainnet status
python utils/health_checker.py --network mainnet
```

### Market Comparison
```bash
# Compare all markets (spot + derivative)
python utils/market_comparison_unified.py --compare-all

# Compare specific market type
python utils/market_comparison_unified.py \
  --testnet data/testnet_spot_market_data.json \
  --mainnet data/mainnet_spot_market_data.json
```

## 📊 Performance & Features

### Orderbook Quality
- **Before**: 6-12 sparse orders with obvious gaps
- **After**: 28-66 natural orders with smooth depth progression
- **Result**: Indistinguishable from mainnet for paper trading

### Price Accuracy
- **Deviation threshold**: <2% from mainnet
- **Update frequency**: Every 15 seconds
- **Response time**: Immediate when gap detected

### Sequence Management
- **Automatic recovery** from sequence mismatches
- **Circuit breaker** after consecutive errors
- **Proactive refresh** every 30 seconds
- **Bulletproof operation** with comprehensive error handling

### Transaction Efficiency
- **Batch transactions** for create + cancel operations
- **Reduced gas costs** through batching
- **Atomic operations** prevent partial failures

## 📁 Project Structure

```
├── derivative_trader.py       # Main derivative trading bot
├── spot_trader.py            # Main spot trading bot
├── trader.py                 # Original unified trader (legacy)
│
├── config/
│   ├── trader_config.json    # Market configuration
│   └── markets_config.json   # Alternative market config (deprecated)
│
├── scripts/
│   ├── manual_order_canceller.py  # Emergency cancellation
│   └── position_closer.py         # Position management
│
├── utils/
│   ├── secure_wallet_loader.py    # Wallet configuration
│   ├── balance_checker.py         # Balance monitoring
│   ├── health_checker.py          # Network health checks
│   ├── market_comparison_unified.py  # Market data analysis
│   ├── check_open_orders.py       # Order monitoring
│   └── check_positions.py         # Position monitoring
│
├── web/
│   ├── app.py                # Web dashboard backend
│   └── static/              # Web dashboard frontend
│
├── docs/
│   ├── SPOT_TRADER_GUIDE.md           # Comprehensive spot guide
│   ├── SEQUENCE_MANAGEMENT_GUIDE.md   # Sequence error prevention
│   └── BEAUTIFUL_ORDERBOOK_EXAMPLE.md # Orderbook design theory
│
├── data/                    # Market data snapshots
├── logs/                    # Trading logs
├── tests/                   # Test suites
└── requirements.txt         # Python dependencies
```

## 📚 Documentation

### Trader Guides
- **[Spot Trader Guide](docs/SPOT_TRADER_GUIDE.md)** - Complete guide for spot trading
- **[Sequence Management Guide](docs/SEQUENCE_MANAGEMENT_GUIDE.md)** - Error prevention
- **[Orderbook Design Guide](docs/BEAUTIFUL_ORDERBOOK_EXAMPLE.md)** - Theory and examples

### System Documentation
- **[Architecture Overview](ARCHITECTURE.md)** - System design and components
- **[Project Structure](PROJECT_STRUCTURE.md)** - File organization
- **[Configuration Guide](config/README.md)** - Configuration reference

### Utility Documentation
- **[Health Checker Guide](utils/HEALTH_CHECKER_README.md)** - Network diagnostics
- **[Utilities README](utils/README.md)** - Utility tools overview

## 🔒 Security & Risk Management

### Security Best Practices
- **Private keys in .env** - Never commit to version control
- **Testnet only by default** - Mainnet requires explicit configuration
- **Secure wallet loading** - Environment variable isolation
- **Log sanitization** - Sensitive data filtered from logs

### Risk Controls
- **Sequence management** - Prevents transaction conflicts
- **Circuit breakers** - Automatic pause after errors
- **Balance monitoring** - Real-time balance tracking
- **Order limits** - Configurable per-wallet maximums

### Operational Safety
- **Graceful shutdown** - Clean exit on Ctrl+C
- **Error recovery** - Automatic retry with backoff
- **Transaction logging** - Full audit trail with blockchain hashes
- **Health monitoring** - Pre-trade network checks

## ⚠️ Important Notes

### Testnet Configuration
- Configured for Injective **testnet** by default
- Use testnet wallets and tokens (free from faucet)
- Never use mainnet private keys in testnet configuration
- Testnet tokens have no real value

### Operational Considerations
- **Monitor initially** - Watch first few cycles for proper operation
- **Multiple wallets** - Run in separate terminals for deeper liquidity
- **Log monitoring** - Check logs regularly for errors
- **Network status** - Use health checker before starting

### Performance Stats
- **Order success rate**: ~95-98%
- **Sequence error rate**: <1% with enhanced management
- **Price convergence**: Typically within 2-3 cycles
- **Resource usage**: Low CPU/memory footprint

## 🔧 Troubleshooting

### Common Issues

**"No wallets found"**
- Check `.env` file exists and has correct format
- Verify `WALLET_X_ENABLED=true` is set
- Ensure private keys are valid hex strings

**"Sequence mismatch" errors**
- Bots have automatic recovery built-in
- Wait 10-30 seconds for automatic resolution
- Circuit breaker will pause and recover automatically

**"Mainnet price failed"**
- Network connectivity issue
- Bot will retry automatically
- Check with `python utils/health_checker.py --network mainnet`

**"Market not found"**
- Verify market is enabled in `config/trader_config.json`
- Check market type matches bot (spot vs derivative)
- Ensure market IDs are correct for testnet

### Debug Mode

Enable verbose logging by checking log files:
```bash
# Spot trader logs
tail -f logs/spot_trader.log

# Derivative trader logs
tail -f logs/derivative_trader.log

# General trading logs
tail -f logs/trader.log
```

## 🚀 Production Deployment

### Using Screen (Simple)
```bash
# Start in screen session
screen -S derivative-wallet1
python derivative_trader.py wallet_1
# Ctrl+A, D to detach

# Reattach later
screen -r derivative-wallet1
```

### Using nohup (Background)
```bash
nohup python derivative_trader.py wallet_1 > logs/derivative_wallet1.log 2>&1 &
nohup python spot_trader.py wallet2 > logs/spot_wallet2.log 2>&1 &
```

### Using systemd (Recommended)
Create service files in `/etc/systemd/system/`:

```ini
[Unit]
Description=Injective Derivative Trader - Wallet 1
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/qa-python-injective-trading-bot
Environment="PATH=/path/to/qa-python-injective-trading-bot/venv/bin"
ExecStart=/path/to/venv/bin/python derivative_trader.py wallet_1
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## 🔮 Future Enhancements

### Planned Features
- Advanced analytics and performance metrics
- Strategy configuration via web interface
- Additional market types and trading pairs
- Enhanced risk management controls
- Mobile application for monitoring

### Technical Improvements
- Database integration for historical data
- Improved error classification and handling
- Advanced orderbook algorithms
- Multi-network support enhancements

## 📞 Support

For issues or questions:
1. Check the relevant documentation in `docs/`
2. Review log files for detailed error messages
3. Use health checker to diagnose network issues
4. Check configuration files for proper setup

## 📈 Success Metrics

The bot is successfully operating when:
- Testnet prices consistently within 2% of mainnet
- Orderbooks show 30+ orders across price levels
- Paper traders report realistic trading conditions
- Sequence errors occur <1% of the time
- Price convergence happens within minutes of divergence

---

## 🎯 Project Goals

**Primary Goal**: Make Injective testnet prices and liquidity match mainnet quality.

**Success Criteria**: 
- Paper traders can't distinguish testnet from mainnet
- Sufficient liquidity depth for realistic order execution
- Price accuracy enables meaningful strategy testing
- Infrastructure supports Injective ecosystem growth

**Built for the Injective community** to enable realistic paper trading and strategy development.

---

*This is testnet infrastructure for the ecosystem. Use responsibly and help make Injective testnet better for everyone.*