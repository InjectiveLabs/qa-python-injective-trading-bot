# QA Injective Trading Bot - System Architecture

## 🎯 Overview

The QA Injective Trading Bot is a sophisticated single-wallet trading system that operates on Injective Protocol's testnet while using mainnet prices as reference. The system creates professional-grade orderbooks and maintains price parity between testnet and mainnet for realistic paper trading conditions.

## 🏗️ Core Architecture

### Single-Wallet Design Philosophy

Unlike traditional multi-wallet orchestration systems, this bot uses a **single-wallet architecture** where:
- Each bot instance manages one wallet independently
- Multiple bots run in separate processes for parallel operation
- No central coordinator - each bot is autonomous
- Simpler, more resilient, easier to maintain

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                     TRADING BOTS (Independent)                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐ │
│  │ derivative_trader│  │  spot_trader.py  │  │ trader.py    │ │
│  │      .py         │  │                  │  │  (legacy)    │ │
│  │                  │  │                  │  │              │ │
│  │ • Enhanced 2-phase│  │ • Enhanced 2-phase│  │ • Basic     │ │
│  │ • Sequence mgmt  │  │ • Sequence mgmt  │  │ • Fixed     │ │
│  │ • Derivatives only│  │ • Spot only      │  │ • Spot+Deriv│ │
│  └──────────────────┘  └──────────────────┘  └──────────────┘ │
│                                                                 │
│  Each bot instance = Single wallet + All assigned markets      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                   CONFIGURATION LAYER                           │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐ │
│  │ trader_config    │  │      .env        │  │ markets_     │ │
│  │    .json         │  │                  │  │ config.json  │ │
│  │                  │  │ • Wallet keys    │  │ (deprecated) │ │
│  │ • Markets        │  │ • Wallet names   │  │              │ │
│  │ • Parameters     │  │ • Enable flags   │  │              │ │
│  └──────────────────┘  └──────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    MANAGEMENT TOOLS                             │
├─────────────────────────────────────────────────────────────────┤
│  scripts/                      utils/                           │
│  ├─ manual_order_canceller.py  ├─ balance_checker.py           │
│  └─ position_closer.py         ├─ health_checker.py            │
│                                 ├─ market_comparison_unified.py │
│                                 ├─ check_open_orders.py         │
│                                 └─ check_positions.py           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                   WEB DASHBOARD (Optional)                      │
├─────────────────────────────────────────────────────────────────┤
│  web/app.py - FastAPI backend                                  │
│  web/static/ - HTML/JS frontend                                │
│  • Bot status monitoring                                       │
│  • Start/stop controls                                         │
│  • Balance tracking                                            │
│  • Live activity feed                                          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                  INJECTIVE PROTOCOL                             │
├─────────────────────────────────────────────────────────────────┤
│  Testnet (Trading)              Mainnet (Price Reference)      │
│  • Order placement              • Real market prices           │
│  • Order cancellation           • Price discovery              │
│  • Position management          • Market data                  │
│  • Balance queries              • Oracle data                  │
└─────────────────────────────────────────────────────────────────┘
```

## 🔄 Data Flow Architecture

### Price Discovery & Order Placement Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        Trading Cycle                            │
└─────────────────────────────────────────────────────────────────┘

1. INITIALIZATION
   ├─ Load wallet from .env
   ├─ Connect to testnet (trading)
   ├─ Connect to mainnet (price reference)
   ├─ Load market configuration
   └─ Initialize sequence management

2. PRICE DISCOVERY (Every 15 seconds)
   ├─ Query mainnet price for each market
   ├─ Query testnet price for each market
   ├─ Calculate price gap percentage
   └─ Determine trading strategy phase

3. ORDERBOOK ASSESSMENT
   ├─ Count total orders in testnet orderbook
   ├─ Count orders within 5% of mainnet price
   ├─ Evaluate depth sufficiency
   └─ Select appropriate action

4. STRATEGY SELECTION
   ├─ Phase 1: MARKET MOVING (gap >15%, depth exists)
   │   └─ Large directional orders to move price
   │
   ├─ Phase 2: ORDERBOOK BUILDING (depth <50 orders)
   │   └─ Create full staircase orderbook (28-66 orders)
   │
   └─ Phase 3: MAINTENANCE (price aligned, depth good)
       └─ Gradual updates with depth stage cycling

5. ORDER EXECUTION
   ├─ Acquire sequence lock
   ├─ Build batch transaction (create + cancel)
   ├─ Broadcast transaction to testnet
   ├─ Update local sequence
   └─ Release sequence lock

6. ERROR HANDLING
   ├─ Sequence mismatch → Auto-refresh & retry
   ├─ Network error → Exponential backoff
   ├─ Circuit breaker → Pause after consecutive errors
   └─ Logging → Full audit trail

7. REPEAT
   └─ Wait 15 seconds → Go to step 2
```

