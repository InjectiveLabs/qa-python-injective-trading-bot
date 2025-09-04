# Configuration Files

This directory contains all configuration files for the Injective Multi-Wallet Trading Bot.

## Files

### `wallets_config.json`
Configuration for trading wallets including private keys and wallet IDs.

**Structure:**
```json
{
  "wallets": [
    {
      "id": "wallet_1",
      "private_key": "your_private_key_here",
      "enabled": true
    }
  ]
}
```

**⚠️ Security Note:** Never commit private keys to version control. Use environment variables or secure key management.

### `markets_config.json`
Configuration for trading markets including market IDs and trading parameters.

**Structure:**
```json
{
  "markets": {
    "INJ/USDT": {
      "market_id": "0x0611780ba69656949525013d947713300f56c37b6175e02f26bffa495c3208fe",
      "enabled": true,
      "type": "spot"
    }
  }
}
```

## Usage

The scripts automatically load these configuration files from the `config/` directory:

- `scripts/multi_wallet_trader.py` - Loads both config files
- `scripts/batch_cancel_orders.py` - Loads both config files

## Environment Variables

You can override config file paths using environment variables:

```bash
export WALLETS_CONFIG_PATH="path/to/custom/wallets_config.json"
export MARKETS_CONFIG_PATH="path/to/custom/markets_config.json"
```

## Backup

Always keep backups of your configuration files, especially before making changes.
