# Configuration Guide

This directory contains configuration files for the Injective Trading Bot system.

## 📁 Configuration Files

### `trader_config.json` (Primary Configuration)

The main configuration file containing market definitions, trading parameters, and wallet assignments.

**Location**: `config/trader_config.json`

#### Structure

```json
{
  "mode": "single_wallet",
  "wallets": {
    "wallet_1": {
      "markets": ["INJ/USDT", "stINJ/INJ", "INJ/USDT-PERP"],
      "trading_params": {
        "spread_percent": 0.5,
        "order_size": 15,
        "orders_per_market": 3
      }
    },
    "wallet_2": {
      "markets": ["INJ/USDT", "stINJ/INJ"],
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
      "order_size": 15,
      "min_spread": 0.1,
      "max_spread": 2.0,
      "price_correction": {
        "enabled": true,
        "deviation_threshold": 5.0,
        "correction_aggressiveness": 0.8,
        "max_correction_size": 150,
        "correction_cooldown": 300
      }
    },
    "INJ/USDT-PERP": {
      "testnet_market_id": "0x17ef48032cb24375ba7c2e39f384e56433bcab20cbee9a7357e4cba2eb00abe6",
      "mainnet_market_id": "0x9b9980167ecc3645ff1a5517886652d94a0825e54a77d2057cbbe3ebee015963",
      "type": "derivative",
      "spread_percent": 0.3,
      "order_size": 8,
      "min_spread": 0.05,
      "max_spread": 1.5,
      "price_correction": {
        "enabled": true,
        "deviation_threshold": 3.0,
        "correction_aggressiveness": 0.6,
        "max_correction_size": 80,
        "correction_cooldown": 180
      }
    }
  },
  "global": {
    "rebalance_interval": 30,
    "price_update_interval": 10,
    "price_monitoring_interval": 5,
    "ui_port": 8080,
    "api_port": 8000
  }
}
```

#### Configuration Sections

##### 1. Mode
```json
"mode": "single_wallet"
```
- **Purpose**: Indicates bot operation mode
- **Current**: `single_wallet` (each bot instance manages one wallet)
- **Legacy**: `multi_wallet` (no longer supported)

##### 2. Wallets
```json
"wallets": {
  "wallet_1": {
    "markets": ["INJ/USDT", "stINJ/INJ", "INJ/USDT-PERP"],
    "trading_params": {
      "spread_percent": 0.5,
      "order_size": 15,
      "orders_per_market": 3
    }
  }
}
```

**Fields**:
- `markets`: Array of market symbols this wallet will trade
- `trading_params`: Default parameters for this wallet
  - `spread_percent`: Base spread percentage
  - `order_size`: Base order size
  - `orders_per_market`: Number of orders per market (legacy, not used in enhanced traders)

##### 3. Markets
```json
"markets": {
  "INJ/USDT": {
    "testnet_market_id": "0x...",
    "mainnet_market_id": "0x...",
    "type": "spot",
    "spread_percent": 0.5,
    "order_size": 15,
    "min_spread": 0.1,
    "max_spread": 2.0,
    "price_correction": {...}
  }
}
```

**Required Fields**:
- `testnet_market_id`: Market ID on Injective testnet (where orders are placed)
- `mainnet_market_id`: Market ID on Injective mainnet (for price reference)
- `type`: Market type - `"spot"` or `"derivative"`

**Trading Parameters**:
- `spread_percent`: Base spread for orders (percentage)
- `order_size`: Base order size
- `min_spread`: Minimum spread percentage
- `max_spread`: Maximum spread percentage

**Price Correction** (optional):
- `enabled`: Enable price correction for this market
- `deviation_threshold`: Price gap % that triggers correction
- `correction_aggressiveness`: How aggressive corrections are (0.0-1.0)
- `max_correction_size`: Maximum order size for corrections
- `correction_cooldown`: Seconds between corrections

##### 4. Global Settings
```json
"global": {
  "rebalance_interval": 30,
  "price_update_interval": 10,
  "price_monitoring_interval": 5,
  "ui_port": 8080,
  "api_port": 8000
}
```

- `rebalance_interval`: Seconds between rebalance operations
- `price_update_interval`: Seconds between price updates
- `price_monitoring_interval`: Seconds between price checks
- `ui_port`: Port for web UI (legacy)
- `api_port`: Port for API server

### `.env` (Wallet Private Keys)

**⚠️ CRITICAL: This file contains private keys and must NEVER be committed to version control.**

