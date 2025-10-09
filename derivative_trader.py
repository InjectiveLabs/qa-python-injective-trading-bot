#!/usr/bin/env python3
"""
Single Wallet Trader - Future replacement for enhanced_multi_wallet_trader.py
Handles one wallet trading on all configured markets
"""

import argparse
import asyncio
import json
import logging
import os
import random
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

from pyinjective.async_client_v2 import AsyncClient
from pyinjective.indexer_client import IndexerClient
from pyinjective.core.network import Network
from pyinjective.core.broadcaster import MsgBroadcasterWithPk
from pyinjective import PrivateKey, Address

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from utils.secure_wallet_loader import load_wallets_from_env

def log(message: str, wallet_id: str = None, market_id: str = None):
    """Enhanced logging with wallet and market context"""
    prefix = f"[{wallet_id}]" if wallet_id else ""
    if market_id:
        prefix += f"[{market_id}]"
    if prefix:
        prefix += " "
    
    formatted_message = f"{prefix}{message}"
    
    # Print to console
    print(formatted_message)
    
    # Save to log file
    try:
        os.makedirs("logs", exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {formatted_message}\n"
        
        with open("logs/trader.log", "a") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Failed to write to log file: {e}")

class SingleWalletTrader:
    def __init__(self, wallet_id: str, config_path: str = "config/trader_config.json", selected_markets: List[str] = None):
        self.wallet_id = wallet_id
        self.config_path = config_path
        self.config = self.load_config()
        self.selected_markets = selected_markets  # Optional market filter
        
        # Load all wallets from environment
        wallets_config = load_wallets_from_env()
        
        # Find our wallet
        wallet_data = None
        for wallet in wallets_config['wallets']:
            if wallet['id'] == wallet_id:
                wallet_data = wallet
                break
        
        if not wallet_data:
            raise ValueError(f"Wallet {wallet_id} not found in environment")
            
        # Initialize wallet
        self.private_key = wallet_data['private_key']
        
        # Initialize network with custom testnet endpoint
        self.network = Network.testnet()
        # Override the indexer endpoint as recommended by dev team
        self.network.grpc_exchange_endpoint = "k8s.testnet.exchange.grpc.injective.network:443"
        log(f"🔧 Using custom testnet endpoint: {self.network.grpc_exchange_endpoint}", self.wallet_id)
        
        # Initialize client and other attributes (will be set in initialize())
        self.async_client = None
        self.composer = None
        self.address = None
        self.broadcaster = None
        self.sequence = 0
        self.account_number = 0
        
        # Trading state
        self.active_orders = {}  # market_id -> list of order hashes
        self.last_prices = {}
        self.last_rebalance = 0
        self.orderbook_built = {}  # market_id -> bool (tracks if initial orderbook is built)
        self.orderbook_depth_stage = {}  # market_id -> int (tracks how far out we've built)
        
        # Trading statistics
        self.trading_stats = {
            'total_orders': 0,
            'successful_orders': 0,
            'failed_orders': 0,
            'total_transactions': 0,
            'sequence_errors': 0,
            'sequence_recoveries': 0,
            'markets': {}
        }
        self.start_time = time.time()
        
        # Professional sequence management
        self.sequence_lock = asyncio.Lock()
        self.consecutive_sequence_errors = 0
        self.max_sequence_errors = 5  # Circuit breaker threshold
        self.last_sequence_refresh = 0
        self.sequence_refresh_interval = 30  # Proactive refresh every 30s
        
    def load_config(self) -> Dict:
        """Load configuration from file"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            log(f"❌ Failed to load config: {e}", self.wallet_id)
            sys.exit(1)
    
    async def initialize(self):
        """Initialize the trader"""
        try:
            log(f"🚀 Initializing {self.wallet_id} trader", self.wallet_id)
            
            # Create clients
            self.async_client = AsyncClient(self.network)
            self.indexer_client = IndexerClient(self.network)
            self.composer = await self.async_client.composer()
            
            # Set up wallet identity
            private_key_obj = PrivateKey.from_hex(self.private_key)
            self.address = private_key_obj.to_public_key().to_address()
            
            # Initialize account and reset sequence to prevent mismatch
            await self.async_client.fetch_account(self.address.to_acc_bech32())
            self.sequence = self.async_client.sequence
            self.account_number = self.async_client.number
            
            # Force sequence refresh to ensure we're in sync
            await self.refresh_sequence()
            log(f"🔄 Sequence synchronized: {self.sequence}", self.wallet_id)
            
            # Initialize broadcaster with enhanced settings for network congestion
            gas_price = await self.async_client.current_chain_gas_price()
            gas_price = int(gas_price * 1.3)  # Increased gas price for faster processing
            
            self.broadcaster = MsgBroadcasterWithPk.new_using_gas_heuristics(
                network=self.network,
                private_key=self.private_key,
                gas_price=gas_price
            )
            
            # Confirm broadcaster is using the K8s endpoint
            log(f"🚀 Broadcaster using endpoint: {self.network.grpc_exchange_endpoint}", self.wallet_id)
            
            # Set timeout height offset for network congestion (increased for better reliability)
            self.broadcaster.timeout_height_offset = 300  # Increased to 300 blocks for better reliability
            
            log(f"✅ {self.wallet_id} trader initialized", self.wallet_id)
            
        except Exception as e:
            log(f"❌ Failed to initialize {self.wallet_id}: {e}", self.wallet_id)
            raise
    
    async def run(self):
        """Main trading loop"""
        await self.initialize()
        
        while True:
            try:
                # Get wallet markets
                wallet_config = self.config["wallets"][self.wallet_id]
                all_markets = wallet_config["markets"]
                
                # Filter markets if specific markets were selected
                if self.selected_markets:
                    # Validate that selected markets are in the wallet config
                    invalid_markets = [m for m in self.selected_markets if m not in all_markets]
                    if invalid_markets:
                        log(f"❌ Invalid markets for {self.wallet_id}: {invalid_markets}", self.wallet_id)
                        log(f"Available markets: {all_markets}", self.wallet_id)
                        return
                    
                    markets = self.selected_markets
                    log(f"🎯 Running with selected markets: {markets}", self.wallet_id)
                else:
                    markets = all_markets
                    log(f"🎯 Running with all configured markets: {markets}", self.wallet_id)
                
                # Trade on selected markets in a single batch transaction
                await self.trade_all_markets_batch(markets)
                
                # Wait before next cycle (increased to reduce network pressure)
                await asyncio.sleep(30)
                
            except Exception as e:
                log(f"❌ Error in trading loop: {e}", self.wallet_id)
                await asyncio.sleep(5)
    
    async def trade_all_markets_batch(self, markets: list):
        """Trade on all markets in a single batch transaction"""
        try:
            # Collect all orders for DERIVATIVE markets ONLY
            spot_orders = []
            derivative_orders = []
            derivative_orders_to_cancel = []  # Track orders to cancel
            
            # Filter for derivative markets only
            derivative_market_symbols = [
                m for m in markets 
                if self.config["markets"][m].get("type", "spot") == "derivative"
            ]
            
            if not derivative_market_symbols:
                log("⚠️ No derivative markets configured for this wallet", self.wallet_id)
                return
            
            log(f"🎯 Processing {len(derivative_market_symbols)} derivative markets", self.wallet_id)
            
            # Process each DERIVATIVE market and collect orders
            for market_symbol in derivative_market_symbols:
                market_config = self.config["markets"][market_symbol]
                market_id = market_config["testnet_market_id"]
                market_type = market_config.get("type", "spot")
                
                log(f"📊 Processing {market_symbol} ({market_type})", self.wallet_id)
                
                # Get MAINNET price for price discovery (this is the key!)
                mainnet_market_id = market_config.get("mainnet_market_id")
                if market_type == "derivative":
                    # For derivatives, get both mainnet and testnet prices for comparison
                    mainnet_price = await self.get_mainnet_derivative_price(market_symbol, mainnet_market_id)
                    testnet_price = await self.get_derivative_market_price(market_id, market_symbol)
                    
                    # Use TESTNET price as the base, we'll push it towards mainnet
                    if testnet_price > 0:
                        price = testnet_price
                        if mainnet_price > 0:
                            price_diff_percent = abs(mainnet_price - testnet_price) / mainnet_price * 100
                            log(f"💰 {market_symbol} | Mainnet: ${mainnet_price:.4f} | Testnet: ${testnet_price:.4f} | Diff: {price_diff_percent:.2f}%", self.wallet_id)
                        else:
                            log(f"💰 {market_symbol} | Using Testnet derivative price: ${testnet_price:.4f} (no mainnet price)", self.wallet_id)
                    elif mainnet_price > 0:
                        # Only if we can't get testnet price, use mainnet as fallback
                        price = mainnet_price
                        log(f"⚠️ {market_symbol} | Using Mainnet derivative price: ${mainnet_price:.4f} (no testnet price)", self.wallet_id)
                    else:
                        price = 0
                else:
                    # For spot markets, use MAINNET price to guide testnet liquidity
                    mainnet_price = await self.get_mainnet_price(market_symbol, mainnet_market_id)
                    testnet_price = await self.get_market_price(market_id, market_symbol)
                    
                    if mainnet_price > 0:
                        price = mainnet_price
                        if testnet_price > 0:
                            price_diff_percent = abs(mainnet_price - testnet_price) / mainnet_price * 100
                            log(f"💰 {market_symbol} | Mainnet: ${mainnet_price:.4f} | Testnet: ${testnet_price:.4f} | Diff: {price_diff_percent:.2f}%", self.wallet_id)
                        else:
                            log(f"💰 {market_symbol} | Using Mainnet price: ${mainnet_price:.4f} (no testnet price)", self.wallet_id)
                    else:
                        # Fallback to testnet price if mainnet unavailable
                        price = testnet_price
                        log(f"⚠️ {market_symbol} | Fallback to testnet price: ${testnet_price:.4f} (mainnet unavailable)", self.wallet_id)
                
                if not price:
                    log(f"⚠️ Skipping {market_symbol} - no price available", self.wallet_id)
                    continue
                
                # Create derivative orders (we already filtered for derivatives only)
                result = await self.create_derivative_orders(market_id, market_symbol, market_config, price)
                
                # Handle both tuple (with cancellations) and list (without cancellations) returns
                if isinstance(result, tuple):
                    market_derivative_orders, market_cancellations = result
                    derivative_orders.extend(market_derivative_orders)
                    derivative_orders_to_cancel.extend(market_cancellations)
                else:
                    derivative_orders.extend(result)
            
            # If we have orders, send them in one batch transaction
            if spot_orders or derivative_orders or derivative_orders_to_cancel:
                await self.send_batch_orders(spot_orders, derivative_orders, derivative_orders_to_cancel)
            else:
                log("⚠️ No orders to place in this cycle", self.wallet_id)
                
        except Exception as e:
            log(f"❌ Error in batch trading: {e}", self.wallet_id)
    
    # SPOT ORDERS METHOD REMOVED - Derivatives only!
    
    async def create_derivative_orders(self, market_id: str, market_symbol: str, market_config: Dict, price: float) -> list:
        """Create derivative orders - DIRECTIONAL to push price towards mainnet"""
        orders = []
        try:
            spread = market_config["spread_percent"] / 100
            order_size = Decimal(str(market_config["order_size"]))
            orders_per_market = self.config["wallets"][self.wallet_id]["trading_params"]["orders_per_market"]
            margin_ratio = Decimal("0.1")  # 10% margin requirement
            
            # Get mainnet price to determine direction
            mainnet_price = await self.get_mainnet_derivative_price(market_symbol, market_config.get("mainnet_market_id"))
            
            # Determine strategy based on price gap
            if mainnet_price > 0:
                price_gap_percent = abs(mainnet_price - price) / mainnet_price * 100
                
                log(f"💰 {market_symbol} | Testnet: ${price:.4f} | Mainnet: ${mainnet_price:.4f} | Gap: {price_gap_percent:.2f}%", self.wallet_id)
                
                # 🐋 SMART PRICE BLOCKER DETECTION & ELIMINATION
                blocker_info = await self.detect_price_blockers(market_id, mainnet_price)
                
                if blocker_info['has_blockers']:
                    log(f"🚧 Price blockers detected! {blocker_info['blocker_description']}", self.wallet_id)
                    
                    # Check if we can afford to eliminate the blockers
                    available_balance = await self.get_available_balance(market_id)
                    elimination_plan = await self.calculate_blocker_elimination_feasibility(blocker_info, available_balance)
                    
                    if elimination_plan['can_eliminate']:
                        log(f"💰 BLOCKER ELIMINATION: Balance ${available_balance:.0f} | Required: ${elimination_plan['required_margin']:.0f} | Clearing the path!", self.wallet_id)
                        
                        # Execute blocker elimination
                        success = await self.execute_blocker_elimination(market_id, elimination_plan['attack_plan'])
                        
                        if success:
                            log(f"🎉 PATH CLEARED! Blockers eliminated. Building orderbook toward target in 5 seconds...", self.wallet_id)
                            await asyncio.sleep(5)  # Brief pause after elimination
                        else:
                            log(f"❌ Elimination failed, working around blockers", self.wallet_id)
                    else:
                        log(f"💸 Can't eliminate blockers: {elimination_plan['reason']}. Working around them.", self.wallet_id)
                else:
                    log(f"✅ No significant price blockers detected", self.wallet_id)
                
                # BUILD SMART ORDERBOOK (from current reality toward target)
                orders = await self.build_smart_orderbook_toward_target(
                    market_id, market_symbol, market_config, price, mainnet_price, blocker_info
                )
                
                # SMART ORDER MANAGEMENT: Build depth first, then maintain
                if orders:  # Only check cancellation if we're placing new orders
                    # Check current open order count
                    try:
                        from pyinjective.client.model.pagination import PaginationOption
                        current_orders_response = await self.indexer_client.fetch_derivative_orders(
                            market_ids=[market_id],
                            subaccount_id=self.address.get_subaccount_id(0),
                            pagination=PaginationOption(limit=100)
                        )
                        current_order_count = len(current_orders_response.get('orders', []))
                        
                        # TARGET: Maintain 50-60 open orders for good liquidity depth
                        target_min_orders = 50
                        target_max_orders = 60
                        
                        if current_order_count >= target_max_orders:
                            # We have enough depth, start cancelling to maintain balance
                            num_to_cancel = min(8, current_order_count - target_min_orders)  # Cancel excess
                            cancellations = await self.get_open_orders_to_cancel(market_id, num_to_cancel)
                            log(f"🎯 DEPTH MANAGEMENT: {current_order_count} orders (target: {target_min_orders}-{target_max_orders}), cancelling {len(cancellations)} excess orders", self.wallet_id)
                            return orders, cancellations
                        else:
                            # Still building depth, don't cancel yet
                            log(f"📈 BUILDING DEPTH: {current_order_count} orders (target: {target_min_orders}-{target_max_orders}), adding {len(orders)} more", self.wallet_id)
                            return orders
                            
                    except Exception as e:
                        log(f"⚠️ Could not check order count, proceeding without cancellation: {e}", self.wallet_id)
                        return orders
                
                # DEBUG: Check orderbook after placing orders
                if orders:
                    log(f"🔍 DEBUG: Placed {len(orders)} orders, checking orderbook in 3 seconds...", self.wallet_id)
                    await asyncio.sleep(3)  # Wait for orders to appear
                    
                    debug_orderbook = await self.get_orderbook_depth(market_id)
                    if debug_orderbook:
                        debug_buys = debug_orderbook.get('buys', [])
                        debug_sells = debug_orderbook.get('sells', [])
                        log(f"🔍 DEBUG: Orderbook now has {len(debug_buys)} bids, {len(debug_sells)} asks", self.wallet_id)
                        
                        if debug_buys:
                            best_bid = float(debug_buys[0].get('price', '0'))
                            log(f"🔍 DEBUG: Best bid now: ${best_bid:.2f}", self.wallet_id)
                        if debug_sells:
                            best_ask = float(debug_sells[0].get('price', '999999'))
                            log(f"🔍 DEBUG: Best ask now: ${best_ask:.2f}", self.wallet_id)
                    else:
                        log(f"🔍 DEBUG: Still no orderbook data after placing orders", self.wallet_id)
                return orders
            else:
                # Can't get mainnet price - use testnet price as fallback
                log(f"⚠️ No mainnet price available - creating orderbook at testnet price ${price:.4f}", self.wallet_id)
                return await self.create_beautiful_orderbook(market_id, market_symbol, market_config, price, price)
                
        except Exception as e:
            log(f"❌ Error creating derivative orders for {market_symbol}: {e}", self.wallet_id)
            
        return orders
    
    async def get_open_orders_to_cancel(self, market_id: str, num_to_cancel: int = 3) -> list:
        """
        Fetch open orders for a market and select oldest ones to cancel
        
        Returns: List of order data dicts (market_id, subaccount_id, order_hash) for cancellation
        """
        try:
            from pyinjective.client.model.pagination import PaginationOption
            
            # Fetch open orders for this market
            # Note: API uses market_ids (plural) not market_id (singular)
            orders_response = await self.indexer_client.fetch_derivative_orders(
                market_ids=[market_id],  # Pass as list
                subaccount_id=self.address.get_subaccount_id(0),
                pagination=PaginationOption(limit=100)
            )
            
            # API returns dict with 'orders' key, not an object
            if not orders_response or 'orders' not in orders_response:
                log(f"⚠️ No orders response from API for cancellation", self.wallet_id)
                return []
            
            # Get orders list from response dict
            orders = orders_response['orders']
            if len(orders) == 0:
                log(f"⚠️ No open orders found to cancel (orderbook may be too fresh)", self.wallet_id)
                return []
            
            # INTELLIGENT BALANCING: Cancel orders from the side that has too many
            buy_orders = [o for o in orders if o.get('orderType', '').upper() == 'BUY']
            sell_orders = [o for o in orders if o.get('orderType', '').upper() == 'SELL']
            
            log(f"📋 Found {len(orders)} open orders ({len(buy_orders)} BUY, {len(sell_orders)} SELL), selecting {min(num_to_cancel, len(orders))} to cancel", self.wallet_id)
            
            orders_to_cancel = []
            
            # Strategy: Maintain balance by cancelling from the overrepresented side
            buy_count = len(buy_orders)
            sell_count = len(sell_orders)
            
            if buy_count == 0 and sell_count == 0:
                return []  # No orders to cancel
            
            # Calculate imbalance
            total_orders = buy_count + sell_count
            buy_ratio = buy_count / total_orders if total_orders > 0 else 0
            sell_ratio = sell_count / total_orders if total_orders > 0 else 0
            
            # Determine which side is overrepresented (threshold: >60% of orders)
            if buy_ratio > 0.6:  # Too many buy orders
                sorted_buys = sorted(buy_orders, key=lambda x: x.get('orderHash', ''))
                cancel_from_buys = min(num_to_cancel, len(sorted_buys))
                orders_to_cancel.extend(sorted_buys[:cancel_from_buys])
                log(f"⚖️ REBALANCING: Too many BUY orders ({buy_ratio:.1%}), cancelling {cancel_from_buys} BUY orders", self.wallet_id)
                
            elif sell_ratio > 0.6:  # Too many sell orders
                sorted_sells = sorted(sell_orders, key=lambda x: x.get('orderHash', ''))
                cancel_from_sells = min(num_to_cancel, len(sorted_sells))
                orders_to_cancel.extend(sorted_sells[:cancel_from_sells])
                log(f"⚖️ REBALANCING: Too many SELL orders ({sell_ratio:.1%}), cancelling {cancel_from_sells} SELL orders", self.wallet_id)
                
            else:  # Balanced or slight imbalance - cancel proportionally
                # Cancel proportionally from both sides to maintain balance
                buys_to_cancel = int(num_to_cancel * buy_ratio) if buy_count > 0 else 0
                sells_to_cancel = num_to_cancel - buys_to_cancel
                
                # Adjust if we don't have enough orders on one side
                if buys_to_cancel > buy_count:
                    sells_to_cancel += (buys_to_cancel - buy_count)
                    buys_to_cancel = buy_count
                elif sells_to_cancel > sell_count:
                    buys_to_cancel += (sells_to_cancel - sell_count)
                    sells_to_cancel = sell_count
                
                if buys_to_cancel > 0:
                    sorted_buys = sorted(buy_orders, key=lambda x: x.get('orderHash', ''))
                    orders_to_cancel.extend(sorted_buys[:buys_to_cancel])
                    
                if sells_to_cancel > 0:
                    sorted_sells = sorted(sell_orders, key=lambda x: x.get('orderHash', ''))
                    orders_to_cancel.extend(sorted_sells[:sells_to_cancel])
                
                log(f"⚖️ BALANCED: Cancelling {buys_to_cancel} BUY + {sells_to_cancel} SELL orders proportionally", self.wallet_id)
            
            # Format as order data dicts for composer (matching manual_order_canceller.py format)
            order_data_list = [
                {
                    'market_id': market_id,
                    'subaccount_id': self.address.get_subaccount_id(0),
                    'order_hash': order.get('orderHash')
                }
                for order in orders_to_cancel
            ]
            
            if order_data_list:
                log(f"🗑️ Selected {len(order_data_list)} orders to cancel", self.wallet_id)
            
            return order_data_list
            
        except Exception as e:
            log(f"⚠️ Error fetching orders to cancel: {e}", self.wallet_id)
            return []
    
    async def gradual_orderbook_update(self, market_id: str, market_symbol: str, market_config: Dict,
                                       testnet_price: float, mainnet_price: float) -> list:
        """
        Gradually build orderbook when prices are aligned
        - Progressively expand spread range to build depth outward
        - Cancel 2-3 oldest orders to refresh (returned separately for batch update)
        
        Returns: (new_orders, orders_to_cancel)
        """
        orders = []
        try:
            order_size = Decimal(str(market_config["order_size"]))
            margin_ratio = Decimal("0.1")
            # Use TESTNET price as center when aligned - we're maintaining current market, not pushing it
            center_price = testnet_price
            
            # Track depth expansion stage (how far out we've built)
            if market_id not in self.orderbook_depth_stage:
                self.orderbook_depth_stage[market_id] = 0
            
            # Progressive depth expansion - each cycle pushes orders further out
            current_stage = self.orderbook_depth_stage[market_id]
            
            # Define spread ranges for each stage (MUCH WIDER for deep orderbook)
            spread_ranges = [
                (0.002, 0.015),  # Stage 0: 0.2%-1.5% (tight center)
                (0.010, 0.035),  # Stage 1: 1%-3.5% (mid range)
                (0.025, 0.060),  # Stage 2: 2.5%-6% (wider)
                (0.045, 0.090),  # Stage 3: 4.5%-9% (deep)
                (0.070, 0.120),  # Stage 4: 7%-12% (very deep)
                (0.100, 0.180),  # Stage 5: 10%-18% (ultra deep)
            ]
            
            # Cycle through stages (reset to 0 after stage 5)
            min_spread, max_spread = spread_ranges[current_stage % len(spread_ranges)]
            
            # Place MORE orders per side for deeper book
            num_orders_per_side = random.randint(8, 12)
            
            log(f"📏 Depth stage {current_stage}: spread range {min_spread*100:.1f}%-{max_spread*100:.1f}%", self.wallet_id)
            
            for i in range(num_orders_per_side):
                # EXPONENTIAL spread distribution for better price diversity
                # Early orders closer to center, later orders much further out
                spread_factor = (i / (num_orders_per_side - 1)) ** 1.5  # Exponential curve
                spread = min_spread + (max_spread - min_spread) * spread_factor
                
                # Add small random variation to avoid exact duplicates
                spread *= random.uniform(0.9, 1.1)
                offset = spread
                
                # Smaller sizes (20%-50% of base) but more orders for organic look
                size_mult = random.uniform(0.2, 0.5)
                actual_size = (order_size * Decimal(str(size_mult))).quantize(Decimal('0.001'))
                
                # Buy order
                buy_price = Decimal(str(center_price * (1 - offset)))
                # Round to 2 decimal places for exchange compatibility
                buy_price = buy_price.quantize(Decimal('0.01'))
                buy_margin = (buy_price * actual_size * margin_ratio).quantize(Decimal('0.01'))
                
                orders.append(self.composer.derivative_order(
                    market_id=market_id,
                    subaccount_id=self.address.get_subaccount_id(0),
                    fee_recipient=self.address.to_acc_bech32(),
                    price=buy_price,
                    quantity=actual_size,
                    margin=buy_margin,
                    order_type="BUY",
                    cid=None
                ))
                
                # Sell order - add extra buffer to prevent immediate fills
                sell_spread_buffer = 0.002  # Extra 0.2% buffer for sells
                sell_price = Decimal(str(center_price * (1 + offset + sell_spread_buffer)))
                # Round to 2 decimal places for exchange compatibility
                sell_price = sell_price.quantize(Decimal('0.01'))
                sell_margin = (sell_price * actual_size * margin_ratio * Decimal("1.5")).quantize(Decimal('0.01'))  # Higher margin for shorts
                
                orders.append(self.composer.derivative_order(
                    market_id=market_id,
                    subaccount_id=self.address.get_subaccount_id(0),
                    fee_recipient=self.address.to_acc_bech32(),
                    price=sell_price,
                    quantity=actual_size,
                    margin=sell_margin,
                    order_type="SELL",
                    cid=None
                ))
            
            # Advance to next stage FASTER (every 2 cycles instead of every cycle)
            if random.random() < 0.5:  # 50% chance to advance stage each cycle
                self.orderbook_depth_stage[market_id] = current_stage + 1
                log(f"📈 Advanced to depth stage {self.orderbook_depth_stage[market_id]}", self.wallet_id)
            
            log(f"📝 Created {len(orders)} gradual orders ({num_orders_per_side} buys + {num_orders_per_side} sells)", self.wallet_id)
            
            # Debug: Show sell order prices to verify they're reasonable
            sell_orders = [o for o in orders if "SELL" in str(o)]
            buy_orders = [o for o in orders if "BUY" in str(o)]
            
            if sell_orders and num_orders_per_side > 0:
                # Estimate sell prices for logging (this is approximate)
                min_sell_spread = min_spread + 0.002  # Adding our buffer
                max_sell_spread = max_spread + 0.002
                min_sell_price = center_price * (1 + min_sell_spread)
                max_sell_price = center_price * (1 + max_sell_spread)
                log(f"💸 Sell orders: ${min_sell_price:.4f} - ${max_sell_price:.4f} (spread: {min_sell_spread*100:.2f}% - {max_sell_spread*100:.2f}%)", self.wallet_id)
                log(f"📊 Current market: mid=${center_price:.4f}, expected sells should appear ABOVE this price", self.wallet_id)
                log(f"🔍 Created {len(buy_orders)} BUY + {len(sell_orders)} SELL orders for submission", self.wallet_id)
            
            # Reduce cancellation rate to preserve sell orders (was 4-6, now 2-3)
            num_to_cancel = random.randint(2, 3)
            orders_to_cancel = await self.get_open_orders_to_cancel(market_id, num_to_cancel)
            
        except Exception as e:
            log(f"❌ Error creating gradual orders for {market_symbol}: {e}", self.wallet_id)
            orders_to_cancel = []
            
        return orders, orders_to_cancel
    
    async def create_beautiful_orderbook(self, market_id: str, market_symbol: str, market_config: Dict, 
                                         testnet_price: float, mainnet_price: float) -> list:
        """
        Create a smart, adaptive orderbook that responds to market conditions
        - Detects aggressive buyers/sellers and adjusts accordingly
        - Uses dynamic sizing based on orderbook depth
        - Implements smart spread management
        """
        orders = []
        try:
            order_size = Decimal(str(market_config["order_size"]))
            margin_ratio = Decimal("0.1")
            
            # Use mainnet price as the center for orderbook
            center_price = mainnet_price
            
            # SMART ADAPTATION: Check current orderbook conditions
            current_orderbook = await self.get_orderbook_depth(market_id)
            
            # Analyze market conditions
            buy_pressure, sell_pressure = self.analyze_market_pressure(current_orderbook)
            
            # Dynamic order sizing based on market conditions AND price convergence mission
            price_gap_percent = abs(mainnet_price - testnet_price) / mainnet_price * 100
            is_testnet_overpriced = testnet_price > mainnet_price
            
            if buy_pressure > 3.0:  # Strong buying pressure detected
                if is_testnet_overpriced:
                    log(f"🎯 MISSION MODE: Testnet overpriced by {price_gap_percent:.1f}% + Strong buying pressure ({buy_pressure:.1f}x)", self.wallet_id)
                    log(f"🔥 Strategy: AGGRESSIVE SELLING to correct price + Strategic buying at mainnet levels", self.wallet_id)
                    # MISSION: Correct overpriced testnet with aggressive selling
                    buy_size_multiplier = 0.8   # Some buy support at mainnet price
                    sell_size_multiplier = 3.0  # VERY aggressive selling to push price down
                    sell_spread_multiplier = 0.6  # Much tighter sell spreads (aggressive correction)
                    buy_spread_multiplier = 1.2   # Slightly wider buy spreads
                else:
                    log(f"🔥 STRONG BUYING PRESSURE detected ({buy_pressure:.1f}x) - Adapting strategy", self.wallet_id)
                    # Standard adaptive response when testnet isn't overpriced
                    buy_size_multiplier = 0.5
                    sell_size_multiplier = 2.0
                    sell_spread_multiplier = 0.8
                    buy_spread_multiplier = 1.5
                    
            elif sell_pressure > 3.0:  # Strong selling pressure detected
                if not is_testnet_overpriced:  # Testnet is underpriced
                    log(f"🎯 MISSION MODE: Testnet underpriced by {price_gap_percent:.1f}% + Strong selling pressure ({sell_pressure:.1f}x)", self.wallet_id)
                    log(f"🔥 Strategy: AGGRESSIVE BUYING to correct price + Strategic selling at mainnet levels", self.wallet_id)
                    # MISSION: Support underpriced testnet with aggressive buying
                    buy_size_multiplier = 3.0   # VERY aggressive buying to push price up
                    sell_size_multiplier = 0.8  # Some sell resistance at mainnet price
                    sell_spread_multiplier = 1.2  # Slightly wider sell spreads
                    buy_spread_multiplier = 0.6   # Much tighter buy spreads (aggressive correction)
                else:
                    log(f"🔥 STRONG SELLING PRESSURE detected ({sell_pressure:.1f}x) - Adapting strategy", self.wallet_id)
                    # Standard adaptive response when testnet isn't underpriced
                    buy_size_multiplier = 2.0
                    sell_size_multiplier = 0.5
                    sell_spread_multiplier = 1.5
                    buy_spread_multiplier = 0.8
            else:
                # Balanced market - focus purely on price convergence mission
                if price_gap_percent > 2.0:
                    if is_testnet_overpriced:
                        log(f"🎯 PRICE CORRECTION MODE: Testnet {price_gap_percent:.1f}% overpriced - Aggressive selling", self.wallet_id)
                        buy_size_multiplier = 0.7
                        sell_size_multiplier = 2.5  # Aggressive selling to correct
                        sell_spread_multiplier = 0.7  # Tighter sells
                        buy_spread_multiplier = 1.3   # Wider buys
                    else:
                        log(f"🎯 PRICE CORRECTION MODE: Testnet {price_gap_percent:.1f}% underpriced - Aggressive buying", self.wallet_id)
                        buy_size_multiplier = 2.5   # Aggressive buying to correct
                        sell_size_multiplier = 0.7
                        sell_spread_multiplier = 1.3  # Wider sells
                        buy_spread_multiplier = 0.7   # Tighter buys
                else:
                    log(f"⚖️ BALANCED MARKET + ALIGNED PRICES ({price_gap_percent:.1f}% gap) - Standard strategy", self.wallet_id)
                    buy_size_multiplier = 1.0
                    sell_size_multiplier = 1.0
                    sell_spread_multiplier = 1.0
                    buy_spread_multiplier = 1.0
            
            # Create beautiful staircase orderbook with smooth depth
            # Start tight near center, gradually widen
            order_levels = []
            base_spread = 0.0001  # Start at 0.01% from center
            
            # Create 12 levels on each side with much wider spreads to avoid immediate fills
            for level in range(12):
                if level < 4:
                    # Tight levels near center (0.05% - 0.5%) - Much wider minimum spread
                    spread = base_spread * (level + 1) * 5  # Increased from 3 to 5
                    size_mult = 1.5 - (level * 0.05)  # Gradually decrease size
                elif level < 8:
                    # Medium levels (0.5% - 1.5%) - Much wider spreads
                    spread = 0.005 + (level - 4) * 0.0025  # Increased significantly
                    size_mult = 1.2 - ((level - 4) * 0.08)
                else:
                    # Wide levels (1.5% - 4%) - Very wide spreads
                    spread = 0.015 + (level - 8) * 0.008  # Much wider
                    size_mult = 0.8 - ((level - 8) * 0.08)
                
                order_levels.append((spread, size_mult))
            
            # Create orders at each level with smart adaptation
            for level_idx, (spread, size_mult) in enumerate(order_levels):
                # Add slight randomization for natural look
                spread_jitter = random.uniform(0.95, 1.05)
                size_jitter = random.uniform(0.9, 1.1)
                
                # Apply smart multipliers based on market conditions
                buy_spread = spread * spread_jitter * buy_spread_multiplier
                sell_spread = spread * spread_jitter * sell_spread_multiplier
                
                buy_size = order_size * Decimal(str(size_mult * size_jitter * buy_size_multiplier))
                sell_size = order_size * Decimal(str(size_mult * size_jitter * sell_size_multiplier))
                
                buy_size = buy_size.quantize(Decimal('0.001'))
                sell_size = sell_size.quantize(Decimal('0.001'))
                
                # Calculate prices for this level with much more conservative sells
                buy_price = Decimal(str(center_price * (1 - buy_spread)))
                
                # CRITICAL FIX: For huge price gaps, place sells ABOVE the testnet best bid to avoid whales
                if price_gap_percent > 5.0:  # Large price gap detected
                    # Get the best bid from testnet orderbook to avoid whale orders
                    testnet_best_bid = testnet_price  # This is the best bid price
                    
                    # Place sells ABOVE the whale's bid with small premiums
                    sell_premium_percent = 0.002 + (sell_spread * 0.5)  # 0.2% base + spread
                    sell_price = Decimal(str(testnet_best_bid * (1 + sell_premium_percent)))
                    
                    log(f"🐋 Whale avoidance: Placing sells ABOVE testnet bid ${testnet_best_bid:.4f} at ${float(sell_price):.4f} (+{sell_premium_percent*100:.2f}%)", self.wallet_id) if level_idx == 0 else None
                else:
                    # Normal mode - use mainnet price as base
                    sell_price = Decimal(str(center_price * (1 + sell_spread + 0.005)))  # Extra buffer for sells
                
                # Smart rounding based on price level for natural look
                # Round to 2 decimal places for exchange compatibility
                buy_price = buy_price.quantize(Decimal('0.01'))
                sell_price = sell_price.quantize(Decimal('0.01'))
                
                # Create buy order (only if size is meaningful)
                if buy_size >= Decimal('0.1'):  # Minimum order size check
                    buy_margin = buy_price * buy_size * margin_ratio
                    buy_margin = buy_margin.quantize(Decimal('0.01'))
                    buy_order = self.composer.derivative_order(
                        market_id=market_id,
                        subaccount_id=self.address.get_subaccount_id(0),
                        fee_recipient=self.address.to_acc_bech32(),
                        price=buy_price,
                        quantity=buy_size,
                        margin=buy_margin,
                        order_type="BUY",
                        cid=None
                    )
                    orders.append(buy_order)
                
                # Create sell order (only if size is meaningful)
                if sell_size >= Decimal('0.1'):  # Minimum order size check
                    sell_margin = sell_price * sell_size * margin_ratio * Decimal("1.5")  # Higher margin for shorts
                    sell_margin = sell_margin.quantize(Decimal('0.01'))
                    sell_order = self.composer.derivative_order(
                        market_id=market_id,
                        subaccount_id=self.address.get_subaccount_id(0),
                        fee_recipient=self.address.to_acc_bech32(),
                        price=sell_price,
                        quantity=sell_size,
                        margin=sell_margin,
                        order_type="SELL",
                        cid=None
                    )
                    orders.append(sell_order)
                
                # Debug: Log first few levels to verify whale avoidance strategy
                if level_idx < 3:
                    buy_distance = (center_price - float(buy_price)) / center_price * 100
                    sell_distance = (float(sell_price) - center_price) / center_price * 100
                    whale_distance = (float(sell_price) - testnet_price) / testnet_price * 100
                    log(f"🔍 Level {level_idx}: BUY ${buy_price:.4f} ({buy_distance:.2f}% below mainnet, size: {buy_size}) | SELL ${sell_price:.4f} ({sell_distance:.2f}% above mainnet, +{whale_distance:.2f}% vs whale bid, size: {sell_size})", self.wallet_id)
            
            # Count buy vs sell orders for debugging
            buy_orders = [o for o in orders if "BUY" in str(o)]
            sell_orders = [o for o in orders if "SELL" in str(o)]
            
            # Calculate total margin requirements
            total_buy_margin = sum(buy_price * actual_size * Decimal("0.1") for buy_price, actual_size in [(Decimal("12.60"), Decimal("11.0"))] * len(buy_orders))
            total_sell_margin = sum(sell_price * actual_size * Decimal("0.1") for sell_price, actual_size in [(Decimal("12.65"), Decimal("11.0"))] * len(sell_orders))
            
            log(f"📖 Created beautiful orderbook with {len(orders)} orders ({len(buy_orders)} BUY, {len(sell_orders)} SELL) across {len(order_levels)} levels", self.wallet_id)
            log(f"💰 Estimated margin - BUY: ${total_buy_margin:.2f} | SELL: ${total_sell_margin:.2f} | TOTAL: ${total_buy_margin + total_sell_margin:.2f}", self.wallet_id)
            
        except Exception as e:
            log(f"❌ Error creating beautiful orderbook for {market_symbol}: {e}", self.wallet_id)
            
        return orders
    
    async def get_orderbook_depth(self, market_id: str) -> dict:
        """Get current orderbook depth for market analysis"""
        try:
            # Fix: Add required depth parameter
            orderbook = await self.indexer_client.fetch_derivative_orderbook_v2(market_id=market_id, depth=10)
            return {
                'buys': orderbook.get('buys', []),
                'sells': orderbook.get('sells', [])
            }
        except Exception as e:
            log(f"⚠️ Could not fetch orderbook depth: {e}", self.wallet_id)
            return {'buys': [], 'sells': []}
    
    def analyze_market_pressure(self, orderbook: dict) -> tuple:
        """
        Analyze market pressure from orderbook depth
        Returns (buy_pressure, sell_pressure) as ratios
        """
        try:
            buys = orderbook.get('buys', [])
            sells = orderbook.get('sells', [])
            
            if not buys or not sells:
                return 1.0, 1.0  # Neutral if no data
            
            # Calculate total volume in top 5 levels
            buy_volume = sum(float(order.get('quantity', 0)) for order in buys[:5])
            sell_volume = sum(float(order.get('quantity', 0)) for order in sells[:5])
            
            if buy_volume == 0 or sell_volume == 0:
                return 1.0, 1.0
            
            # Calculate pressure ratios
            if buy_volume > sell_volume:
                buy_pressure = buy_volume / sell_volume
                sell_pressure = 1.0
            else:
                sell_pressure = sell_volume / buy_volume
                buy_pressure = 1.0
                
            # Cap extreme values
            buy_pressure = min(buy_pressure, 10.0)
            sell_pressure = min(sell_pressure, 10.0)
            
            return buy_pressure, sell_pressure
            
        except Exception as e:
            log(f"⚠️ Error analyzing market pressure: {e}", self.wallet_id)
            return 1.0, 1.0
    
    async def get_available_balance(self, market_id: str) -> Decimal:
        """Get available USDT balance for derivative trading"""
        try:
            portfolio = await self.indexer_client.fetch_account_portfolio(
                account_address=self.address.to_acc_bech32()
            )
            
            if not portfolio or 'portfolio' not in portfolio:
                return Decimal('0')
            
            # Look for USDT balance (quote currency for derivatives)
            for balance in portfolio['portfolio'].get('bankBalances', []):
                denom = balance.get('denom', '')
                if 'usdt' in denom.lower() or 'peggy0x' in denom.lower():
                    available = balance.get('amount', '0')
                    # Convert from wei to human readable (18 decimals for USDT)
                    return Decimal(available) / Decimal('10') ** 18
            
            return Decimal('0')
            
        except Exception as e:
            log(f"⚠️ Error getting available balance: {e}", self.wallet_id)
            return Decimal('0')

    async def detect_price_blockers(self, market_id: str, target_price: float) -> Dict:
        """
        Detect orders that block us from building orderbook toward target price
        These are the 'whales' we need to deal with
        """
        try:
            orderbook = await self.get_orderbook_depth(market_id)
            if not orderbook:
                return {'has_blockers': False}
            
            buys = orderbook.get('buys', [])
            sells = orderbook.get('sells', [])
            
            blockers = {
                'has_blockers': False,
                'blocker_description': '',
                'buy_blockers': [],
                'sell_blockers': [],
                'total_blocker_volume': Decimal('0')
            }
            
            # Define what constitutes a "blocker"
            min_blocker_size = Decimal('50')  # Orders > 50 size that block our path
            
            # Check for buy-side blockers (preventing us from building sells toward target)
            if buys:
                best_bid = float(buys[0].get('price', '0'))
                
                # If best bid is way above target, it's blocking us from building sell orders
                if best_bid > target_price * 1.5:  # 50% above target
                    for buy in buys[:3]:  # Check top 3 bids
                        size = Decimal(buy.get('quantity', '0'))
                        price = float(buy.get('price', '0'))
                        
                        if size >= min_blocker_size and price > target_price * 1.2:  # 20% above target
                            blockers['buy_blockers'].append({
                                'price': Decimal(str(price)),
                                'size': size,
                                'notional': Decimal(str(price)) * size
                            })
                            blockers['total_blocker_volume'] += size
            
            # Check for sell-side blockers (preventing us from building buys toward target)
            if sells:
                best_ask = float(sells[0].get('price', '999999'))
                
                # If best ask is way below target, it's blocking us from building buy orders
                if best_ask < target_price * 0.5:  # 50% below target
                    for sell in sells[:3]:  # Check top 3 asks
                        size = Decimal(sell.get('quantity', '0'))
                        price = float(sell.get('price', '999999'))
                        
                        if size >= min_blocker_size and price < target_price * 0.8:  # 20% below target
                            blockers['sell_blockers'].append({
                                'price': Decimal(str(price)),
                                'size': size,
                                'notional': Decimal(str(price)) * size
                            })
                            blockers['total_blocker_volume'] += size
            
            # Determine if we have significant blockers
            if blockers['buy_blockers'] or blockers['sell_blockers']:
                blockers['has_blockers'] = True
                
                descriptions = []
                if blockers['buy_blockers']:
                    buy_blocker = blockers['buy_blockers'][0]  # Biggest one
                    descriptions.append(f"Buy blocker: {buy_blocker['size']} @ ${buy_blocker['price']:.4f}")
                
                if blockers['sell_blockers']:
                    sell_blocker = blockers['sell_blockers'][0]  # Biggest one
                    descriptions.append(f"Sell blocker: {sell_blocker['size']} @ ${sell_blocker['price']:.4f}")
                
                blockers['blocker_description'] = " | ".join(descriptions)
            
            return blockers
            
        except Exception as e:
            log(f"⚠️ Error detecting price blockers: {e}", self.wallet_id)
            return {'has_blockers': False}

    async def calculate_blocker_elimination_feasibility(self, blocker_info: Dict, available_balance: Decimal) -> Dict:
        """Calculate if we can afford to eliminate the price blockers"""
        try:
            if not blocker_info['has_blockers']:
                return {'can_eliminate': False, 'reason': 'No blockers detected'}
            
            margin_ratio = Decimal('0.15')  # 15% margin for safety
            required_margin = Decimal('0')
            attack_plan = {}
            
            # Plan elimination of buy blockers (we sell to them)
            if blocker_info['buy_blockers']:
                for i, blocker in enumerate(blocker_info['buy_blockers'][:2]):  # Max 2 blockers
                    attack_size = min(blocker['size'], blocker['size'] * Decimal('0.8'))  # Attack 80% max
                    attack_margin = blocker['price'] * attack_size * margin_ratio
                    required_margin += attack_margin
                    
                    attack_plan[f'sell_attack_{i}'] = {
                        'target_price': blocker['price'],
                        'attack_size': attack_size,
                        'required_margin': attack_margin
                    }
            
            # Plan elimination of sell blockers (we buy from them)
            if blocker_info['sell_blockers']:
                for i, blocker in enumerate(blocker_info['sell_blockers'][:2]):  # Max 2 blockers
                    attack_size = min(blocker['size'], blocker['size'] * Decimal('0.8'))  # Attack 80% max
                    attack_margin = blocker['price'] * attack_size * margin_ratio
                    required_margin += attack_margin
                    
                    attack_plan[f'buy_attack_{i}'] = {
                        'target_price': blocker['price'],
                        'attack_size': attack_size,
                        'required_margin': attack_margin
                    }
            
            # Reserve funds for continued market making (30% of balance)
            reserved_for_mm = available_balance * Decimal('0.3')
            available_for_attack = available_balance - reserved_for_mm
            
            can_eliminate = required_margin <= available_for_attack and required_margin > 0
            
            return {
                'can_eliminate': can_eliminate,
                'required_margin': required_margin,
                'available_balance': available_balance,
                'available_for_attack': available_for_attack,
                'reserved_for_mm': reserved_for_mm,
                'attack_plan': attack_plan,
                'reason': 'Sufficient funds' if can_eliminate else f'Need ${required_margin:.0f}, have ${available_for_attack:.0f}'
            }
            
        except Exception as e:
            log(f"⚠️ Error calculating blocker elimination: {e}", self.wallet_id)
            return {'can_eliminate': False, 'reason': f'Calculation error: {e}'}

    async def execute_blocker_elimination(self, market_id: str, attack_plan: Dict) -> bool:
        """Execute the elimination of price blockers"""
        try:
            orders = []
            
            # Execute all planned attacks
            for attack_key, attack_data in attack_plan.items():
                price = attack_data['target_price']
                size = attack_data['attack_size']
                margin = attack_data['required_margin']
                
                if 'sell_attack' in attack_key:
                    # Sell attack (eliminate buy blocker)
                    order = self.composer.derivative_order(
                        market_id=market_id,
                        subaccount_id=self.address.get_subaccount_id(0),
                        fee_recipient=self.address.to_acc_bech32(),
                        price=price,
                        quantity=size,
                        margin=margin,
                        order_type="SELL",
                        cid=None
                    )
                    orders.append(order)
                    log(f"🎯 ELIMINATING BUY BLOCKER: Selling {size} @ ${price:.4f}", self.wallet_id)
                    
                elif 'buy_attack' in attack_key:
                    # Buy attack (eliminate sell blocker)
                    order = self.composer.derivative_order(
                        market_id=market_id,
                        subaccount_id=self.address.get_subaccount_id(0),
                        fee_recipient=self.address.to_acc_bech32(),
                        price=price,
                        quantity=size,
                        margin=margin,
                        order_type="BUY",
                        cid=None
                    )
                    orders.append(order)
                    log(f"🎯 ELIMINATING SELL BLOCKER: Buying {size} @ ${price:.4f}", self.wallet_id)
            
            if orders:
                # Execute elimination orders
                success = await self.send_batch_orders([], orders)  # Only derivative orders
                if success:
                    total_value = sum(float(o.price) * float(o.quantity) for o in orders)
                    log(f"🎉 BLOCKERS ELIMINATED! Cleared ${total_value:.0f} of blocking liquidity", self.wallet_id)
                    return True
                else:
                    log(f"❌ Blocker elimination failed - orders rejected", self.wallet_id)
                    return False
            
            return False
            
        except Exception as e:
            log(f"❌ Error executing blocker elimination: {e}", self.wallet_id)
            return False

    async def build_smart_orderbook_toward_target(self, market_id: str, market_symbol: str, market_config: Dict,
                                                testnet_price: float, mainnet_price: float, blocker_info: Dict) -> list:
        """
        Build orderbook intelligently from current reality toward mainnet target
        Takes into account any remaining blockers we couldn't eliminate
        """
        try:
            orders = []
            order_size = Decimal(str(market_config["order_size"]))
            margin_ratio = Decimal("0.1")
            target_price = mainnet_price
            
            # Get current orderbook state
            current_orderbook = await self.get_orderbook_depth(market_id)
            current_best_bid = 0.0
            current_best_ask = float('inf')
            
            if current_orderbook:
                buys = current_orderbook.get('buys', [])
                sells = current_orderbook.get('sells', [])
                
                if buys:
                    current_best_bid = float(buys[0].get('price', '0'))
                if sells:
                    current_best_ask = float(sells[0].get('price', '999999'))
            
            log(f"🎯 Building toward target: Current BID ${current_best_bid:.4f} ←→ ASK ${current_best_ask:.4f} | Target: ${target_price:.4f}", self.wallet_id)
            
            # Calculate how aggressive we should be based on price gap
            price_gap_percent = abs(mainnet_price - testnet_price) / mainnet_price * 100
            
            if price_gap_percent > 20:
                # Large gap - be more aggressive, move 30% toward target each cycle
                convergence_factor = 0.3
                num_orders_per_side = 10
                log(f"🚀 AGGRESSIVE MODE: Large gap ({price_gap_percent:.1f}%), moving 30% toward target", self.wallet_id)
            elif price_gap_percent > 5:
                # Medium gap - moderate approach, move 20% toward target
                convergence_factor = 0.2
                num_orders_per_side = 12
                log(f"🎯 MODERATE MODE: Medium gap ({price_gap_percent:.1f}%), moving 20% toward target", self.wallet_id)
            else:
                # Small gap - conservative approach, move 10% toward target
                convergence_factor = 0.1
                num_orders_per_side = 8
                log(f"⚖️ CONSERVATIVE MODE: Small gap ({price_gap_percent:.1f}%), moving 10% toward target", self.wallet_id)
            
            # Calculate our target bid/ask (moving toward mainnet price)
            # Handle the case where current_best_bid is 0 or current_best_ask is inf
            if current_best_bid == 0.0:
                # No existing bids - start from a reasonable distance below target
                our_best_bid = target_price * 0.98  # 2% below target
            elif current_best_bid < target_price:
                our_best_bid = current_best_bid + (target_price - current_best_bid) * convergence_factor
            else:
                our_best_bid = max(current_best_bid * 0.99, target_price * 0.995)  # Don't go too far below target
                
            if current_best_ask == float('inf'):
                # No existing asks - start from a reasonable distance above target
                our_best_ask = target_price * 1.02  # 2% above target
            elif current_best_ask > target_price:
                our_best_ask = current_best_ask - (current_best_ask - target_price) * convergence_factor
            else:
                our_best_ask = min(current_best_ask * 1.01, target_price * 1.005)  # Don't go too far above target
            
            # Adjust for any remaining blockers we couldn't eliminate
            if blocker_info.get('buy_blockers'):
                # There are still buy blockers, place our sells safely above them
                highest_blocker = max(blocker_info['buy_blockers'], key=lambda x: x['price'])
                our_best_ask = max(our_best_ask, float(highest_blocker['price']) * 1.02)  # 2% above blocker
                log(f"🚧 Adjusting for buy blocker: Placing sells above ${highest_blocker['price']:.4f}", self.wallet_id)
            
            if blocker_info.get('sell_blockers'):
                # There are still sell blockers, place our buys safely below them
                lowest_blocker = min(blocker_info['sell_blockers'], key=lambda x: x['price'])
                our_best_bid = min(our_best_bid, float(lowest_blocker['price']) * 0.98)  # 2% below blocker
                log(f"🚧 Adjusting for sell blocker: Placing buys below ${lowest_blocker['price']:.4f}", self.wallet_id)
            
            log(f"📊 Our orderbook plan: BID ${our_best_bid:.4f} ←→ ASK ${our_best_ask:.4f}", self.wallet_id)
            
            # Safety check - ensure we have valid prices
            if not (0 < our_best_bid < float('inf') and 0 < our_best_ask < float('inf')):
                log(f"❌ Invalid price calculation: BID=${our_best_bid}, ASK=${our_best_ask}", self.wallet_id)
                return []
            
            if our_best_bid >= our_best_ask:
                log(f"❌ Invalid spread: BID ${our_best_bid:.4f} >= ASK ${our_best_ask:.4f}", self.wallet_id)
                return []
            
            # Log results - track prices as we create orders
            buy_prices = []
            sell_prices = []
            
            # Create orders spreading outward from our target bid/ask
            for i in range(num_orders_per_side):
                # Progressive spread (tighter near center, wider further out)
                spread_factor = (i / max(1, num_orders_per_side - 1)) ** 1.2  # Exponential curve
                max_spread = 0.05  # 5% max spread
                spread = max_spread * spread_factor
                
                # Buy orders spreading down from our_best_bid
                buy_price = Decimal(str(our_best_bid * (1 - spread)))
                # Round to 3 decimal places for better precision
                buy_price = buy_price.quantize(Decimal('0.001'))
                buy_prices.append(float(buy_price))  # Track for summary
                
                # Sell orders spreading up from our_best_ask
                sell_price = Decimal(str(our_best_ask * (1 + spread)))
                # Round to 3 decimal places for better precision
                sell_price = sell_price.quantize(Decimal('0.001'))
                sell_prices.append(float(sell_price))  # Track for summary
                
                # Variable order sizes for organic look
                size_mult = random.uniform(0.7, 1.3)
                buy_size = (order_size * Decimal(str(size_mult))).quantize(Decimal('0.001'))
                sell_size = (order_size * Decimal(str(size_mult))).quantize(Decimal('0.001'))
                
                # Create buy order
                buy_margin = (buy_price * buy_size * margin_ratio).quantize(Decimal('0.01'))
                
                # Debug logging for buy order
                log(f"🔍 Creating BUY order: price=${float(buy_price):.3f}, size={float(buy_size):.3f}, margin={float(buy_margin):.2f}", self.wallet_id)
                
                try:
                    buy_order = self.composer.derivative_order(
                        market_id=market_id,
                        subaccount_id=self.address.get_subaccount_id(0),
                        fee_recipient=self.address.to_acc_bech32(),
                        price=buy_price,
                        quantity=buy_size,
                        margin=buy_margin,
                        order_type="BUY",
                        cid=None
                    )
                    orders.append(buy_order)
                except Exception as buy_error:
                    log(f"❌ Error creating BUY order: {buy_error}", self.wallet_id)
                    continue
                
                # Create sell order
                sell_margin = (sell_price * sell_size * margin_ratio * Decimal("1.5")).quantize(Decimal('0.01'))
                
                # Debug logging for sell order
                log(f"🔍 Creating SELL order: price=${float(sell_price):.3f}, size={float(sell_size):.3f}, margin={float(sell_margin):.2f}", self.wallet_id)
                
                try:
                    sell_order = self.composer.derivative_order(
                        market_id=market_id,
                        subaccount_id=self.address.get_subaccount_id(0),
                        fee_recipient=self.address.to_acc_bech32(),
                        price=sell_price,
                        quantity=sell_size,
                        margin=sell_margin,
                        order_type="SELL",
                        cid=None
                    )
                    orders.append(sell_order)
                except Exception as sell_error:
                    log(f"❌ Error creating SELL order: {sell_error}", self.wallet_id)
                    continue
            
            # Log results using our tracked prices
            buy_orders = [o for o in orders if "BUY" in str(o)]
            sell_orders = [o for o in orders if "SELL" in str(o)]
            
            if buy_prices and sell_prices:
                log(f"📖 Smart orderbook: {len(orders)} orders ({len(buy_orders)} BUY: ${min(buy_prices):.3f}-${max(buy_prices):.3f}, {len(sell_orders)} SELL: ${min(sell_prices):.3f}-${max(sell_prices):.3f})", self.wallet_id)
            else:
                log(f"📖 Smart orderbook: {len(orders)} orders ({len(buy_orders)} BUY, {len(sell_orders)} SELL)", self.wallet_id)
            
            return orders
            
        except Exception as e:
            log(f"❌ Error building smart orderbook: {e}", self.wallet_id)
            import traceback
            log(f"❌ Full traceback: {traceback.format_exc()}", self.wallet_id)
            return []
    
    async def send_batch_orders(self, spot_orders: list, derivative_orders: list, derivative_orders_to_cancel: list = None):
        """
        Professional batch order sender with intelligent sequence recovery
        
        Features:
        - Automatic retry with exponential backoff
        - Intelligent sequence error detection and recovery
        - Circuit breaker for persistent failures
        - Proactive sequence refresh
        - Batch order cancellation + creation in single transaction
        """
        if derivative_orders_to_cancel is None:
            derivative_orders_to_cancel = []
            
        total_orders = len(spot_orders) + len(derivative_orders)
        total_cancellations = len(derivative_orders_to_cancel)
        max_retries = 3
        base_delay = 0.5
        
        # Circuit breaker: If too many consecutive sequence errors, pause trading
        if self.consecutive_sequence_errors >= self.max_sequence_errors:
            log(f"🛑 Circuit breaker activated! Too many sequence errors ({self.consecutive_sequence_errors}). Cooling down...", self.wallet_id)
            await asyncio.sleep(5.0)
            # Force sequence refresh to recover
            await self.refresh_sequence(force=True)
            self.consecutive_sequence_errors = 0
            log(f"🔄 Circuit breaker reset, resuming trading", self.wallet_id)
        
        for attempt in range(max_retries):
            try:
                # Proactive sequence check before broadcasting
                if attempt == 0:
                    await self.proactive_sequence_check()
                
                # Use sequence lock to prevent concurrent broadcasts
                async with self.sequence_lock:
                    # Create batch update message - DERIVATIVES ONLY
                    msg = self.composer.msg_batch_update_orders(
                        sender=self.address.to_acc_bech32(),
                        spot_orders_to_create=[],  # No spot orders
                        derivative_orders_to_create=derivative_orders,
                        derivative_orders_to_cancel=derivative_orders_to_cancel,  # Cancel old orders
                        spot_orders_to_cancel=[]
                    )
                    
                    # Broadcast batch update
                    response = await self.broadcaster.broadcast([msg])
                    
                    # Extract TX hash and check for errors
                    tx_hash = (response.get('txhash') or 
                              response.get('txResponse', {}).get('txhash') or
                              response.get('tx_response', {}).get('txhash') or
                              'unknown')
                    
                    # Check for detailed transaction response
                    tx_response = response.get('txResponse') or response.get('tx_response')
                    if tx_response and 'logs' in tx_response:
                        # Log any events or errors in the transaction
                        logs = tx_response.get('logs', [])
                        for log_entry in logs:
                            if 'events' in log_entry:
                                for event in log_entry['events']:
                                    if event.get('type') == 'message' and 'action' in str(event):
                                        continue  # Skip routine message events
                                    elif 'error' in event.get('type', '').lower():
                                        log(f"⚠️ Transaction event: {event}", self.wallet_id)
                    
                    # Check for partial failures (some orders rejected)
                    if tx_response and tx_response.get('code', 0) != 0:
                        log(f"⚠️ Transaction had issues - Code: {tx_response.get('code')}, Log: {tx_response.get('raw_log', 'N/A')}", self.wallet_id)
                    
                    # Check for broadcast errors in response
                    tx_response = response.get('txResponse') or response.get('tx_response') or {}
                    code = tx_response.get('code', 0)
                    raw_log = tx_response.get('rawLog') or tx_response.get('raw_log', '')
                
                # Check if transaction was successful
                if tx_hash != 'unknown' and code == 0:
                    self.trading_stats['total_orders'] += total_orders
                    self.trading_stats['successful_orders'] += total_orders
                    self.trading_stats['total_transactions'] += 1
                    self.consecutive_sequence_errors = 0  # Reset error counter
                    
                    cancel_msg = f", cancelled {total_cancellations}" if total_cancellations > 0 else ""
                    
                    # Debug: Count order types for detailed logging
                    buy_orders = [o for o in derivative_orders if "BUY" in str(o)]
                    sell_orders = [o for o in derivative_orders if "SELL" in str(o)]
                    
                    log(f"✅ Placed {total_orders} orders ({len(spot_orders)} spot, {len(derivative_orders)} derivative: {len(buy_orders)} BUY + {len(sell_orders)} SELL{cancel_msg}) | TX: {tx_hash}", self.wallet_id)
                    
                    # Refresh sequence after success to stay in sync
                    await self.refresh_sequence()
                    return  # Success, exit function
                    
                elif code != 0:
                    # Transaction failed with error code
                    log(f"❌ Transaction failed (code {code}): {raw_log}", self.wallet_id)
                    self.trading_stats['failed_orders'] += total_orders
                    # Refresh sequence and retry
                    await self.refresh_sequence(force=True)
                    
                else:
                    log(f"❌ Failed to place {total_orders} orders: {response}", self.wallet_id)
                    self.trading_stats['failed_orders'] += total_orders
                    # Refresh sequence and retry
                    await self.refresh_sequence(force=True)
                    
            except Exception as e:
                error_str = str(e).lower()
                
                # Check if this is a sequence mismatch error
                if "sequence mismatch" in error_str or "incorrect account sequence" in error_str:
                    self.consecutive_sequence_errors += 1
                    self.trading_stats['sequence_errors'] += 1
                    
                    # Extract expected sequence from error if possible
                    expected_seq = self.extract_expected_sequence(str(e))
                    if expected_seq is not None:
                        log(f"🔧 Sequence mismatch detected! Blockchain expects: {expected_seq}, We had: {self.sequence}", self.wallet_id)
                        self.trading_stats['sequence_recoveries'] += 1
                    
                    log(f"⚠️ Sequence error (attempt {attempt + 1}/{max_retries})", self.wallet_id)
                    
                    # CRITICAL: Recreate broadcaster to reset its internal sequence
                    # Just refreshing sequence isn't enough - broadcaster has its own counter!
                    await self.recreate_broadcaster()
                    
                    # Exponential backoff with jitter
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                    await asyncio.sleep(delay)
                    
                    # Retry
                    continue
                    
                else:
                    # Non-sequence error
                    log(f"❌ Error sending batch orders (attempt {attempt + 1}/{max_retries}): {e}", self.wallet_id)
                    self.trading_stats['failed_orders'] += total_orders
                    
                    # Refresh sequence anyway (defensive)
                    await self.refresh_sequence(force=True)
                    
                    # Exponential backoff
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        await asyncio.sleep(delay)
                        continue
        
        # All retries exhausted
        log(f"❌ Failed to place orders after {max_retries} attempts", self.wallet_id)
        self.trading_stats['failed_orders'] += total_orders
    
    async def trade_market(self, market_symbol: str):
        """Trade on a specific market (spot or derivative)"""
        try:
            market_config = self.config["markets"][market_symbol]
            
            # Get market ID based on network
            market_id = market_config["testnet_market_id"]  # or mainnet_market_id
            
            # Check market type and place appropriate orders
            market_type = market_config.get("type", "spot")
            
            if market_type == "derivative":
                await self.place_derivative_orders(market_id, market_symbol, market_config)
            else:
                log(f"⚠️ Skipping non-derivative market: {market_symbol} (type: {market_type})", self.wallet_id)
            
        except Exception as e:
            log(f"❌ Error trading {market_symbol}: {e}", self.wallet_id)
    
    # SPOT ORDERS REMOVED - This is a derivatives-only trader
    
    async def place_derivative_orders(self, market_id: str, market_symbol: str, market_config: Dict):
        """Place derivative orders for a perpetual futures market"""
        try:
            # Get current price for derivatives
            price = await self.get_derivative_market_price(market_id, market_symbol)
            if not price:
                return
            
            # Calculate order parameters
            spread = market_config["spread_percent"] / 100
            order_size = Decimal(str(market_config["order_size"]))
            orders_per_market = self.config["wallets"][self.wallet_id]["trading_params"]["orders_per_market"]
            
            # Create buy and sell derivative orders
            orders = []
            for i in range(orders_per_market):
                # Calculate margin (typically a fraction of notional value)
                # For derivatives, margin = price * quantity * margin_ratio
                margin_ratio = Decimal("0.1")  # 10% margin requirement
                
                # Buy order (long position)
                buy_price = Decimal(str(price * (1 - spread * (i + 1))))
                buy_margin = buy_price * order_size * margin_ratio
                buy_order = self.composer.derivative_order(
                    market_id=market_id,
                    subaccount_id=self.address.get_subaccount_id(0),
                    fee_recipient=self.address.to_acc_bech32(),
                    price=buy_price,
                    quantity=order_size,
                    margin=buy_margin,
                    order_type="BUY",
                    cid=None
                )
                orders.append(buy_order)
                
                # Sell order (short position)
                sell_price = Decimal(str(price * (1 + spread * (i + 1))))
                sell_margin = sell_price * order_size * margin_ratio
                sell_order = self.composer.derivative_order(
                    market_id=market_id,
                    subaccount_id=self.address.get_subaccount_id(0),
                    fee_recipient=self.address.to_acc_bech32(),
                    price=sell_price,
                    quantity=order_size,
                    margin=sell_margin,
                    order_type="SELL",
                    cid=None
                )
                orders.append(sell_order)
            
            # Create batch update message for derivatives
            if orders:
                msg = self.composer.msg_batch_update_orders(
                    sender=self.address.to_acc_bech32(),
                    spot_orders_to_create=[],
                    derivative_orders_to_create=orders,
                    derivative_orders_to_cancel=[],
                    spot_orders_to_cancel=[]
                )
                
                # Broadcast batch update
                response = await self.broadcaster.broadcast([msg])
                tx_hash = (response.get('txhash') or 
                          response.get('txResponse', {}).get('txhash') or
                          response.get('tx_response', {}).get('txhash') or
                          'unknown')
                
                # Refresh sequence after successful transaction to prevent drift
                if tx_hash != 'unknown':
                    await self.refresh_sequence()
                
                # Check if successful and update statistics
                if tx_hash != 'unknown':
                    # Update statistics
                    self.trading_stats['total_orders'] += len(orders)
                    self.trading_stats['successful_orders'] += len(orders)
                    self.trading_stats['total_transactions'] += 1
                    
                    if market_symbol not in self.trading_stats['markets']:
                        self.trading_stats['markets'][market_symbol] = {'orders': 0, 'transactions': 0}
                    self.trading_stats['markets'][market_symbol]['orders'] += len(orders)
                    self.trading_stats['markets'][market_symbol]['transactions'] += 1
                    
                    log(f"✅ Placed {len(orders)} derivative orders on {market_symbol} | TX: {tx_hash}", self.wallet_id)
                else:
                    # Update failed statistics
                    self.trading_stats['failed_orders'] += len(orders) if orders else 1
                    log(f"❌ Failed to place derivative orders on {market_symbol}: {response}", self.wallet_id)
            
        except Exception as e:
            log(f"❌ Error placing derivative orders on {market_symbol}: {e}", self.wallet_id)
    
    async def recreate_broadcaster(self):
        """
        Recreate broadcaster to reset its internal sequence state
        This is the nuclear option for sequence recovery
        """
        try:
            log(f"🔄 Recreating broadcaster to reset sequence state...", self.wallet_id)
            
            # Fetch fresh account info
            await self.async_client.fetch_account(self.address.to_acc_bech32())
            self.sequence = self.async_client.sequence
            self.account_number = self.async_client.number
            
            # Recreate broadcaster with fresh sequence
            # Match the initialization logic - pass private_key string directly
            gas_price = await self.async_client.current_chain_gas_price()
            gas_price = int(gas_price * 1.3)  # Same gas price boost as initialization
            
            self.broadcaster = MsgBroadcasterWithPk.new_using_gas_heuristics(
                network=self.network,
                private_key=self.private_key,  # Pass string directly, SDK handles conversion
                gas_price=gas_price
            )
            
            # Confirm recreated broadcaster is using the K8s endpoint
            log(f"🚀 Recreated broadcaster using endpoint: {self.network.grpc_exchange_endpoint}", self.wallet_id)
            
            # Set same timeout as initialization
            self.broadcaster.timeout_height_offset = 300
            
            log(f"✅ Broadcaster recreated with sequence: {self.sequence}", self.wallet_id)
            
            # Give blockchain time to sync
            await asyncio.sleep(2.0)
            
        except Exception as e:
            log(f"❌ Failed to recreate broadcaster: {e}", self.wallet_id)
            raise
    
    async def refresh_sequence(self, force: bool = False):
        """
        Professional sequence refresh with locking and drift detection
        
        Args:
            force: Force refresh even if recently refreshed
        """
        async with self.sequence_lock:
            try:
                # Check if we need to refresh (throttle unnecessary refreshes)
                current_time = time.time()
                time_since_refresh = current_time - self.last_sequence_refresh
                
                if not force and time_since_refresh < 2.0:
                    # Too soon since last refresh, skip
                    return
                
                # Fetch account info from blockchain
                await self.async_client.fetch_account(self.address.to_acc_bech32())
                old_sequence = self.sequence
                self.sequence = self.async_client.sequence
                self.account_number = self.async_client.number
                self.last_sequence_refresh = current_time
                
                # Detect sequence drift
                if old_sequence != self.sequence:
                    drift = abs(self.sequence - old_sequence)
                    if drift > 1:
                        log(f"⚠️ Sequence drift detected: {old_sequence} → {self.sequence} (drift: {drift})", self.wallet_id)
                    else:
                        log(f"🔄 Sequence updated: {old_sequence} → {self.sequence}", self.wallet_id)
                
                # Reset error counter on successful refresh
                self.consecutive_sequence_errors = 0
                
                # Small delay to ensure blockchain sync
                await asyncio.sleep(0.5)
                
            except Exception as e:
                log(f"❌ Failed to refresh sequence: {e}", self.wallet_id)
                raise
    
    async def proactive_sequence_check(self):
        """Proactively refresh sequence if enough time has passed"""
        current_time = time.time()
        if current_time - self.last_sequence_refresh > self.sequence_refresh_interval:
            log(f"🔍 Proactive sequence refresh (30s interval)", self.wallet_id)
            await self.refresh_sequence(force=True)
    
    def extract_expected_sequence(self, error_message: str) -> Optional[int]:
        """Extract expected sequence number from error message"""
        try:
            # Parse error like: "expected 4227, got 4228"
            if "expected" in error_message.lower():
                parts = error_message.split("expected")
                if len(parts) > 1:
                    # Extract number after "expected"
                    expected_part = parts[1].split(",")[0].strip()
                    expected_seq = int(''.join(filter(str.isdigit, expected_part)))
                    return expected_seq
        except Exception:
            pass
        return None
    
    async def get_market_price(self, market_id: str, market_symbol: str = "") -> float:
        """Get current testnet market price using LAST TRADE PRICE (not orderbook mid-price)"""
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                # FIRST: Try to get last trade price (most accurate)
                try:
                    from pyinjective.client.model.pagination import PaginationOption
                    trades = await asyncio.wait_for(
                        self.indexer_client.fetch_spot_trades(
                            market_ids=[market_id],  # Filter by our specific market
                            pagination=PaginationOption(limit=1)  # Get only the most recent trade
                        ),
                        timeout=5.0
                    )
                    
                    if trades and 'trades' in trades and len(trades['trades']) > 0:
                        # Get the most recent trade (already filtered by market_id)
                        last_trade = trades['trades'][0]
                        price_value = last_trade.get('price', 0)
                        
                        # Handle different price formats (string, number, dict, etc.)
                        if isinstance(price_value, str):
                            trade_price = Decimal(price_value)
                        elif isinstance(price_value, (int, float)):
                            trade_price = Decimal(str(price_value))
                        elif isinstance(price_value, dict):
                            # Price might be in a nested structure, try common keys
                            if 'price' in price_value:
                                trade_price = Decimal(str(price_value['price']))
                            elif 'value' in price_value:
                                trade_price = Decimal(str(price_value['value']))
                            else:
                                # Try to extract the first numeric value
                                for key, value in price_value.items():
                                    if isinstance(value, (str, int, float)):
                                        trade_price = Decimal(str(value))
                                        break
                                else:
                                    raise Exception(f"Could not extract price from dict: {price_value}")
                        else:
                            raise Exception(f"Unexpected price format: {type(price_value)} - {price_value}")
                        
                        # Scale prices based on market type
                        if 'stinj' in market_symbol.lower():
                            price_scale_factor = Decimal('1')
                        else:
                            price_scale_factor = Decimal('1000000000000')  # 10^12
                        
                        last_trade_price = float(trade_price * price_scale_factor)
                        log(f"📈 Using LAST TRADE price: ${last_trade_price:.4f} for {market_symbol}", self.wallet_id, market_id)
                        return last_trade_price
                        
                except Exception as trade_error:
                    log(f"⚠️ Could not get last trade price: {trade_error}", self.wallet_id, market_id)
                
                # FALLBACK: Use orderbook mid-price if no recent trades
                orderbook = await asyncio.wait_for(
                    self.indexer_client.fetch_spot_orderbook_v2(market_id=market_id, depth=10),
                    timeout=10.0
                )
                
                if orderbook and 'orderbook' in orderbook:
                    buys = orderbook['orderbook'].get('buys', [])
                    sells = orderbook['orderbook'].get('sells', [])
                    
                    # Scale prices based on market type
                    if 'stinj' in market_symbol.lower():
                        price_scale_factor = Decimal('1')
                    else:
                        price_scale_factor = Decimal('1000000000000')  # 10^12
                    
                    # Handle different orderbook scenarios
                    if buys and sells:
                        # Both sides available - use mid price
                        best_bid = Decimal(str(buys[0]['price']))
                        best_ask = Decimal(str(sells[0]['price']))
                        best_bid_scaled = best_bid * price_scale_factor
                        best_ask_scaled = best_ask * price_scale_factor
                        mid_price = float((best_bid_scaled + best_ask_scaled) / 2)
                        log(f"📊 Using ORDERBOOK mid-price: ${mid_price:.4f} for {market_symbol}", self.wallet_id, market_id)
                        return mid_price
                    elif buys:
                        # Only buys available - use best bid
                        best_bid = Decimal(str(buys[0]['price']))
                        best_bid_scaled = best_bid * price_scale_factor
                        log(f"📊 Using best BID price: ${float(best_bid_scaled):.4f} for {market_symbol}", self.wallet_id, market_id)
                        return float(best_bid_scaled)
                    elif sells:
                        # Only sells available - use best ask
                        best_ask = Decimal(str(sells[0]['price']))
                        best_ask_scaled = best_ask * price_scale_factor
                        log(f"📊 Using best ASK price: ${float(best_ask_scaled):.4f} for {market_symbol}", self.wallet_id, market_id)
                        return float(best_ask_scaled)
                
                return 0.0
                
            except Exception as e:
                if attempt < max_retries - 1:
                    log(f"⚠️ Error getting market price (attempt {attempt + 1}/{max_retries}): {e}", self.wallet_id, market_id)
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    log(f"❌ Error getting market price after {max_retries} attempts: {e}", self.wallet_id, market_id)
                    return 0.0
    
    async def get_derivative_market_price(self, market_id: str, market_symbol: str = "") -> float:
        """Get current derivative market price using ORDERBOOK (most reliable)"""
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                # Use derivative orderbook for price discovery (most reliable)
                orderbook = await asyncio.wait_for(
                    self.indexer_client.fetch_derivative_orderbook_v2(market_id=market_id, depth=10),
                    timeout=10.0
                )
                
                if orderbook and 'orderbook' in orderbook:
                    buys = orderbook['orderbook'].get('buys', [])
                    sells = orderbook['orderbook'].get('sells', [])
                    
                    # Derivative prices need to be divided by 10^6
                    price_scale_factor = Decimal('1000000')  # 10^6 for derivatives
                    
                    if buys and sells:
                        # Both sides available - use mid price (most reliable)
                        best_bid = Decimal(str(buys[0]['price'])) / price_scale_factor
                        best_ask = Decimal(str(sells[0]['price'])) / price_scale_factor
                        mid_price = float((best_bid + best_ask) / 2)
                        log(f"📊 Using DERIVATIVE ORDERBOOK mid-price: ${mid_price:.4f} for {market_symbol}", self.wallet_id, market_id)
                        return mid_price
                    else:
                        # ONE-SIDED ORDERBOOK: Get last trade price instead (more reliable than one side)
                        log(f"⚠️ One-sided orderbook detected, fetching last trade price...", self.wallet_id, market_id)
                        from pyinjective.client.model.pagination import PaginationOption
                        try:
                            trades = await asyncio.wait_for(
                                self.indexer_client.fetch_derivative_trades(
                                    market_ids=[market_id],
                                    pagination=PaginationOption(limit=1)
                                ),
                                timeout=5.0
                            )
                            if trades and hasattr(trades, 'trades') and len(trades.trades) > 0:
                                last_trade = trades.trades[0]
                                trade_price = float(Decimal(str(last_trade.position_delta.execution_price)))
                                log(f"📊 Using last TRADE price: ${trade_price:.4f} for {market_symbol}", self.wallet_id, market_id)
                                return trade_price
                        except Exception as trade_err:
                            log(f"⚠️ Could not fetch last trade: {trade_err}", self.wallet_id, market_id)
                        
                        # Fallback to one side if trade fetch fails
                        if buys:
                            best_bid = Decimal(str(buys[0]['price'])) / price_scale_factor
                            log(f"📊 Fallback to best BID: ${float(best_bid):.4f} for {market_symbol}", self.wallet_id, market_id)
                            return float(best_bid)
                        elif sells:
                            best_ask = Decimal(str(sells[0]['price'])) / price_scale_factor
                            log(f"📊 Fallback to best ASK: ${float(best_ask):.4f} for {market_symbol}", self.wallet_id, market_id)
                            return float(best_ask)
                
                return 0.0
                
            except Exception as e:
                if attempt < max_retries - 1:
                    log(f"⚠️ Error getting derivative market price (attempt {attempt + 1}/{max_retries}): {e}", self.wallet_id, market_id)
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    log(f"❌ Error getting derivative market price after {max_retries} attempts: {e}", self.wallet_id, market_id)
                    return 0.0
    
    async def get_mainnet_price(self, market_symbol: str, mainnet_market_id: str = None) -> float:
        """Get current mainnet market price for price discovery"""
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                from pyinjective.core.network import Network
                from pyinjective.indexer_client import IndexerClient
                
                mainnet_network = Network.mainnet()
                mainnet_indexer = IndexerClient(mainnet_network)
                
                if mainnet_market_id:
                    market_id = mainnet_market_id
                else:
                    # Search for market ID by symbol
                    markets_response = await asyncio.wait_for(
                        mainnet_indexer.fetch_spot_markets(),
                        timeout=10.0
                    )
                    
                    if not markets_response or 'markets' not in markets_response:
                        return 0.0
                    
                    # Find market by base/quote symbols (like working bot)
                    market_id = None
                    for market in markets_response['markets']:
                        base_symbol = market.get('baseTokenMeta', {}).get('symbol', '')
                        quote_symbol = market.get('quoteTokenMeta', {}).get('symbol', '')
                        
                        if (base_symbol.upper() == market_symbol.split('/')[0].upper() and 
                            quote_symbol.upper() == market_symbol.split('/')[1].upper()):
                            market_id = market.get('marketId')  # Use camelCase like working bot
                            break
                    
                    if not market_id:
                        log(f"⚠️ Mainnet market not found for {market_symbol}", self.wallet_id)
                        return 0.0
                
                # Get mainnet orderbook
                orderbook = await asyncio.wait_for(
                    mainnet_indexer.fetch_spot_orderbook_v2(market_id=market_id, depth=10),
                    timeout=10.0
                )
                
                if orderbook and 'orderbook' in orderbook:
                    buys = orderbook['orderbook'].get('buys', [])
                    sells = orderbook['orderbook'].get('sells', [])
                    
                    # Mainnet spot price scaling (from working bot)
                    if 'stinj' in market_symbol.lower():
                        price_scale_factor = Decimal('1')  # No scaling for stINJ
                    else:
                        price_scale_factor = Decimal('1000000000000')  # 10^12 for other markets
                    
                    if buys and sells:
                        # Both sides available - use mid price
                        best_bid = Decimal(str(buys[0]['price']))
                        best_ask = Decimal(str(sells[0]['price']))
                        best_bid_scaled = best_bid * price_scale_factor
                        best_ask_scaled = best_ask * price_scale_factor
                        mid_price = float((best_bid_scaled + best_ask_scaled) / 2)
                        return mid_price
                    elif buys:
                        # Only buys available - use best bid
                        best_bid = Decimal(str(buys[0]['price']))
                        best_bid_scaled = best_bid * price_scale_factor
                        return float(best_bid_scaled)
                    elif sells:
                        # Only sells available - use best ask
                        best_ask = Decimal(str(sells[0]['price']))
                        best_ask_scaled = best_ask * price_scale_factor
                        return float(best_ask_scaled)
                
                return 0.0
                
            except Exception as e:
                if attempt < max_retries - 1:
                    log(f"⚠️ Error getting mainnet price (attempt {attempt + 1}/{max_retries}): {e}", self.wallet_id)
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    log(f"❌ Error getting mainnet price after {max_retries} attempts: {e}", self.wallet_id)
                    return 0.0

    async def get_mainnet_derivative_price(self, market_symbol: str, mainnet_market_id: str = None) -> float:
        """Get current mainnet derivative market price for price discovery"""
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                from pyinjective.core.network import Network
                from pyinjective.indexer_client import IndexerClient
                
                mainnet_network = Network.mainnet()
                mainnet_indexer = IndexerClient(mainnet_network)
                
                if mainnet_market_id:
                    market_id = mainnet_market_id
                else:
                    # Search for derivative market ID by ticker
                    markets_response = await asyncio.wait_for(
                        mainnet_indexer.fetch_derivative_markets(),
                        timeout=10.0
                    )
                    
                    if not markets_response or 'markets' not in markets_response:
                        return 0.0
                    
                    # Find derivative market by ticker (derivatives use ticker field)
                    market_id = None
                    for market in markets_response['markets']:
                        if market.get('ticker') == market_symbol:
                            market_id = market.get('marketId')  # Use camelCase like working bot
                            break
                    
                    if not market_id:
                        log(f"⚠️ Mainnet derivative market not found for {market_symbol}", self.wallet_id)
                        return 0.0
                
                # Use orderbook for mainnet price (most reliable)
                orderbook = await asyncio.wait_for(
                    mainnet_indexer.fetch_derivative_orderbook_v2(market_id=market_id, depth=10),
                    timeout=10.0
                )
                
                if orderbook and 'orderbook' in orderbook:
                    buys = orderbook['orderbook'].get('buys', [])
                    sells = orderbook['orderbook'].get('sells', [])
                    
                    # Mainnet derivative price scaling (divide by 10^6)
                    price_scale_factor = Decimal('1000000')  # 10^6
                    
                    if buys and sells:
                        # Both sides available - use mid price
                        best_bid = Decimal(str(buys[0]['price']))
                        best_ask = Decimal(str(sells[0]['price']))
                        best_bid_scaled = best_bid / price_scale_factor
                        best_ask_scaled = best_ask / price_scale_factor
                        mid_price = float((best_bid_scaled + best_ask_scaled) / 2)
                        return mid_price
                    elif buys:
                        # Only buys available - use best bid
                        best_bid = Decimal(str(buys[0]['price']))
                        best_bid_scaled = best_bid / price_scale_factor
                        return float(best_bid_scaled)
                    elif sells:
                        # Only sells available - use best ask
                        best_ask = Decimal(str(sells[0]['price']))
                        best_ask_scaled = best_ask / price_scale_factor
                        return float(best_ask_scaled)
                
                return 0.0
                
            except Exception as e:
                if attempt < max_retries - 1:
                    log(f"⚠️ Error getting mainnet derivative price (attempt {attempt + 1}/{max_retries}): {e}", self.wallet_id)
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    log(f"❌ Error getting mainnet derivative price after {max_retries} attempts: {e}", self.wallet_id)
                    return 0.0
    
    def get_trading_summary(self) -> str:
        """Get trading summary"""
        runtime = time.time() - self.start_time
        hours, remainder = divmod(runtime, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        summary = f"\n{'='*60}\n"
        summary += f"📊 TRADING SUMMARY - {self.wallet_id.upper()}\n"
        summary += f"{'='*60}\n"
        summary += f"⏱️  Runtime: {int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}\n"
        summary += f"📦 Total Orders: {self.trading_stats['total_orders']}\n"
        summary += f"✅ Successful: {self.trading_stats['successful_orders']}\n"
        summary += f"❌ Failed: {self.trading_stats['failed_orders']}\n"
        summary += f"🔄 Total Transactions: {self.trading_stats['total_transactions']}\n"
        
        if self.trading_stats['markets']:
            summary += f"\n📈 Per Market:\n"
            for market, stats in self.trading_stats['markets'].items():
                summary += f"  {market}: {stats['orders']} orders, {stats['transactions']} transactions\n"
        
        summary += f"{'='*60}"
        return summary

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Single Wallet Derivative Trader - Trade on Injective Protocol derivative markets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all configured markets for wallet_1
  python derivative_trader.py wallet_1
  
  # Run specific markets only
  python derivative_trader.py wallet_1 --markets INJ/USDT-PERP BTC/USDT-PERP
  
  # Show available markets for a wallet
  python derivative_trader.py wallet_1 --list-markets
        """
    )
    
    parser.add_argument(
        'wallet_id',
        help='Wallet ID to use for trading (e.g., wallet_1, wallet_2, wallet_3)'
    )
    
    parser.add_argument(
        '--markets', '-m',
        nargs='+',
        help='Specific markets to trade on (space-separated). If not specified, trades on all configured markets.'
    )
    
    parser.add_argument(
        '--list-markets', '-l',
        action='store_true',
        help='List available markets for the specified wallet and exit'
    )
    
    return parser.parse_args()

