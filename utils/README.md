# Unified Market Comparison Scripts

This directory contains scripts for comparing testnet and mainnet market data files for both spot and derivative markets.

## 🎯 **Why Unified?**

Instead of having separate scripts for spot and derivative markets, we now have **one smart script** that:
- **Automatically detects** whether you're comparing spot or derivative markets
- **Handles different data structures** automatically
- **Uses appropriate field comparisons** for each market type
- **Generates separate reports** for each market type

## 📁 **Files**

- `market_comparison_unified.py` - **Single script** that handles all market comparisons
- `README.md` - This documentation file

## 🚀 **Quick Start (Recommended)**

Compare both market types at once:

```bash
python3 utils/market_comparison_unified.py --compare-all
```

**Note**: The script now automatically looks for market data files in the `data/` directory.

This will:
- Automatically detect and compare **spot markets**
- Automatically detect and compare **derivative markets**
- Generate separate reports for each type
- Display progress and results

## 🔧 **Advanced Usage**

Use the main unified script directly for more control:

```bash
# Auto-detect market type and file paths
python3 utils/market_comparison_unified.py

# Specify custom file paths
python3 utils/market_comparison_unified.py --testnet data/testnet_spot_market_data.json --mainnet data/mainnet_spot_market_data.json

# Save output to a specific file
python3 utils/market_comparison_unified.py --output my_report.txt

# Get help
python3 utils/market_comparison_unified.py --help
```

## 🧠 **How It Works**

The unified script automatically:

1. **Detects Market Type**: Analyzes the JSON structure to determine if it's spot or derivative
2. **Selects Fields**: Chooses appropriate configuration fields to compare based on market type
3. **Handles Structure**: Manages different data layouts (nested vs flat)
4. **Generates Reports**: Creates market-type-specific reports with appropriate titles

## 📊 **What Gets Compared**

### **Spot Markets**
- `maker_fee_rate`, `taker_fee_rate`, `relayer_fee_share_rate`
- `status`, `min_price_tick_size`, `min_quantity_tick_size`
- `min_notional`, `admin`, `admin_permissions`
- `base_decimals`, `quote_decimals`

### **Derivative Markets**
- `oracle_type`, `oracle_scale_factor`
- `initial_margin_ratio`, `maintenance_margin_ratio`, `reduce_margin_ratio`
- `maker_fee_rate`, `taker_fee_rate`, `relayer_fee_share_rate`
- `status`, `min_price_tick_size`, `min_quantity_tick_size`
- `min_notional`, `admin`, `admin_permissions`, `quote_decimals`

**Note**: `market_id`, `base_denom`, `quote_denom`, `oracle_base`, and `oracle_quote` are excluded from comparison as they're always different between environments, but testnet market IDs are displayed for reference.

## 📈 **Output Format**

The script generates comprehensive reports showing:

1. **Summary** - Market type, total counts, and overview
2. **Common Markets** - Markets present in both environments with configuration differences
3. **Testnet-only Markets** - Markets unique to testnet
4. **Mainnet-only Markets** - Markets unique to mainnet
5. **Detailed Differences** - Side-by-side comparison of all configuration differences

## 🎯 **Example Output**

```
================================================================================
SPOT MARKET DATA COMPARISON REPORT
================================================================================

SUMMARY:
  Market Type: Spot
  Total markets in testnet: 185
  Total markets in mainnet: 132
  Common markets: 16
  Testnet-only markets: 169
  Mainnet-only markets: 116

INJ/USDT (Testnet Market ID: 0x1234567890abcdef...):
    maker_fee_rate:
      testnet: -0.000100000000000000
      mainnet: -0.000050000000000000
    min_notional:
      testnet: 0.000000000001000000
      mainnet: 1.000000000000000000
```

## 🔍 **Key Differences Found**

### **Spot Markets**
- **Quote Denominations**: Different USDT contract addresses between environments
- **Fee Rates**: Testnet has higher maker fee rates (-0.0001 vs -0.00005)
- **Trading Parameters**: Different minimum tick sizes, quantities, and notional values

### **Derivative Markets**
- **Margin Requirements**: Testnet has much higher margin ratios
- **Fee Structures**: Testnet has significantly higher fees
- **Oracle Types**: Testnet uses mixed oracle types, mainnet uses Pyth
- **Trading Parameters**: Different minimum notional and tick size requirements

## 🚀 **Benefits of Unified Approach**

1. **Single Script**: One script handles both market types
2. **Auto-Detection**: No need to specify market type manually
3. **Maintainable**: One codebase to maintain instead of four
4. **Consistent**: Same output format and logic for both types
5. **Extensible**: Easy to add new market types in the future

## 📋 **Requirements**

- Python 3.6+
- No external dependencies (uses only standard library)

## 🛠️ **Troubleshooting**

- **File not found errors**: Ensure the market data JSON files exist in the `data/` directory
- **JSON parsing errors**: Verify the JSON files are valid and not corrupted
- **Market type detection issues**: Check that the JSON structure follows the expected format
- **Permission errors**: Ensure you have read access to the market data files