**Location**: Project root (`.env`)

#### Structure

```bash
# Wallet 1 - Primary Market Maker
WALLET_1_PRIVATE_KEY=0x1234567890abcdef...
WALLET_1_NAME=Primary Market Maker
WALLET_1_ENABLED=true
WALLET_1_MAX_ORDERS=50
WALLET_1_BALANCE_THRESHOLD=100

# Wallet 2 - QA Market Maker
WALLET_2_PRIVATE_KEY=0xabcdef1234567890...
WALLET_2_NAME=QA Market Maker
WALLET_2_ENABLED=true
WALLET_2_MAX_ORDERS=50
WALLET_2_BALANCE_THRESHOLD=100

# Wallet 3 - QA Market Taker
WALLET_3_PRIVATE_KEY=0x567890abcdef1234...
WALLET_3_NAME=QA Market Taker
WALLET_3_ENABLED=true
WALLET_3_MAX_ORDERS=50
WALLET_3_BALANCE_THRESHOLD=100
```

#### Environment Variables

**Per Wallet** (replace `X` with wallet number):

- `WALLET_X_PRIVATE_KEY` (required): Injective wallet private key (hex string starting with 0x)
- `WALLET_X_NAME` (optional): Human-readable wallet name
- `WALLET_X_ENABLED` (optional): `true` or `false` - whether wallet is active
- `WALLET_X_MAX_ORDERS` (optional): Maximum number of open orders
- `WALLET_X_BALANCE_THRESHOLD` (optional): Minimum balance threshold for warnings

#### Security Best Practices

1. **Never commit `.env` to git**
   - Verify `.env` is in `.gitignore`
   - Use `env.example` as a template

2. **Use testnet keys only**
   - Never use mainnet private keys in testnet config
   - Testnet keys control testnet tokens (no real value)

3. **Restrict file permissions**
   ```bash
   chmod 600 .env  # Read/write for owner only
   ```

4. **Keep backups secure**
   - Store private keys in secure password manager
   - Never share keys via email/chat

### `markets_config.json` (Deprecated)

**Status**: Deprecated, kept for backwards compatibility

Some older scripts may reference this file. New implementations should use `trader_config.json` instead.

## 🔧 Configuration Usage

### How Bots Load Configuration

#### Derivative Trader
```python
# Loads trader_config.json for markets
trader = SingleWalletTrader(
    wallet_id="wallet_1",
    config_path="config/trader_config.json"
)

# Loads .env for private key
wallets_config = load_wallets_from_env()
```

#### Spot Trader
```python
# Loads trader_config.json for markets
trader = EnhancedSpotTrader(
    wallet_id="wallet1",
    config_path="config/trader_config.json"
)

# Loads .env for private key
wallets_config = load_wallets_from_env()
```

### Configuration Precedence

When values are specified in multiple places, the precedence is:

1. **Market-specific settings** in `trader_config.json` → `markets` section
2. **Wallet-specific settings** in `trader_config.json` → `wallets` section
3. **Global settings** in `trader_config.json` → `global` section
4. **Default hardcoded values** in bot code

Example:
```json
// Market-specific order_size overrides wallet default
"markets": {
  "INJ/USDT": {
    "order_size": 15  // ← This wins
  }
},
"wallets": {
  "wallet_1": {
    "trading_params": {
      "order_size": 10  // ← This is ignored for INJ/USDT
    }
  }
}
```

## 📊 Common Configuration Scenarios

### Scenario 1: Single Wallet, All Markets

```json
{
  "wallets": {
    "wallet_1": {
      "markets": ["INJ/USDT", "stINJ/INJ", "INJ/USDT-PERP"],
      "trading_params": {
        "spread_percent": 0.5,
        "order_size": 15
      }
    }
  }
}
```

**Launch**:
```bash
python derivative_trader.py wallet_1
python spot_trader.py wallet1
```

### Scenario 2: Multiple Wallets, Market Specialization

```json
{
  "wallets": {
    "wallet_1": {
      "markets": ["INJ/USDT-PERP"],  // Derivatives only
      "trading_params": {
        "spread_percent": 0.3,
        "order_size": 8
      }
    },
    "wallet_2": {
      "markets": ["INJ/USDT", "stINJ/INJ"],  // Spot only
      "trading_params": {
        "spread_percent": 0.5,
        "order_size": 15
      }
    }
  }
}
```