async def main():
    """Main entry point"""
    args = parse_arguments()
    
    # Create trader instance to access config
    try:
        trader = SingleWalletTrader(args.wallet_id, selected_markets=args.markets)
    except ValueError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to initialize trader: {e}")
        sys.exit(1)
    
    # Handle list-markets option
    if args.list_markets:
        wallet_config = trader.config["wallets"][args.wallet_id]
        all_markets = wallet_config["markets"]
        
        print(f"\n📊 Available markets for {args.wallet_id}:")
        for market in all_markets:
            market_config = trader.config["markets"][market]
            market_type = market_config.get("type", "spot")
            spread = market_config.get("spread_percent", 0)
            order_size = market_config.get("order_size", 0)
            print(f"  • {market} ({market_type}) - Spread: {spread}%, Order Size: {order_size}")
        
        # Show derivative markets specifically
        derivative_markets = [m for m in all_markets if trader.config["markets"][m].get("type") == "derivative"]
        if derivative_markets:
            print(f"\n🎯 Derivative markets: {', '.join(derivative_markets)}")
        else:
            print(f"\n⚠️  No derivative markets configured for {args.wallet_id}")
        
        return
    
    # Validate selected markets if provided
    if args.markets:
        wallet_config = trader.config["wallets"][args.wallet_id]
        all_markets = wallet_config["markets"]
        invalid_markets = [m for m in args.markets if m not in all_markets]
        
        if invalid_markets:
            print(f"❌ Invalid markets: {invalid_markets}")
            print(f"Available markets for {args.wallet_id}: {all_markets}")
            sys.exit(1)
        
        # Check if any selected markets are derivatives
        derivative_markets = [m for m in args.markets if trader.config["markets"][m].get("type") == "derivative"]
        if not derivative_markets:
            print(f"⚠️  Warning: None of the selected markets are derivative markets: {args.markets}")
            print("This trader is optimized for derivative trading.")
            response = input("Continue anyway? (y/N): ")
            if response.lower() != 'y':
                sys.exit(0)
    
    # Start trading
    try:
        print(f"🚀 Starting derivative trader for {args.wallet_id}")
        if args.markets:
            print(f"🎯 Selected markets: {args.markets}")
        else:
            wallet_config = trader.config["wallets"][args.wallet_id]
            print(f"🎯 All configured markets: {wallet_config['markets']}")
        
        await trader.run()
    except KeyboardInterrupt:
        log(f"🛑 {args.wallet_id} trader stopped by user", args.wallet_id)
        # Show trading summary
        summary = trader.get_trading_summary()
        print(summary)
        log(f"📊 Trading session ended for {args.wallet_id}", args.wallet_id)

if __name__ == "__main__":
    asyncio.run(main())
