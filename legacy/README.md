# Legacy Files

This folder contains files that were moved here during project cleanup. These files are kept for reference but are no longer actively used.

## Files Moved Here:

### Redundant Runner Scripts:
- `run_simple_market_maker.py` - Simple market maker runner (redundant)
- `run_multi_wallet_market_maker.py` - Multi-wallet runner (redundant)
- `run_market_maker.py` - Market maker runner (redundant)
- `run_bot.py` - Bot runner (redundant)

### Redundant Cancel Scripts:
- `cancel_all_orders.py` - Cancel orders script (redundant - batch_cancel_orders.py is better)
- `simple_cancel.py` - Simple cancel script (redundant)

### Test Files:
- `simple_trade_test.py` - Test file for simple trading
- `check_order_states.py` - Order state checking utility

## Why These Were Moved:

1. **Redundancy**: Multiple scripts doing the same thing
2. **Better Alternatives**: `multi_wallet_trader.py` and `batch_cancel_orders.py` are superior
3. **Test Files**: Not needed for production use
4. **Cleaner Structure**: Main directory now focuses on active, working code

## Current Active Files:

- `multi_wallet_trader.py` - Main CLI trading system
- `batch_cancel_orders.py` - Order cancellation utility
- `main.py` - Web UI entry point
- All infrastructure in `core/`, `strategies/`, `api/`, `ui/` directories

## If You Need These Files:

These files are preserved here in case you need to reference the old implementations or restore functionality. However, the current system in the main directory is more robust and feature-complete.