**Launch** (separate terminals):
```bash
# Terminal 1
python derivative_trader.py wallet_1

# Terminal 2
python spot_trader.py wallet2
```

### Scenario 3: Conservative Trading

```json
{
  "markets": {
    "INJ/USDT": {
      "type": "spot",
      "spread_percent": 1.0,          // Wider spreads
      "order_size": 5,                // Smaller sizes
      "min_spread": 0.5,
      "max_spread": 3.0,
      "price_correction": {
        "enabled": true,
        "deviation_threshold": 10.0,   // Only correct large gaps
        "correction_aggressiveness": 0.5,  // Less aggressive
        "max_correction_size": 50,     // Smaller corrections
        "correction_cooldown": 600     // Longer cooldown
      }
    }
  }
}
```

### Scenario 4: Aggressive Liquidity Building

```json
{
  "markets": {
    "INJ/USDT": {
      "type": "spot",
      "spread_percent": 0.2,          // Tighter spreads
      "order_size": 30,               // Larger sizes
      "min_spread": 0.05,
      "max_spread": 1.0,
      "price_correction": {
        "enabled": true,
        "deviation_threshold": 2.0,    // Correct small gaps
        "correction_aggressiveness": 0.9,  // Very aggressive
        "max_correction_size": 300,    // Large corrections
        "correction_cooldown": 120     // Short cooldown
      }
    }
  }
}
```

## 🔍 Configuration Validation

### Required Market Fields Checklist

For each market in `markets` section:
- [ ] `testnet_market_id` exists and is valid hex
- [ ] `mainnet_market_id` exists and is valid hex
- [ ] `type` is either `"spot"` or `"derivative"`
- [ ] `order_size` is positive number
- [ ] `spread_percent` is positive number

### Required Wallet Configuration Checklist

For each wallet you plan to use:
- [ ] Wallet ID in `trader_config.json` → `wallets` section
- [ ] `WALLET_X_PRIVATE_KEY` in `.env` file
- [ ] `WALLET_X_ENABLED=true` in `.env` file
- [ ] Private key is valid hex string (starts with 0x)
- [ ] Private key corresponds to funded testnet wallet

### Common Configuration Errors

**Error**: `Wallet wallet_1 not found in environment`
- **Cause**: Missing or disabled in `.env`
- **Fix**: Add `WALLET_1_ENABLED=true` to `.env`

**Error**: `Market INJ/USDT not found in config`
- **Cause**: Market not defined in `trader_config.json`
- **Fix**: Add market definition to `markets` section

**Error**: `Invalid market type: derivative for spot trader`
- **Cause**: Running spot trader on derivative market
- **Fix**: Use correct trader for market type

## 🛠️ Configuration Tools

### View Current Configuration
```bash
# View markets for a wallet
python derivative_trader.py wallet_1 --list-markets

# View wallet configuration
python -c "from utils.secure_wallet_loader import load_wallets_from_env; import json; print(json.dumps(load_wallets_from_env(), indent=2))"
```

### Validate Configuration
```bash
# Test wallet loading
python -c "from utils.secure_wallet_loader import load_wallets_from_env; wallets = load_wallets_from_env(); print(f'Loaded {len(wallets[\"wallets\"])} wallets')"

# Test market configuration
python -c "import json; config = json.load(open('config/trader_config.json')); print(f'Configured {len(config[\"markets\"])} markets')"
```

## 📝 Configuration Best Practices

1. **Start Conservative**
   - Small order sizes initially
   - Wider spreads until comfortable
   - Lower aggressiveness settings

2. **Test Single Market First**
   - Configure one market
   - Run bot on that market only
   - Monitor for 30-60 minutes
   - Scale up gradually

3. **Monitor Resource Usage**
   - More markets = more API calls
   - More wallets = more processes
   - Balance depth vs. system capacity

4. **Document Changes**
   - Comment configuration files
   - Note why specific values chosen
   - Track what works and what doesn't

5. **Version Control Configuration**
   - Commit `trader_config.json` (no secrets)
   - Never commit `.env` (contains secrets)
   - Use `env.example` as template

## 🔗 Related Documentation

- **[Main README](../README.md)** - Complete system overview
- **[Architecture](../ARCHITECTURE.md)** - System design details
- **[Spot Trader Guide](../docs/SPOT_TRADER_GUIDE.md)** - Spot trading specifics
- **[Utilities README](../utils/README.md)** - Helper tools

---

**Configuration is the key to effective liquidity provision. Start conservative, monitor closely, and scale gradually.**