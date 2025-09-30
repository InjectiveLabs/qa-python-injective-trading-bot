# 🎨 Enhanced Spot Trader Guide

## Overview

The **Enhanced Spot Trader** (`spot_trader.py`) creates beautiful, realistic orderbooks for spot markets on Injective testnet. It mirrors the sophisticated two-phase strategy from the derivative trader but is specifically designed for spot markets.

## 🚀 Quick Start

### Run All Enabled Spot Markets
```bash
python spot_trader.py wallet1
```

### Run Specific Market Only
```bash
python spot_trader.py wallet1 INJ/USDT
python spot_trader.py wallet1 stINJ/INJ
```

## 🎯 Intelligent Multi-Phase Strategy

### Phase 0: ORDERBOOK ASSESSMENT (Always First)
**Before any action, the bot assesses current orderbook:**
- ✅ Counts total orders in the book
- ✅ Counts orders within 5% of mainnet price
- ✅ Evaluates if depth is sufficient (50+ orders, 20+ near price)
- ✅ Decides strategy based on depth + price gap

### Phase 1: MARKET MOVING (Price Wrong, Depth Exists)
**When price gap >2% AND orderbook has 30+ orders:**
- 🎯 **Cancel 8-12 old orders** far from mainnet price
- 🎯 **Create 6-10 new orders** at mainnet price (tighter spreads 0.1%-1%)
- 🎯 **Larger order sizes** (50%-100% of base) for market impact
- 🎯 **Goal:** Move price towards mainnet without flooding book

**Why:** Book exists but price is wrong - need to shift liquidity, not add more

### Phase 2: ORDERBOOK BUILDING (Depth Poor)
**When orderbook has <50 total orders OR <20 near mainnet price:**
- 📖 **Creates beautiful staircase orderbook** with 28 orders (14 levels × 2 sides)
- 📖 Smooth progression from tight to wide spreads
- 📖 Uses mainnet price as the center
- 📖 Natural size variation (±10%)
- 📖 Smart price rounding based on price level

**Spread Distribution:**
- Tight levels (0.01% - 0.1%): 5 levels
- Medium levels (0.1% - 0.5%): 5 levels  
- Wide levels (0.5% - 2%): 4 levels

**Why:** Book is empty/sparse - need to build depth from scratch

### Phase 3: MAINTENANCE (Price Aligned, Depth Good)
**When price gap ≤2% AND orderbook has good depth:**
- 🔄 **Gradual orderbook updates** with depth stages
- 🔄 Adds 5-8 small orders per side (10-16 total)
- 🔄 Cancels 4-6 old orders to keep orderbook fresh
- 🔄 Cycles through depth stages (0.5%-1.5%, 1.5%-3%, 3%-5%, 5%-8%)
- 🔄 Smaller order sizes (20%-50% of base) for organic look

**Why:** Everything is good - just maintain and refresh liquidity

## 📊 Features

### Beautiful Orderbook Creation
✅ **28 orders** in full build mode (vs 6-12 basic)
✅ **Smooth staircase depth** - tight near center, wider farther out
✅ **Natural randomization** - looks like real traders, not bots
✅ **Progressive sizing** - smaller tight, larger deep
✅ **Smart price rounding** - based on price level

### Intelligent Management
✅ **Sequence management** - automatic recovery from sequence errors
✅ **Circuit breaker** - pauses trading after consecutive errors
✅ **Proactive sequence refresh** - every 30 seconds
✅ **Batch transactions** - create + cancel in single TX
✅ **Market selection** - run all or specific markets

### Price Discovery
✅ **Mainnet price tracking** - uses mainnet as price reference
✅ **Testnet price monitoring** - tracks current testnet state
✅ **Automatic strategy selection** - based on price gap
✅ **Last trade price** - prefers actual trades over orderbook

## 🔧 Configuration

Markets are configured in `config/markets_config.json`:

