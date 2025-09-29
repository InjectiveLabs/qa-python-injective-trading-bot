#!/usr/bin/env python3
"""
Single Wallet Trader - Future replacement for enhanced_multi_wallet_trader.py
Handles one wallet trading on all configured markets
"""

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
    def __init__(self, wallet_id: str, config_path: str = "config/trader_config.json"):
        self.wallet_id = wallet_id
        self.config_path = config_path
        self.config = self.load_config()
        
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
        
        # Initialize network 
        self.network = Network.testnet()
        
        # Initialize client and other attributes (will be set in initialize())
        self.async_client = None
        self.composer = None
        self.address = None
        self.broadcaster = None
        self.sequence = 0
        self.account_number = 0
        
        # Trading state
        self.active_orders = {}
        self.last_prices = {}
        self.last_rebalance = 0
        
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
            
            # Set timeout height offset for network congestion (increased for better reliability)
            self.broadcaster.timeout_height_offset = 120  # Increased from 60 to 120 blocks
            
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
                markets = wallet_config["markets"]
                
                # Trade on ALL markets in a single batch transaction
                await self.trade_all_markets_batch(markets)
                
                # Wait before next cycle
                await asyncio.sleep(15)
                
            except Exception as e:
                log(f"❌ Error in trading loop: {e}", self.wallet_id)
                await asyncio.sleep(5)
    
    async def trade_all_markets_batch(self, markets: list):
        """Trade on all markets in a single batch transaction"""
        try:
            # Collect all orders for DERIVATIVE markets ONLY
            spot_orders = []
            derivative_orders = []
            
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
                market_derivative_orders = await self.create_derivative_orders(market_id, market_symbol, market_config, price)
                derivative_orders.extend(market_derivative_orders)
            
            # If we have orders, send them in one batch transaction
            if spot_orders or derivative_orders:
                await self.send_batch_orders(spot_orders, derivative_orders)
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
                
                # ALWAYS CREATE BEAUTIFUL ORDERBOOK AT MAINNET PRICE
                # Ignore current testnet orderbook - we're making the market!
                log(f"✨ Creating beautiful orderbook at mainnet price ${mainnet_price:.4f} (current testnet: ${price:.4f}, gap: {price_gap_percent:.2f}%)", self.wallet_id)
                return await self.create_beautiful_orderbook(market_id, market_symbol, market_config, price, mainnet_price)
            else:
                # Can't get mainnet price - use testnet price as fallback
                log(f"⚠️ No mainnet price available - creating orderbook at testnet price ${price:.4f}", self.wallet_id)
                return await self.create_beautiful_orderbook(market_id, market_symbol, market_config, price, price)
                
        except Exception as e:
            log(f"❌ Error creating derivative orders for {market_symbol}: {e}", self.wallet_id)
            
        return orders
    
    async def create_beautiful_orderbook(self, market_id: str, market_symbol: str, market_config: Dict, 
                                         testnet_price: float, mainnet_price: float) -> list:
        """
        Create a beautiful, natural-looking orderbook with deep liquidity
        Used when prices are aligned (< 2% difference)
        """
        orders = []
        try:
            order_size = Decimal(str(market_config["order_size"]))
            margin_ratio = Decimal("0.1")
            
            # Use mainnet price as the center for orderbook
            center_price = mainnet_price
            
            # Create multi-tiered orderbook with natural distribution
            liquidity_tiers = [
                # (spread_percent, num_orders, size_multiplier, priority)
                (0.001, 3, 1.5, "immediate"),    # Tier 1: Micro spread (0.1%) - tight liquidity
                (0.005, 3, 1.2, "immediate"),    # Tier 2: Tight spread (0.5%)
                (0.01, 2, 1.0, "immediate"),     # Tier 3: Normal spread (1%)
                (0.02, 2, 0.8, "secondary"),     # Tier 4: Medium spread (2%)
                (0.03, 2, 0.6, "secondary"),     # Tier 5: Wide spread (3%)
                (0.05, 2, 0.5, "tertiary"),      # Tier 6: Very wide (5%)
            ]
            
            for spread_pct, num_orders, size_mult, priority in liquidity_tiers:
                for i in range(num_orders):
                    # Add randomness for natural look
                    spread_variation = random.uniform(0.9, 1.1)
                    actual_spread = spread_pct * spread_variation
                    size_variation = random.uniform(0.85, 1.15)
                    actual_size = order_size * Decimal(str(size_mult * size_variation))
                    # Round quantity to avoid decimal precision issues
                    actual_size = actual_size.quantize(Decimal('0.001'))
                    
                    # Calculate buy and sell prices
                    offset = actual_spread * (i + 1)
                    buy_price = Decimal(str(center_price * (1 - offset)))
                    sell_price = Decimal(str(center_price * (1 + offset)))
                    
                    # Smart rounding based on price level for natural look
                    if buy_price > 10:
                        buy_price = buy_price.quantize(Decimal('0.0001'))
                        sell_price = sell_price.quantize(Decimal('0.0001'))
                    else:
                        buy_price = buy_price.quantize(Decimal('0.00001'))
                        sell_price = sell_price.quantize(Decimal('0.00001'))
                    
                    # Create buy order
                    buy_margin = buy_price * actual_size * margin_ratio
                    # Round margin to avoid decimal precision issues with blockchain
                    buy_margin = buy_margin.quantize(Decimal('0.01'))
                    buy_order = self.composer.derivative_order(
                        market_id=market_id,
                        subaccount_id=self.address.get_subaccount_id(0),
                        fee_recipient=self.address.to_acc_bech32(),
                        price=buy_price,
                        quantity=actual_size,
                        margin=buy_margin,
                        order_type="BUY",
                        cid=None
                    )
                    orders.append(buy_order)
                    
                    # Create sell order
                    sell_margin = sell_price * actual_size * margin_ratio
                    # Round margin to avoid decimal precision issues with blockchain
                    sell_margin = sell_margin.quantize(Decimal('0.01'))
                    sell_order = self.composer.derivative_order(
                        market_id=market_id,
                        subaccount_id=self.address.get_subaccount_id(0),
                        fee_recipient=self.address.to_acc_bech32(),
                        price=sell_price,
                        quantity=actual_size,
                        margin=sell_margin,
                        order_type="SELL",
                        cid=None
                    )
                    orders.append(sell_order)
            
            log(f"📖 Created beautiful orderbook with {len(orders)} orders across {len(liquidity_tiers)} tiers", self.wallet_id)
            
        except Exception as e:
            log(f"❌ Error creating beautiful orderbook for {market_symbol}: {e}", self.wallet_id)
            
        return orders
    
    async def send_batch_orders(self, spot_orders: list, derivative_orders: list):
        """
        Professional batch order sender with intelligent sequence recovery
        
        Features:
        - Automatic retry with exponential backoff
        - Intelligent sequence error detection and recovery
        - Circuit breaker for persistent failures
        - Proactive sequence refresh
        """
        total_orders = len(spot_orders) + len(derivative_orders)
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
                        derivative_orders_to_cancel=[],
                        spot_orders_to_cancel=[]
                    )
                    
                    # Broadcast batch update
                    response = await self.broadcaster.broadcast([msg])
                    
                    # Extract TX hash and check for errors
                    tx_hash = (response.get('txhash') or 
                              response.get('txResponse', {}).get('txhash') or
                              response.get('tx_response', {}).get('txhash') or
                              'unknown')
                    
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
                    
                    log(f"✅ Placed {total_orders} orders ({len(spot_orders)} spot, {len(derivative_orders)} derivative) | TX: {tx_hash}", self.wallet_id)
                    
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
                        # Both sides available - use mid price
                        best_bid = Decimal(str(buys[0]['price'])) / price_scale_factor
                        best_ask = Decimal(str(sells[0]['price'])) / price_scale_factor
                        mid_price = float((best_bid + best_ask) / 2)
                        log(f"📊 Using DERIVATIVE ORDERBOOK mid-price: ${mid_price:.4f} for {market_symbol}", self.wallet_id, market_id)
                        return mid_price
                    elif buys:
                        # Only buys available - use best bid
                        best_bid = Decimal(str(buys[0]['price'])) / price_scale_factor
                        log(f"📊 Using derivative best BID price: ${float(best_bid):.4f} for {market_symbol}", self.wallet_id, market_id)
                        return float(best_bid)
                    elif sells:
                        # Only sells available - use best ask
                        best_ask = Decimal(str(sells[0]['price'])) / price_scale_factor
                        log(f"📊 Using derivative best ASK price: ${float(best_ask):.4f} for {market_symbol}", self.wallet_id, market_id)
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

async def main():
    """Main entry point"""
    if len(sys.argv) != 2:
        print("Usage: python trader.py <wallet_id>")
        sys.exit(1)
    
    wallet_id = sys.argv[1]
    trader = SingleWalletTrader(wallet_id)
    
    try:
        await trader.run()
    except KeyboardInterrupt:
        log(f"🛑 {wallet_id} trader stopped by user", wallet_id)
        # Show trading summary
        summary = trader.get_trading_summary()
        print(summary)
        log(f"📊 Trading session ended for {wallet_id}", wallet_id)

if __name__ == "__main__":
    asyncio.run(main())