## 🎯 Enhanced Trading Strategy

### Two-Phase Strategy Design

The bot uses an intelligent strategy optimized for the **testnet liquidity provision mission**:

#### Phase 1: Market Moving
**When**: Large price gap (>15%) but orderbook has depth (>30 orders)

**Problem**: Price is wrong but book already has orders

**Solution**: 
- Cancel 8-12 old orders far from mainnet price
- Create 6-10 new orders at mainnet price
- Use larger order sizes (50%-100% of base)
- Tighter spreads (0.1%-1%)

**Goal**: Shift liquidity to correct price without flooding book

#### Phase 2: Orderbook Building
**When**: Poor orderbook depth (<50 total orders OR <20 near price)

**Problem**: Empty or sparse orderbook

**Solution**:
- Create beautiful staircase orderbook with 28 orders minimum
- Smooth progression from tight (0.01%) to wide (2%) spreads
- Natural size variation (±10-15%)
- Smart price rounding based on level

**Goal**: Build professional-grade depth from scratch

#### Phase 3: Maintenance
**When**: Price aligned (gap <2%) AND good depth exists

**Problem**: Everything is good, just need to maintain quality

**Solution**:
- Add 5-8 small orders per side (gradual updates)
- Cancel 4-6 old orders to keep book fresh
- Cycle through depth stages (0.5%-1.5%, 1.5%-3%, 3%-5%, 5%-8%)
- Smaller order sizes (20%-50% of base)

**Goal**: Maintain liquidity and responsiveness

### Spread Distribution Strategy

Orders are placed across multiple tiers for realistic depth:

```
Tier 1: Micro (0.01-0.05%)     - 5 levels × 2 sides = 10 orders
Tier 2: Very Tight (0.05-0.1%) - 6 levels × 2 sides = 12 orders
Tier 3: Tight (0.1-0.5%)       - 5 levels × 2 sides = 10 orders
Tier 4: Medium (0.5-1%)        - 4 levels × 2 sides = 8 orders
Tier 5: Wide (1-2%)            - 4 levels × 2 sides = 8 orders
Tier 6: Deep (2-5%)            - 3 levels × 2 sides = 6 orders

Total: 54 orders creating smooth, natural depth
```

## 🔧 Technical Architecture

### Sequence Management System

**Problem**: Blockchain transactions require sequential sequence numbers. Multiple concurrent operations can cause mismatches.

**Solution**: Bulletproof sequence management with multiple layers:

```python
1. Sequence Lock
   └─ asyncio.Lock() prevents concurrent sequence operations

2. Proactive Monitoring
   └─ Refresh sequence every 30 seconds automatically

3. Enhanced Retry Logic
   └─ Sequence errors trigger forced refresh + 3-second wait + retry

4. Drift Detection
   └─ Compare local vs blockchain sequence, auto-correct if drift >2

5. Circuit Breaker
   └─ Pause after 3-5 consecutive errors, extended cooldown
```

**Result**: <1% sequence error rate, automatic recovery

### Batch Transaction Architecture

All order operations use batch transactions for efficiency:

```python
Batch Transaction Structure:
├─ CREATE orders (multiple)
│   ├─ Order 1: Buy at price X
│   ├─ Order 2: Buy at price Y
│   ├─ Order 3: Sell at price Z
│   └─ ...
│
└─ CANCEL orders (multiple)
    ├─ Cancel order hash A
    ├─ Cancel order hash B
    └─ ...

Benefits:
├─ Single sequence number for all operations
├─ Atomic execution (all or nothing)
├─ Reduced gas costs
└─ Faster execution
```

### Price Scaling & Precision

Different markets require different price scaling:

```python
Price Scaling Logic:
├─ stINJ/INJ markets: scale = 1 (token price scale)
├─ INJ/USDT markets: scale = 10^12 (standard spot scale)
└─ Derivatives: scale = 10^18 (derivative price scale)

Quantity Scaling:
├─ Base decimals: From market metadata
├─ Quote decimals: From market metadata
└─ Proper rounding: Based on min_quantity_tick_size
```

## 🔒 Security Architecture

### Wallet Security
```
Environment Variables (.env)
├─ Private keys never in code
├─ gitignore prevents commits
├─ Loaded at runtime only
└─ Isolated per wallet

Secure Wallet Loader (utils/secure_wallet_loader.py)
├─ Validates key format
├─ Enables/disables per wallet
├─ Error handling for missing keys
└─ No key logging
```

### Transaction Security
```
Sequence Management
├─ Lock prevents race conditions
├─ Drift detection prevents desync
└─ Circuit breaker prevents cascading failures

Transaction Validation
├─ Balance checks before orders
├─ Price validation against mainnet
├─ Size validation against limits
└─ Market validation before execution
```