```json
{
  "markets": {
    "INJ/USDT": {
      "testnet_market_id": "0x0611780ba69656949525013d947713300f56c37b6175e02f26bffa495c3208fe",
      "mainnet_market_id": "0xa508cb32923323679f29a032c70342c147c17d0145625922b0ef22e955c844c0",
      "enabled": true,
      "type": "spot",
      "spread_percent": 0.5,
      "order_size": 15
    },
    "stINJ/INJ": {
      "testnet_market_id": "0xf02752c2c87728af7fd10a298a8a645261859eafd0295dcda7e2c5b45c8412cf",
      "mainnet_market_id": "0xce1829d4942ed939580e72e66fd8be3502396fc840b6d12b2d676bdb86542363",
      "enabled": true,
      "type": "spot",
      "spread_percent": 0.3,
      "order_size": 10
    }
  }
}
```

**Key Parameters:**
- `enabled`: Must be `true` for market to be traded
- `type`: Must be `"spot"` (derivative markets are ignored)
- `order_size`: Base order size for the market
- `spread_percent`: Base spread (used in config, but strategy is dynamic)

## 📝 Usage Examples

### Example 1: Build liquidity on all spot markets
```bash
python spot_trader.py wallet1
```
**Output (Empty Orderbook):**
```
[wallet1] 🚀 Initializing Enhanced Spot Trader for wallet1
[wallet1] ✅ Enhanced Spot Trader initialized for all enabled spot markets
[wallet1] 🎯 Processing 2 spot markets
[wallet1] 💰 INJ/USDT | Mainnet: $24.5623 | Testnet: $22.1043 | Diff: 10.01%
[wallet1] 📊 Orderbook: 8 total orders, 2 near price
[wallet1] 🏗️ ORDERBOOK BUILDING: Low depth (8 orders), building at mainnet $24.5623
[wallet1] 📖 Created beautiful orderbook with 28 staircase levels
[wallet1] ✅ Placed 28 orders | TX: 0x123...
```

**Output (Orderbook Exists, Wrong Price):**
```
[wallet1] 🎯 Processing 1 spot markets
[wallet1] 💰 INJ/USDT | Mainnet: $24.5623 | Testnet: $22.1043 | Diff: 10.01%
[wallet1] 📊 Orderbook: 78 total orders, 12 near price
[wallet1] 🎯 MARKET MOVING: Gap 10.01%, depth exists but price wrong
[wallet1] 🔄 Market moving: creating 8 orders, canceling 10
[wallet1] 🎯 Created 8 market moving orders at mainnet price $24.5623
[wallet1] ✅ Placed 8 orders, cancelled 10 | TX: 0x456...
```

### Example 2: Focus on INJ/USDT only
```bash
python spot_trader.py wallet1 INJ/USDT
```
**Output:**
```
[wallet1] ✅ Enhanced Spot Trader initialized for market: INJ/USDT
[wallet1] 🎯 Processing 1 spot markets
[wallet1] 💰 INJ/USDT | Mainnet: $24.5623 | Testnet: $24.4891 | Diff: 0.30%
[wallet1] 🔄 Gradual orderbook building (gap: 0.30%) - adding orders per side
[wallet1] 📏 Depth stage 0: spread range 0.5%-1.5%
[wallet1] 📝 Created 14 gradual orders (7 buys + 7 sells)
[wallet1] 📋 Found 23 open orders, selecting 5 to cancel
[wallet1] 🗑️ Selected 5 orders for cancellation
[wallet1] ✅ Placed 14 orders, cancelled 5 | TX: 0x456...
```

### Example 3: Multiple wallets (run in separate terminals)
```bash
# Terminal 1
python spot_trader.py wallet1 INJ/USDT

# Terminal 2  
python spot_trader.py wallet2 INJ/USDT

# Terminal 3
python spot_trader.py wallet3 stINJ/INJ
```

## 📈 Expected Results

### Before (Basic Trader)
- ❌ 6-12 sparse orders
- ❌ Obvious gaps (1.67%+)
- ❌ Bot-like patterns
- ❌ Poor depth

### After (Enhanced Trader)
- ✅ 28-50+ natural orders
- ✅ Smooth continuous depth
- ✅ Human-like randomization
- ✅ Professional trading experience

