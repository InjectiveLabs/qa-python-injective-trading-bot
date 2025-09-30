# 🏥 Injective Network Health Checker

Quick diagnostic tool to check all Injective APIs and services.

## 🚀 Usage

```bash
# Activate virtual environment first
source venv/bin/activate  # or on Windows: venv\Scripts\activate

# Check testnet (default)
python utils/health_checker.py

# Check mainnet
python utils/health_checker.py --network mainnet

# Check with specific wallet
python utils/health_checker.py --wallet inj1youraddress...
```

## 📊 What It Tests

### 1. Chain API (LCD/REST)
Cosmos SDK standard endpoints:
- **Syncing Status**: Is the node syncing?
- **Node Info**: Network ID and version
- **Latest Block**: Current block height

### 2. Chain gRPC
Direct chain queries:
- **Account Query**: Can we fetch account data?

### 3. Indexer API (gRPC-Web) ⭐ MOST IMPORTANT
Market data and trading:
- **Spot Markets**: Can we fetch market list?
- **Derivative Markets**: Can we fetch perp markets?
- **Orderbook**: Can we get order depths?
- **Recent Trades**: Can we fetch trade history?

### 4. Wallet Connection (Optional)
If wallet address provided:
- **Bank Balances**: Can we fetch balances?

## 🎨 Output Format

```
✅ Service Name                  [OK] (123ms) - Details
❌ Service Name                  [FAIL] - Error message
⚠️ Service Name                  [WARN] - Warning message
```

## 🔍 Interpreting Results

### All Green ✅
Everything working perfectly! Your trading bot should work fine.

### Indexer API Red ❌
**Most Critical!** Your bot won't work properly:
- Can't fetch orderbooks
- Can't get market prices
- Can't see trades

**Solution:** 
1. Wait 5-10 minutes and retry
2. Check https://status.injective.network
3. If persistent, use mainnet instead

### Chain gRPC Red ❌
**Critical for trading!** Can't broadcast transactions.

**Solution:**
1. Check your internet connection
2. Try different network endpoint
3. Wait and retry

### LCD API Red ❌
**Not critical** for trading. Bot still works fine.

This is just for chain queries, not needed for trading operations.

## 🛠️ Common Error Codes

### 503 Service Unavailable
- Indexer is down or overloaded
- Usually temporary (5-10 minutes)
- Check again later

### Timeout
- Network congestion
- Slow connection
- Service under heavy load

### Connection Refused
- Service is down
- Wrong endpoint URL
- Firewall blocking

## 📝 Examples

### Example 1: Everything Working
```
✅ Spot Markets                  [OK] (123ms) - 204 markets found
✅ Orderbook (INJ/USDT)          [OK] (89ms) - 45 bids, 52 asks
```
**Meaning:** All systems operational, safe to trade!

### Example 2: Indexer Down
```
❌ Spot Markets                  [FAIL] - 503 Service Unavailable
❌ Orderbook (INJ/USDT)          [FAIL] - 503 Service Unavailable
```
**Meaning:** Indexer is down. Wait 10 minutes and retry.

### Example 3: Network Issues
```
❌ Spot Markets                  [FAIL] - Timeout after 15s
❌ Derivative Markets            [FAIL] - Timeout after 15s
```
**Meaning:** Network problems. Check your internet connection.

## 🔗 Useful Links

- **Injective Docs**: https://docs.injective.network/
- **Network Status**: https://status.injective.network/
- **Explorer (Testnet)**: https://testnet.explorer.injective.network/
- **Explorer (Mainnet)**: https://explorer.injective.network/

## 💡 Pro Tips

1. **Run before trading** - Always check health before starting your bot
2. **Bookmark it** - Keep this tool handy for quick diagnostics
3. **Check both networks** - If testnet is down, try mainnet
4. **Save output** - Redirect to file for support tickets:
   ```bash
   python utils/health_checker.py > health_report.txt
   ```

## 🐛 Troubleshooting

**Q: All services show FAIL**
- Check internet connection
- Try VPN if firewall blocking
- Verify DNS resolution

**Q: Only Indexer shows FAIL** 
- Most common issue
- Wait 5-10 minutes
- Check status.injective.network

**Q: Bot was working, now shows errors**
- Run health checker first
- Identify which service is down
- Wait for service recovery or switch networks

---

**Made with ❤️ for the Injective community**