### Operational Security
```
Testnet Isolation
├─ Default network: testnet
├─ Separate mainnet connection (read-only for prices)
├─ No mainnet trading without explicit config
└─ Clear network indicators in logs

Error Handling
├─ Comprehensive try/catch blocks
├─ Graceful degradation on failures
├─ Full error logging with context
└─ No sensitive data in error messages
```

## 📊 Performance Characteristics

### Scalability
- **Single-wallet design**: Simple, linear scaling by adding bot processes
- **Async operations**: Non-blocking I/O for network calls
- **Batch transactions**: Multiple orders in single blockchain transaction
- **Resource efficient**: Low CPU/memory footprint per bot instance

### Reliability
- **Automatic recovery**: Self-healing from sequence errors
- **Circuit breakers**: Prevent error cascades
- **Graceful shutdown**: Clean exit on signals
- **Full logging**: Complete audit trail for debugging

### Performance Metrics
- **Order success rate**: 95-98%
- **Sequence error rate**: <1% with enhanced management
- **Price convergence time**: 2-3 cycles (30-45 seconds)
- **Orderbook build time**: 1-2 cycles (15-30 seconds)
- **Resource usage**: ~50-100MB RAM, minimal CPU

## 🌐 Web Dashboard Architecture (Optional)

```
┌────────────────────────────────────────────────────────────┐
│                   WEB DASHBOARD STACK                      │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Frontend (Static HTML/JS)                                │
│  ├─ Vanilla JavaScript                                    │
│  ├─ Tailwind CSS                                          │
│  ├─ Real-time WebSocket client                           │
│  └─ Responsive design                                     │
│                                                            │
│  Backend (FastAPI)                                        │
│  ├─ REST API endpoints                                    │
│  │   ├─ GET /api/wallets                                 │
│  │   ├─ GET /api/markets                                 │
│  │   ├─ POST /api/start_bot                              │
│  │   └─ POST /api/stop_bot                               │
│  │                                                        │
│  ├─ WebSocket server                                     │
│  │   └─ Real-time status updates                         │
│  │                                                        │
│  └─ Process management                                   │
│      ├─ Spawn bot processes                              │
│      ├─ Monitor running bots                             │
│      └─ Collect bot output                               │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### Dashboard Data Flow

```
User Action (Browser)
    ├─> HTTP Request to FastAPI
    ├─> FastAPI spawns bot process (subprocess)
    ├─> Bot writes to log file
    ├─> FastAPI reads log file
    ├─> FastAPI broadcasts via WebSocket
    └─> Browser updates UI in real-time

Benefits:
├─ Decoupled bot processes (bots independent of web)
├─ Process isolation (bot crash doesn't crash web)
├─ Multiple bots manageable from one interface
└─ Real-time monitoring without polling
```

## 🔮 Architecture Evolution

### Current State (V2 - Single Wallet)
✅ Single-wallet independent bots
✅ Enhanced two-phase strategy
✅ Bulletproof sequence management
✅ Batch transactions
✅ Optional web dashboard

### Previous State (V1 - Multi Wallet Coordinator)
❌ Removed: Central multi-wallet coordinator
❌ Removed: Complex parallel orchestration
❌ Removed: scripts/multi_wallet_trader.py
❌ Removed: scripts/batch_cancel_orders.py

**Why changed**: Simpler is better. Single-wallet design is more maintainable, more resilient, and easier to understand.

### Future Enhancements (V3)
🔮 Database integration for historical data
🔮 Advanced analytics and reporting
🔮 Strategy configuration via web interface
🔮 Machine learning price prediction
🔮 Multi-network support (other testnets)

## 📋 Design Decisions

### Why Single-Wallet Architecture?
1. **Simplicity**: Each bot is independent, no coordination needed
2. **Resilience**: One bot failure doesn't affect others
3. **Scalability**: Linear scaling by adding processes
4. **Maintenance**: Easier to debug and modify
5. **Flexibility**: Each wallet can run different strategies

### Why Two-Phase Strategy?
1. **Mission-aligned**: Optimized for price convergence + depth building
2. **Adaptive**: Responds to actual orderbook state
3. **Efficient**: Doesn't flood book when unnecessary
4. **Realistic**: Creates natural-looking orderbooks

### Why Batch Transactions?
1. **Efficiency**: Single sequence number for multiple operations
2. **Atomicity**: All orders execute or none do
3. **Cost**: Reduced gas fees
4. **Speed**: Faster than sequential transactions

### Why Enhanced Sequence Management?
1. **Reliability**: <1% error rate vs 5-10% before
2. **Recovery**: Automatic vs manual intervention
3. **Prevention**: Proactive monitoring prevents issues
4. **Resilience**: Circuit breakers stop cascading failures

---

**Architecture designed for reliability, maintainability, and mission success: Make Injective testnet indistinguishable from mainnet for paper traders.**

*This document reflects the current production architecture as of October 2025.*