### Orderbook Visualization
```
Price      Size     Total      Tier
24.5654    16.3     400.52     ← Tight (0.01%)
24.5623    19.8     486.34     ← Tight
24.5592    15.7     385.58     ← Tight
24.5561    21.4     525.50     ← Tight
24.5530    18.2     446.86     ← Tight

24.5499    23.6     579.38     ← Medium (0.1%)
24.5468    27.1     665.22     ← Medium
24.5437    22.9     562.05     ← Medium
24.5406    25.8     633.15     ← Medium
24.5375    20.4     500.57     ← Medium

--- CURRENT PRICE: $24.5623 (MAINNET) ---

24.5685    24.7     606.84     ← Medium (0.1%)
24.5716    28.3     695.38     ← Medium
24.5747    23.1     567.68     ← Medium
...
```

## 🔍 Monitoring

### Log Files
Logs are saved to: `logs/spot_trader.log`

### Trading Summary
Press `Ctrl+C` to stop and see summary:
```
============================================================
📊 ENHANCED SPOT TRADING SUMMARY - WALLET1
============================================================
⏱️  Runtime: 01:23:45
📦 Total Orders: 342
✅ Successful: 338
❌ Failed: 4
🔄 Total Transactions: 24
⚠️  Sequence Errors: 2

📈 Per Market:
  INJ/USDT: 220 orders, 16 transactions
  stINJ/INJ: 118 orders, 8 transactions
============================================================
```

## ⚙️ Advanced Configuration

### Adjust Depth Stages
Edit `spot_trader.py` line ~345:
```python
spread_ranges = [
    (0.005, 0.015),  # Stage 0: 0.5%-1.5% (tight)
    (0.015, 0.03),   # Stage 1: 1.5%-3% (medium)
    (0.03, 0.05),    # Stage 2: 3%-5% (wide)
    (0.05, 0.08),    # Stage 3: 5%-8% (deep)
]
```

### Adjust Price Gap Threshold
Edit `spot_trader.py` line ~290:
```python
is_aligned = price_gap_percent <= 2.0  # Change threshold here
```

### Adjust Order Count
Edit `spot_trader.py` line ~353:
```python
num_orders_per_side = random.randint(5, 8)  # Change range here
```

## 🆚 vs Other Traders

| Feature | trader.py | derivative_trader.py | spot_trader.py |
|---------|-----------|---------------------|----------------|
| **Markets** | Spot + Derivative | Derivative only | Spot only |
| **Strategy** | Basic fixed spread | Enhanced 2-phase | Enhanced 2-phase |
| **Orderbook** | 6-12 orders | 28-50 orders | 28-50 orders |
| **Price Logic** | Mainnet reference | Testnet → Mainnet | Testnet → Mainnet |
| **Order Refresh** | Replace all | Gradual update | Gradual update |
| **Depth Building** | None | 4 stages | 4 stages |

## 🔧 Troubleshooting

### No orders placed
- Check if market is enabled in `markets_config.json`
- Check if market type is `"spot"`
- Verify mainnet price is available

### Sequence errors
- Script has built-in circuit breaker
- Automatically refreshes sequence
- Pauses and recovers after 3 consecutive errors

### Orders not showing
- Check subaccount balance
- Verify market_id is correct
- Check logs for error messages

## 🎯 Best Practices

1. **Start with one market** to test
2. **Monitor logs** for the first few cycles
3. **Use multiple wallets** for deeper liquidity
4. **Let it run** - orderbook builds over time
5. **Check testnet explorer** to verify orders

## 🚀 Production Deployment

For continuous operation:

```bash
# Using screen
screen -S spot-wallet1
python spot_trader.py wallet1
# Ctrl+A, D to detach

# Using nohup
nohup python spot_trader.py wallet1 > logs/spot_wallet1.log 2>&1 &

# Using systemd (recommended)
# Create service file: /etc/systemd/system/spot-trader-wallet1.service
```

---

**Happy orderbook building! 🎨**
