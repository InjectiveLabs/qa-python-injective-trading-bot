# Manual Order Canceller

This script allows you to cancel orders on demand for the Enhanced Multi-Wallet Trader.

## Usage Examples

### Cancel all orders for a specific wallet and market:
```bash
python scripts/manual_order_canceller.py --wallet wallet_1 --market INJ/USDT
```

### Cancel all orders for a specific wallet across all markets:
```bash
python scripts/manual_order_canceller.py --wallet wallet_1 --market all
```

### Cancel all orders for all wallets and all markets:
```bash
python scripts/manual_order_canceller.py --wallet all --market all
```

### Cancel orders for specific wallet and market:
```bash
python scripts/manual_order_canceller.py --wallet wallet_2 --market stINJ/INJ
```

## Available Wallets
- `wallet_1` - Primary Market Maker
- `wallet_2` - QA Market Maker  
- `wallet_3` - QA Market Taker
- `all` - All wallets

## Available Markets
- `INJ/USDT` - INJ/USDT spot market
- `stINJ/INJ` - stINJ/INJ spot market
- `all` - All enabled markets

## Features
- ✅ Cancels both spot and derivative orders
- ✅ Shows detailed cancellation summary
- ✅ Handles multiple wallets and markets
- ✅ Provides transaction hashes for verification
- ✅ Safe error handling and logging

## When to Use
- 🚨 Emergency order cancellation
- 🧪 Testing order management
- 🔄 Manual order refresh
- 🛑 Stopping specific wallet trading
- 🧹 Cleanup before maintenance

## Example Output
```
🚀 Starting manual cancellation for wallet_1
✅ Manual canceller initialized for wallet_1: inj1gy25maepd4nwwq5m0nud6jygvje4dm9rkcc57w
🔍 Checking active orders for INJ/USDT (0x0611780ba69656949525013d947713300f56c37b6175e02f26bffa495c3208fe)
📋 Found 5 active orders to cancel
✅ Successfully cancelled 5 orders for INJ/USDT
📝 Transaction: 0A23B12E6D0F392BE70866108CA1C906C94B00BDAB9C4E6AC56D8846A915D8A1
✅ Successfully processed INJ/USDT for wallet_1
🏁 Manual cancellation process completed
```
