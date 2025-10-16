#!/usr/bin/env python3
"""
Enhanced Spot Trader - Beautiful orderbook creation for spot markets
Handles one wallet trading on spot markets with sophisticated liquidity building
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
from logging.handlers import TimedRotatingFileHandler

from pyinjective.async_client_v2 import AsyncClient
from pyinjective.indexer_client import IndexerClient
from pyinjective.core.network import Network
from pyinjective.core.broadcaster import MsgBroadcasterWithPk
from pyinjective import PrivateKey, Address

# Add project root to path (works both from repo and inside Docker image)
_here = Path(__file__).resolve()
_parents = _here.parents
_candidates = []
if len(_parents) >= 3:
    # When run from repo at scripts/bots/*.py → repo root is parents[2]
    _candidates.append(_parents[2])
# When run inside Docker image → file is at /app/spot_trader.py → root is parent
_candidates.append(_here.parent)
for _p in _candidates:
    if (_p / "utils").exists():
        sys.path.append(str(_p))
        break

from utils.secure_wallet_loader import load_wallets_from_env

# Configure daily rotating file logger
os.makedirs("logs", exist_ok=True)

# Create logger
_logger = logging.getLogger('spot_trader')
_logger.setLevel(logging.INFO)

# Daily rotating file handler - new file at midnight, keep 7 days
file_handler = TimedRotatingFileHandler(
    'logs/spot_trader.log',
    when='midnight',      # Rotate at midnight
    interval=1,           # Every 1 day
    backupCount=7,        # Keep 7 days of logs
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
# Add date suffix to rotated files (e.g., spot_trader.log.2025-10-01)
file_handler.suffix = "%Y-%m-%d"

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)

# Format: [timestamp] [wallet_id] message
formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

_logger.addHandler(file_handler)
_logger.addHandler(console_handler)

def log(message: str, wallet_id: str = None, market_id: str = None):
    """Enhanced logging with wallet and market context + rotation"""
    prefix = f"[{wallet_id}]" if wallet_id else ""
    if market_id:
        prefix += f"[{market_id}]"
    if prefix:
        prefix += " "
    
    formatted_message = f"{prefix}{message}"
    _logger.info(formatted_message)

class EnhancedSpotTrader:
    def __init__(self, wallet_id: str, target_market: str = None, 
                 config_path: str = "config/trader_config.json",
                 markets_config_path: str = "config/markets_config.json"):
        self.wallet_id = wallet_id
        self.target_market = target_market  # Optional: specific market to trade
        self.config_path = config_path
        self.markets_config_path = markets_config_path
        self.config = self.load_config()
        self.markets_config = self.load_markets_config()
        
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
        
        # Initialize network with custom testnet endpoint and failover state
        self.network = Network.testnet()
        # Default (fallback) testnet exchange indexer endpoint from SDK
        self.default_exchange_endpoint = Network.testnet().grpc_exchange_endpoint
        # Preferred primary indexer endpoint (k8s)
        self.primary_exchange_endpoint = "k8s.testnet.exchange.grpc.injective.network:443"
        # Start on primary and point network to current
        self.current_exchange_endpoint = self.primary_exchange_endpoint
        self.network.grpc_exchange_endpoint = self.current_exchange_endpoint
        log(f"🔧 Using custom testnet endpoint: {self.network.grpc_exchange_endpoint}", self.wallet_id)
        # Failover bookkeeping
        self._on_primary_indexer = True
        self._last_indexer_switch_ts = 0.0
        self._primary_retry_interval_sec = 120  # retry primary every 2 minutes while on fallback
        self._indexer_error_count = 0  # Track consecutive errors
        self._max_indexer_errors = 3  # Switch after 3 consecutive errors
        
        # Initialize client and other attributes (will be set in initialize())
        self.async_client = None
        self.indexer_client = None
        self.composer = None
        self.address = None
        self.broadcaster = None
        self.sequence = 0
        self.account_number = 0
        
        # Trading state
        self.active_orders = {}  # market_id -> list of order hashes
        self.last_prices = {}
        self.orderbook_depth_stage = {}  # market_id -> int (tracks how far out we've built)
        self.orderbook_depth_built = {}  # market_id -> int (tracks total orders in book)
        self.last_orderbook_check = {}  # market_id -> timestamp of last depth check
        
        # Market metadata cache for proper price scaling
        self.market_metadata = {}  # market_id -> {base_decimals, quote_decimals, etc}
        
        # Force chain-based queries (for testing/bypassing indexer issues)
        self.force_chain_queries = os.getenv('FORCE_CHAIN_QUERIES', 'false').lower() == 'true'
        if self.force_chain_queries:
            log(f"⚠️ FORCE_CHAIN_QUERIES enabled - will query chain directly, bypassing indexer", self.wallet_id)
        
        # Professional sequence management
        self.sequence_lock = asyncio.Lock()
        self.consecutive_sequence_errors = 0
        self.max_sequence_errors = 5
        self.last_sequence_refresh = 0
        
        # Trading statistics
        self.trading_stats = {
            'total_orders': 0,
            'successful_orders': 0,
            'failed_orders': 0,
            'total_transactions': 0,
            'sequence_errors': 0,
            'markets': {}
        }
        self.start_time = time.time()
        
    def load_config(self) -> Dict:
        """Load trader configuration from file"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            log(f"❌ Failed to load trader config: {e}", self.wallet_id)
            sys.exit(1)
    
    def load_markets_config(self) -> Dict:
        """Load markets configuration from file"""
        try:
            with open(self.markets_config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            log(f"❌ Failed to load markets config: {e}", self.wallet_id)
            sys.exit(1)
    
    async def initialize(self):
        """Initialize the trader"""
        try:
            log(f"🚀 Initializing Enhanced Spot Trader for {self.wallet_id}", self.wallet_id)
            
            # Create clients
            self.async_client = AsyncClient(self.network)
            self.indexer_client = IndexerClient(self.network)
            self.composer = await self.async_client.composer()
            
            # Set up wallet identity
            private_key_obj = PrivateKey.from_hex(self.private_key)
            self.address = private_key_obj.to_public_key().to_address()
            
            # Log wallet identity for order tracking
            log(f"🔑 Wallet Address: {self.address.to_acc_bech32()}", self.wallet_id)
            log(f"🔑 Subaccount ID: {self.address.get_subaccount_id(0)}", self.wallet_id)
            
            # Initialize account and reset sequence to prevent mismatch
            await self.async_client.fetch_account(self.address.to_acc_bech32())
            self.sequence = self.async_client.sequence
            self.account_number = self.async_client.number
            
            # Force sequence refresh to ensure we're in sync
            await self.refresh_sequence()
            log(f"🔄 Sequence synchronized: {self.sequence}", self.wallet_id)
            
            # Initialize broadcaster with enhanced settings
            gas_price = await self.async_client.current_chain_gas_price()
            gas_price = int(gas_price * 1.3)
            
            self.broadcaster = MsgBroadcasterWithPk.new_using_gas_heuristics(
                network=self.network,
                private_key=self.private_key,
                gas_price=gas_price
            )
            
            self.broadcaster.timeout_height_offset = 120
            
            if self.target_market:
                log(f"✅ Enhanced Spot Trader initialized for market: {self.target_market}", self.wallet_id)
            else:
                log(f"✅ Enhanced Spot Trader initialized for all enabled spot markets", self.wallet_id)
            
        except Exception as e:
            log(f"❌ Failed to initialize {self.wallet_id}: {e}", self.wallet_id)
            raise
    
    async def _switch_indexer_endpoint(self, new_endpoint: str):
        """Switch indexer gRPC endpoint safely, recreating client channels."""
        if self.network.grpc_exchange_endpoint == new_endpoint:
            return
        try:
            if getattr(self, "indexer_client", None) is not None:
                try:
                    await self.indexer_client.close_exchange_channel()
                    await self.indexer_client.close_explorer_channel()
                except Exception:
                    pass
            self.network.grpc_exchange_endpoint = new_endpoint
            self.indexer_client = IndexerClient(self.network)
            self.current_exchange_endpoint = new_endpoint
            self._last_indexer_switch_ts = time.time()
            log(f"🔀 Switched indexer endpoint → {new_endpoint}", self.wallet_id)
        except Exception as e:
            log(f"❌ Failed switching indexer endpoint to {new_endpoint}: {e}", self.wallet_id)
            raise

    async def fetch_spot_orderbook_v2_failover(self, market_id: str, depth: int, force_chain: bool = False) -> dict:
        """
        Fetch spot orderbook v2 with automatic endpoint failover and primary retries.
        This catches ANY error, not just specific ones, and fails over to keep trading.
        
        Args:
            market_id: Market ID to fetch orderbook for
            depth: Orderbook depth
            force_chain: If True, skip indexer and query chain directly (for testing)
        """
        # For testing: Force chain-based query
        if force_chain:
            log(f"🔗 FORCE CHAIN MODE: Querying orderbook directly from chain...", self.wallet_id)
            try:
                chain_orderbook = await self.async_client.fetch_chain_spot_orderbook(market_id=market_id)
                if chain_orderbook:
                    # Chain returns different format - convert to indexer format
                    buys_raw = chain_orderbook.get('buysPriceLevel', [])
                    sells_raw = chain_orderbook.get('sellsPriceLevel', [])
                    
                    buys = [{'price': level['p'], 'quantity': level['q']} for level in buys_raw]
                    sells = [{'price': level['p'], 'quantity': level['q']} for level in sells_raw]
                    
                    converted_orderbook = {
                        'orderbook': {
                            'buys': buys,
                            'sells': sells
                        }
                    }
                    
                    log(f"✅ Chain query successful! ({len(buys)} bids, {len(sells)} asks)", self.wallet_id)
                    return converted_orderbook
                else:
                    log(f"⚠️ Chain query returned no data", self.wallet_id)
                    return None
            except Exception as e:
                log(f"❌ Chain query failed: {e}", self.wallet_id)
                return None
        
        # While on fallback, occasionally probe the primary and switch back if possible
        if not self._on_primary_indexer and time.time() - self._last_indexer_switch_ts > self._primary_retry_interval_sec:
            try:
                log(f"🔄 Probing primary k8s endpoint to see if it's back online...", self.wallet_id)
                await self._switch_indexer_endpoint(self.primary_exchange_endpoint)
                self._on_primary_indexer = True
                self._indexer_error_count = 0  # Reset error counter
            except Exception as e:
                log(f"⚠️ Primary endpoint still unavailable: {e}", self.wallet_id)
                # Switch back to fallback if probe failed
                await self._switch_indexer_endpoint(self.default_exchange_endpoint)
                self._on_primary_indexer = False

        # Try current endpoint first
        try:
            result = await self.indexer_client.fetch_spot_orderbook_v2(market_id=market_id, depth=depth)
            # Success! Reset error counter
            self._indexer_error_count = 0
            return result
        except Exception as e:
            # Increment error counter
            self._indexer_error_count += 1
            
            # If we're on primary and hitting errors, consider failover
            if self._on_primary_indexer and self._indexer_error_count >= self._max_indexer_errors:
                # Log the full error details for the dev team
                log(f"⚠️ K8S INDEXER FAILURE DETECTED ({self._indexer_error_count} consecutive errors) - Full error details:", self.wallet_id)
                log(f"❌ Error Type: {type(e).__name__}", self.wallet_id)
                log(f"❌ Error Message: {str(e)}", self.wallet_id)
                log(f"❌ Failed Endpoint: {self.primary_exchange_endpoint}", self.wallet_id)
                log(f"❌ Market ID: {market_id}", self.wallet_id)
                log(f"🔀 Failing over to default testnet endpoint: {self.default_exchange_endpoint}", self.wallet_id)
                
                # Switch to fallback
                await self._switch_indexer_endpoint(self.default_exchange_endpoint)
                self._on_primary_indexer = False
                self._indexer_error_count = 0  # Reset counter after switch
                
                # Retry once on fallback
                try:
                    return await self.indexer_client.fetch_spot_orderbook_v2(market_id=market_id, depth=depth)
                except Exception as fallback_error:
                    log(f"❌ Fallback indexer endpoint also failed: {fallback_error}", self.wallet_id)
                    # Fall through to try chain-based query
            else:
                # Either not on primary, or haven't hit error threshold yet
                if self._on_primary_indexer:
                    log(f"⚠️ Indexer error {self._indexer_error_count}/{self._max_indexer_errors} on primary: {type(e).__name__}", self.wallet_id)
                # If not at threshold, raise immediately
                if self._indexer_error_count < self._max_indexer_errors:
                    raise
        
        # LAST RESORT: Chain-based orderbook query (bypasses indexer entirely)
        try:
            log(f"🔗 CHAIN FALLBACK: Querying orderbook directly from chain (bypassing indexer)...", self.wallet_id)
            chain_orderbook = await self.async_client.fetch_chain_spot_orderbook(market_id=market_id)
            
            if chain_orderbook:
                # Chain returns different format: {buysPriceLevel: [{p, q}], sellsPriceLevel: [{p, q}]}
                # Convert to indexer format: {orderbook: {buys: [{price, quantity}], sells: [{price, quantity}]}}
                buys_raw = chain_orderbook.get('buysPriceLevel', [])
                sells_raw = chain_orderbook.get('sellsPriceLevel', [])
                
                # Convert format
                buys = [{'price': level['p'], 'quantity': level['q']} for level in buys_raw]
                sells = [{'price': level['p'], 'quantity': level['q']} for level in sells_raw]
                
                converted_orderbook = {
                    'orderbook': {
                        'buys': buys,
                        'sells': sells
                    }
                }
                
                log(f"✅ Successfully fetched orderbook from chain! ({len(buys)} bids, {len(sells)} asks)", self.wallet_id)
                # Reset error counter since we got data
                self._indexer_error_count = 0
                return converted_orderbook
            else:
                log(f"⚠️ Chain orderbook query returned no data", self.wallet_id)
                return None
                
        except Exception as chain_error:
            log(f"❌ Chain-based orderbook query also failed: {chain_error}", self.wallet_id)
            return None
    
    def get_price_scale_factor(self, market_symbol: str) -> Decimal:
        """
        Get the price scaling factor for a market.
        stINJ markets use 1, others use 10^12
        """
        if 'stinj' in market_symbol.lower():
            return Decimal('1')
        else:
            return Decimal('1000000000000')  # 10^12
    
    def get_quantity_tick_size(self, market_symbol: str) -> Decimal:
        """
        Get the minimum quantity tick size for a market.
        Orders must be in multiples of this value to be accepted by the chain.
        """
        # Find market_id for this symbol
        for config_symbol, config in self.markets_config.items():
            if config_symbol == market_symbol:
                market_id = config.get('testnet_market_id' if self.network_name == 'testnet' else 'mainnet_market_id')
                
                # Check if we have metadata cached
                if market_id in self.market_metadata:
                    min_qty_tick = self.market_metadata[market_id].get('min_quantity_tick_size')
                    if min_qty_tick:
                        return Decimal(str(min_qty_tick))
                
                break
        
        # Default to 0.001 if not found (most markets)
        return Decimal('0.001')
    
    def quantize_order_size(self, size: Decimal, market_symbol: str) -> Decimal:
        """
        Quantize order size to match market's min_quantity_tick_size.
        This ensures orders are accepted by the chain.
        
        Args:
            size: Order size to quantize
            market_symbol: Market symbol (e.g., "USDC/USDT")
            
        Returns:
            Quantized size that meets market requirements
        """
        quantity_tick = self.get_quantity_tick_size(market_symbol)
        return (size / quantity_tick).quantize(Decimal('1'), rounding='ROUND_DOWN') * quantity_tick
    
    async def run(self):
        """Main trading loop"""
        await self.initialize()
        
        while True:
            try:
                # Get spot markets from markets_config.json
                spot_markets = self.get_spot_markets()
                
                if not spot_markets:
                    log("⚠️ No enabled spot markets found", self.wallet_id)
                    await asyncio.sleep(30)
                    continue
                
                # Trade on spot markets in a single batch transaction
                await self.trade_spot_markets_batch(spot_markets)
                
                # Wait before next cycle
                await asyncio.sleep(15)
                
            except Exception as e:
                log(f"❌ Error in trading loop: {e}", self.wallet_id)
                await asyncio.sleep(5)
    
    def get_spot_markets(self) -> list:
        """Get list of enabled spot markets from config"""
        spot_markets = []
        
        for market_symbol, market_config in self.markets_config["markets"].items():
            # Check if it's a spot market and enabled
            if market_config.get("type", "spot") == "spot" and market_config.get("enabled", False):
                # If target_market is specified, only include that market
                if self.target_market:
                    if market_symbol == self.target_market:
                        spot_markets.append(market_symbol)
                else:
                    spot_markets.append(market_symbol)
        
        return spot_markets
    
    async def trade_spot_markets_batch(self, markets: list):
        """Trade on spot markets in a single batch transaction"""
        try:
            spot_orders = []
            spot_orders_to_cancel = []
            
            log(f"🎯 Processing {len(markets)} spot markets", self.wallet_id)
            
            # Process each spot market and collect orders
            for market_symbol in markets:
                market_config = self.markets_config["markets"][market_symbol]
                market_id = market_config["testnet_market_id"]
                
                log(f"📊 Processing {market_symbol} (spot)", self.wallet_id)
                
                # Get MAINNET and TESTNET prices
                mainnet_market_id = market_config.get("mainnet_market_id")
                mainnet_price = await self.get_mainnet_price(market_symbol, mainnet_market_id)
                testnet_price = await self.get_market_price(market_id, market_symbol)
                
                # Use TESTNET price as the base, we'll push it towards mainnet
                if testnet_price > 0:
                    price = testnet_price
                    if mainnet_price > 0:
                        price_diff_percent = abs(mainnet_price - testnet_price) / mainnet_price * 100
                        log(f"💰 {market_symbol} | Mainnet: ${mainnet_price:.4f} | Testnet: ${testnet_price:.4f} | Diff: {price_diff_percent:.2f}%", self.wallet_id)
                    else:
                        log(f"💰 {market_symbol} | Using Testnet price: ${testnet_price:.4f} (no mainnet price)", self.wallet_id)
                elif mainnet_price > 0:
                    # Only if we can't get testnet price, use mainnet as fallback
                    price = mainnet_price
                    log(f"⚠️ {market_symbol} | Using Mainnet price: ${mainnet_price:.4f} (no testnet price)", self.wallet_id)
                else:
                    price = 0
                
                if not price:
                    log(f"⚠️ Skipping {market_symbol} - no price available", self.wallet_id)
                    continue
                
                # Create spot orders with enhanced strategy
                result = await self.create_spot_orders(market_id, market_symbol, market_config, price)
                
                # Handle both tuple (with cancellations) and list (without cancellations) returns
                if isinstance(result, tuple):
                    market_spot_orders, market_cancellations = result
                    spot_orders.extend(market_spot_orders)
                    spot_orders_to_cancel.extend(market_cancellations)
                else:
                    spot_orders.extend(result)
            
            # If we have orders, send them in one batch transaction
            if spot_orders or spot_orders_to_cancel:
                await self.send_batch_orders(spot_orders, spot_orders_to_cancel)
            else:
                log("⚠️ No orders to place in this cycle", self.wallet_id)
                
        except Exception as e:
            log(f"❌ Error in batch trading: {e}", self.wallet_id)
    
    async def assess_orderbook_depth(self, market_id: str, market_symbol: str, target_price: float) -> Dict:
        """
        Assess current orderbook depth and quality
        Checks BOTH total market depth AND our own orders
        Returns: dict with depth metrics
        """
        try:
            # Fetch our open orders first
            from pyinjective.client.model.pagination import PaginationOption
            our_orders_response = await self.indexer_client.fetch_spot_orders(
                market_ids=[market_id],
                subaccount_id=self.address.get_subaccount_id(0),
                pagination=PaginationOption(limit=100)  # API max is 100
            )
            
            our_orders_count = 0
            if our_orders_response and 'orders' in our_orders_response:
                our_orders_count = len(our_orders_response['orders'])
            
            # Fetch full orderbook
            orderbook = await self.fetch_spot_orderbook_v2_failover(market_id=market_id, depth=100, force_chain=self.force_chain_queries)
            
            if not orderbook or 'orderbook' not in orderbook:
                return {
                    'total_orders': 0,
                    'our_orders': our_orders_count,
                    'others_orders': 0,
                    'depth_good': False,
                    'needs_building': True
                }
            
            buys = orderbook['orderbook'].get('buys', [])
            sells = orderbook['orderbook'].get('sells', [])
            total_orders = len(buys) + len(sells)
            
            # Price scaling
            if 'stinj' in market_symbol.lower():
                price_scale_factor = Decimal('1')
            else:
                price_scale_factor = Decimal('1000000000000')
            
            # Count orders within 5% of target price
            orders_near_price = 0
            target_decimal = Decimal(str(target_price))
            
            for buy in buys:
                buy_price = Decimal(str(buy['price'])) * price_scale_factor
                if buy_price >= target_decimal * Decimal('0.95'):
                    orders_near_price += 1
            
            for sell in sells:
                sell_price = Decimal(str(sell['price'])) * price_scale_factor
                if sell_price <= target_decimal * Decimal('1.05'):
                    orders_near_price += 1
            
            # Calculate others' orders
            others_orders = max(0, total_orders - our_orders_count)
            
            # Depth assessment - WE need good depth, not just the market
            our_depth_good = our_orders_count >= 30  # WE have at least 30 orders
            market_depth_good = total_orders >= 50  # Market has at least 50 orders total
            
            return {
                'total_orders': total_orders,
                'our_orders': our_orders_count,
                'others_orders': others_orders,
                'orders_near_price': orders_near_price,
                'our_depth_good': our_depth_good,
                'market_depth_good': market_depth_good,
                'needs_building': our_orders_count < 30,  # Build if WE have <30 orders
                'buys_count': len(buys),
                'sells_count': len(sells)
            }
            
        except Exception as e:
            error_msg = str(e)
            if '503' in error_msg or 'UNAVAILABLE' in error_msg:
                log(f"⚠️ Indexer API unavailable - assuming empty orderbook", self.wallet_id)
            else:
                log(f"⚠️ Error assessing orderbook depth: {error_msg[:150]}", self.wallet_id)
            return {
                'total_orders': 0,
                'our_orders': 0,
                'others_orders': 0,
                'depth_good': False,
                'needs_building': True
            }
    
    async def create_spot_orders(self, market_id: str, market_symbol: str, market_config: Dict, price: float):
        """
        Create spot orders using intelligent multi-phase strategy:
        1. Assess orderbook depth first
        2. Choose strategy: Market Moving, Orderbook Building, or Maintenance
        3. Execute appropriate actions
        """
        orders = []
        try:
            order_size = Decimal(str(market_config["order_size"]))
            
            # Get mainnet price to determine strategy
            mainnet_price = await self.get_mainnet_price(market_symbol, market_config.get("mainnet_market_id"))
            
            if mainnet_price <= 0:
                log(f"⚠️ No mainnet price available - using testnet price ${price:.4f}", self.wallet_id)
                mainnet_price = price
            
            price_gap_percent = abs(mainnet_price - price) / mainnet_price * 100
            
            # PHASE 0: ASSESS ORDERBOOK DEPTH
            depth_info = await self.assess_orderbook_depth(market_id, market_symbol, mainnet_price)
            
            log(f"📊 Orderbook: {depth_info['total_orders']} total ({depth_info['our_orders']} ours, {depth_info['others_orders']} others)", self.wallet_id)
            
            # STRATEGY SELECTION LOGIC
            is_price_aligned = price_gap_percent <= 2.0
            is_price_moderate = price_gap_percent <= 3.0
            is_price_diverged = price_gap_percent > 4.0
            is_price_extreme = price_gap_percent > 5.0  # EXTREME gap needs aggressive push (changed from 100%)
            we_have_orders = depth_info['our_orders'] > 0
            we_have_good_depth = depth_info['our_orders'] >= 30
            
            # PHASE 0: EXTREME GAP - Aggressive market moving with directional orders
            # For gaps >15%, we need to actively push price towards mainnet by starting from current price
            if is_price_extreme:
                log(f"🚀 EXTREME GAP ({price_gap_percent:.2f}%) - aggressive price push from ${price:.4f} towards ${mainnet_price:.4f}", self.wallet_id)
                return await self.aggressive_price_push(market_id, market_symbol, market_config, price, mainnet_price)
            
            # PHASE 1: MODERATE GAP (10-15%) - Build full orderbook with blended pricing
            # This creates liquidity at a price between current and target
            elif is_price_diverged:
                log(f"🏗️ LARGE GAP ({price_gap_percent:.2f}%) - building full book at mainnet ${mainnet_price:.4f} to establish correct price", self.wallet_id)
                # Create complete 2-sided orderbook centered on mainnet price
                return await self.create_beautiful_orderbook(market_id, market_symbol, market_config, price, mainnet_price)
            
            # PHASE 2: MARKET MOVING (2% < gap <= 10%, shift liquidity)
            elif not is_price_aligned and is_price_moderate and we_have_orders:
                log(f"🎯 MARKET MOVING: Gap {price_gap_percent:.2f}%, shifting our {depth_info['our_orders']} orders to mainnet price", self.wallet_id)
                # Cancel our old orders and place new ones at mainnet price
                return await self.market_moving_phase(market_id, market_symbol, market_config, price, mainnet_price)
            
            # PHASE 3: ORDERBOOK BUILDING (WE don't have enough orders, price moderate)
            elif depth_info['needs_building'] and not is_price_diverged:
                if depth_info['our_orders'] == 0:
                    log(f"🏗️ ORDERBOOK BUILDING: We have NO orders, building at mainnet ${mainnet_price:.4f}", self.wallet_id)
                else:
                    log(f"🏗️ ORDERBOOK BUILDING: We have only {depth_info['our_orders']} orders, building more at mainnet ${mainnet_price:.4f}", self.wallet_id)
                return await self.create_beautiful_orderbook(market_id, market_symbol, market_config, price, mainnet_price)
            
            # PHASE 4: MAINTENANCE (price aligned, WE have good depth)
            elif is_price_aligned and we_have_good_depth:
                log(f"🔄 MAINTENANCE: Gap {price_gap_percent:.2f}%, we have {depth_info['our_orders']} orders, gradual updates", self.wallet_id)
                return await self.gradual_orderbook_update(market_id, market_symbol, market_config, price, mainnet_price)
            
            # FALLBACK: Build orderbook
            else:
                log(f"📖 BUILDING: Creating orderbook at mainnet ${mainnet_price:.4f}", self.wallet_id)
                return await self.create_beautiful_orderbook(market_id, market_symbol, market_config, price, mainnet_price)
                
        except Exception as e:
            log(f"❌ Error creating spot orders for {market_symbol}: {e}", self.wallet_id)
            
        return orders
    
    async def aggressive_price_moving(self, market_id: str, market_symbol: str, market_config: Dict,
                                        testnet_price: float, mainnet_price: float) -> tuple:
        """
        Aggressive price moving: Analyze orderbook depth and strategically consume liquidity
        to move price towards mainnet target
        """
        orders = []
        orders_to_cancel = []
        
        try:
            order_size = Decimal(str(market_config["order_size"]))
            
            # Fetch FULL orderbook to analyze depth
            orderbook = await asyncio.wait_for(
                self.fetch_spot_orderbook_v2_failover(market_id=market_id, depth=50, force_chain=self.force_chain_queries),
                timeout=15.0
            )
            
            if not orderbook or 'orderbook' not in orderbook:
                log(f"⚠️ No orderbook data available", self.wallet_id)
                return orders, orders_to_cancel
            
            buys = orderbook['orderbook'].get('buys', [])
            sells = orderbook['orderbook'].get('sells', [])
            price_scale = self.get_price_scale_factor(market_symbol)
            
            # Analyze orderbook depth
            log(f"📊 Orderbook Analysis: {len(buys)} bids, {len(sells)} asks", self.wallet_id)
            
            if sells and len(sells) > 0:
                best_ask = Decimal(str(sells[0]['price'])) * price_scale
                log(f"   Best Ask: ${float(best_ask):.4f} (size: {sells[0]['quantity']})", self.wallet_id)
            
            if buys and len(buys) > 0:
                best_bid = Decimal(str(buys[0]['price'])) * price_scale
                log(f"   Best Bid: ${float(best_bid):.4f} (size: {buys[0]['quantity']})", self.wallet_id)
            
            # Determine direction
            testnet_too_high = testnet_price > mainnet_price
            
            if testnet_too_high:
                # Price TOO HIGH → Need to push it DOWN
                
                if not buys or len(buys) == 0:
                    # NO BIDS! Create BOTH SIDES centered on mainnet price
                    log(f"⚠️ No bids to hit - creating FULL ORDERBOOK centered on mainnet ${mainnet_price:.2f}", self.wallet_id)
                    
                    # Create 6-10 levels of BOTH buys and sells around mainnet price
                    num_levels = random.randint(6, 10)
                    spread_increment = Decimal('0.003')  # 0.3% spread between levels
                    
                    for i in range(num_levels):
                        # Calculate price offset from mainnet
                        offset = (i + 1) * spread_increment
                        
                        # BUY side: Below mainnet price
                        buy_price = Decimal(str(mainnet_price)) * (Decimal('1') - offset)
                        buy_price = buy_price.quantize(Decimal('0.0001') if buy_price > 10 else Decimal('0.00001'))
                        
                        # SELL side: Above mainnet price
                        sell_price = Decimal(str(mainnet_price)) * (Decimal('1') + offset)
                        sell_price = sell_price.quantize(Decimal('0.0001') if sell_price > 10 else Decimal('0.00001'))
                        
                        # Varying sizes
                        buy_size = (order_size * Decimal(str(random.uniform(1.5, 3.5)))).quantize(Decimal('0.001'))
                        sell_size = (order_size * Decimal(str(random.uniform(1.5, 3.5)))).quantize(Decimal('0.001'))
                        
                        # Create BUY order
                        orders.append(self.composer.spot_order(
                            market_id=market_id,
                            subaccount_id=self.address.get_subaccount_id(0),
                            fee_recipient=self.address.to_acc_bech32(),
                            price=buy_price,
                            quantity=buy_size,
                            order_type="BUY",
                            cid=None
                        ))
                        
                        # Create SELL order
                        orders.append(self.composer.spot_order(
                            market_id=market_id,
                            subaccount_id=self.address.get_subaccount_id(0),
                            fee_recipient=self.address.to_acc_bech32(),
                            price=sell_price,
                            quantity=sell_size,
                            order_type="SELL",
                            cid=None
                        ))
                        
                        log(f"   📊 Level {i+1}: Buy {float(buy_size):.2f} @ ${float(buy_price):.4f} | Sell {float(sell_size):.2f} @ ${float(sell_price):.4f}", self.wallet_id)
                    
                    log(f"🔥 Created {len(orders)} orders ({num_levels} buy/sell pairs) centered on mainnet price", self.wallet_id)
                    
                else:
                    # BIDS EXIST - hit them aggressively
                    log(f"🔥 Testnet ${testnet_price:.4f} > Mainnet ${mainnet_price:.4f} - HITTING BIDS to push DOWN", self.wallet_id)
                    
                    # Hit top 3-7 bid levels (or all available if less)
                    num_levels_to_hit = min(random.randint(3, 7), len(buys))
                    
                    for i in range(num_levels_to_hit):
                        bid_price = Decimal(str(buys[i]['price'])) * price_scale
                        
                        # Sell AT or SLIGHTLY BELOW the bid price to execute immediately
                        sell_price = bid_price * Decimal('0.9999')  # 0.01% below to ensure execution
                        sell_price = sell_price.quantize(Decimal('0.0001') if sell_price > 10 else Decimal('0.00001'))
                        
                        # Use configured order_size with aggressive multiplier (2x-5x)
                        size_mult = Decimal(str(random.uniform(2.0, 5.0)))
                        actual_size = (order_size * size_mult).quantize(Decimal('0.001'))
                        
                        orders.append(self.composer.spot_order(
                            market_id=market_id,
                            subaccount_id=self.address.get_subaccount_id(0),
                            fee_recipient=self.address.to_acc_bech32(),
                            price=sell_price,
                            quantity=actual_size,
                            order_type="SELL",
                            cid=None
                        ))
                        
                        log(f"   💥 Sell {float(actual_size):.3f} INJ @ ${float(sell_price):.4f} (hitting bid level {i+1})", self.wallet_id)
                
            else:
                # Price TOO LOW → Need to push it UP
                
                if not sells or len(sells) == 0:
                    # NO ASKS! Create BOTH SIDES centered on mainnet price
                    log(f"⚠️ No asks to hit - creating FULL ORDERBOOK centered on mainnet ${mainnet_price:.2f}", self.wallet_id)
                    
                    # Create 6-10 levels of BOTH buys and sells around mainnet price
                    num_levels = random.randint(6, 10)
                    spread_increment = Decimal('0.003')  # 0.3% spread between levels
                    
                    for i in range(num_levels):
                        # Calculate price offset from mainnet
                        offset = (i + 1) * spread_increment
                        
                        # BUY side: Below mainnet price
                        buy_price = Decimal(str(mainnet_price)) * (Decimal('1') - offset)
                        buy_price = buy_price.quantize(Decimal('0.0001') if buy_price > 10 else Decimal('0.00001'))
                        
                        # SELL side: Above mainnet price
                        sell_price = Decimal(str(mainnet_price)) * (Decimal('1') + offset)
                        sell_price = sell_price.quantize(Decimal('0.0001') if sell_price > 10 else Decimal('0.00001'))
                        
                        # Varying sizes
                        buy_size = (order_size * Decimal(str(random.uniform(1.5, 3.5)))).quantize(Decimal('0.001'))
                        sell_size = (order_size * Decimal(str(random.uniform(1.5, 3.5)))).quantize(Decimal('0.001'))
                        
                        # Create BUY order
                        orders.append(self.composer.spot_order(
                            market_id=market_id,
                            subaccount_id=self.address.get_subaccount_id(0),
                            fee_recipient=self.address.to_acc_bech32(),
                            price=buy_price,
                            quantity=buy_size,
                            order_type="BUY",
                            cid=None
                        ))
                        
                        # Create SELL order
                        orders.append(self.composer.spot_order(
                            market_id=market_id,
                            subaccount_id=self.address.get_subaccount_id(0),
                            fee_recipient=self.address.to_acc_bech32(),
                            price=sell_price,
                            quantity=sell_size,
                            order_type="SELL",
                            cid=None
                        ))
                        
                        log(f"   📊 Level {i+1}: Buy {float(buy_size):.2f} @ ${float(buy_price):.4f} | Sell {float(sell_size):.2f} @ ${float(sell_price):.4f}", self.wallet_id)
                    
                    log(f"🔥 Created {len(orders)} orders ({num_levels} buy/sell pairs) centered on mainnet price", self.wallet_id)
                    
                else:
                    # ASKS EXIST - hit them aggressively
                    log(f"🔥 Testnet ${testnet_price:.4f} < Mainnet ${mainnet_price:.4f} - HITTING ASKS to push UP", self.wallet_id)
                    
                    # Hit bottom 3-7 ask levels (or all available if less)
                    num_levels_to_hit = min(random.randint(3, 7), len(sells))
                    
                    for i in range(num_levels_to_hit):
                        ask_price = Decimal(str(sells[i]['price'])) * price_scale
                        
                        # Buy AT or SLIGHTLY ABOVE the ask price to execute immediately
                        buy_price = ask_price * Decimal('1.0001')  # 0.01% above to ensure execution
                        buy_price = buy_price.quantize(Decimal('0.0001') if buy_price > 10 else Decimal('0.00001'))
                        
                        # Use configured order_size with aggressive multiplier (2x-5x)
                        size_mult = Decimal(str(random.uniform(2.0, 5.0)))
                        actual_size = (order_size * size_mult).quantize(Decimal('0.001'))
                        
                        orders.append(self.composer.spot_order(
                            market_id=market_id,
                            subaccount_id=self.address.get_subaccount_id(0),
                            fee_recipient=self.address.to_acc_bech32(),
                            price=buy_price,
                            quantity=actual_size,
                            order_type="BUY",
                            cid=None
                        ))
                        
                        log(f"   💥 Buy {float(actual_size):.3f} INJ @ ${float(buy_price):.4f} (hitting ask level {i+1})", self.wallet_id)
            
            # Cancel our old non-executing orders
            num_to_cancel = 50
            orders_to_cancel = await self.get_open_orders_to_cancel(market_id, num_to_cancel)
            
            log(f"🔥 Created {len(orders)} orders to CONSUME orderbook levels, canceling {len(orders_to_cancel)} old ones", self.wallet_id)
            
        except Exception as e:
            log(f"❌ Error in aggressive price moving: {e}", self.wallet_id)
            import traceback
            traceback.print_exc()
            orders_to_cancel = []
        
        return orders, orders_to_cancel
    
    async def market_moving_phase(self, market_id: str, market_symbol: str, market_config: Dict,
                                   testnet_price: float, mainnet_price: float) -> tuple:
        """
        Market moving phase: Cancel old orders far from mainnet price, create new ones at mainnet price
        This helps move the market price towards mainnet when orderbook exists but price is wrong
        """
        orders = []
        orders_to_cancel = []
        
        try:
            order_size = Decimal(str(market_config["order_size"]))
            
            # Cancel 8-12 old orders to make room for new ones
            num_to_cancel = random.randint(8, 12)
            orders_to_cancel = await self.get_open_orders_to_cancel(market_id, num_to_cancel)
            
            # Create 6-10 new orders at mainnet price with tighter spreads
            num_orders_per_side = random.randint(3, 5)
            
            log(f"🔄 Market moving: creating {num_orders_per_side*2} orders, canceling {len(orders_to_cancel)}", self.wallet_id)
            
            for i in range(num_orders_per_side):
                # Tighter spreads (0.1% - 1%) for market moving
                spread = random.uniform(0.001, 0.01)
                
                # Larger sizes (50%-100% of base) for market impact
                size_mult = random.uniform(0.5, 1.0)
                actual_size = (order_size * Decimal(str(size_mult))).quantize(Decimal('0.001'))
                
                # Buy order
                buy_price = Decimal(str(mainnet_price * (1 - spread)))
                buy_price = buy_price.quantize(Decimal('0.0001') if buy_price > 10 else Decimal('0.00001'))
                
                orders.append(self.composer.spot_order(
                    market_id=market_id,
                    subaccount_id=self.address.get_subaccount_id(0),
                    fee_recipient=self.address.to_acc_bech32(),
                    price=buy_price,
                    quantity=actual_size,
                    order_type="BUY",
                    cid=None
                ))
                
                # Sell order
                sell_price = Decimal(str(mainnet_price * (1 + spread)))
                sell_price = sell_price.quantize(Decimal('0.0001') if sell_price > 10 else Decimal('0.00001'))
                
                orders.append(self.composer.spot_order(
                    market_id=market_id,
                    subaccount_id=self.address.get_subaccount_id(0),
                    fee_recipient=self.address.to_acc_bech32(),
                    price=sell_price,
                    quantity=actual_size,
                    order_type="SELL",
                    cid=None
                ))
            
            log(f"🎯 Created {len(orders)} market moving orders at mainnet price ${mainnet_price:.4f}", self.wallet_id)
            
        except Exception as e:
            log(f"❌ Error in market moving phase: {e}", self.wallet_id)
            orders_to_cancel = []
        
        return orders, orders_to_cancel
    
    async def gradual_orderbook_update(self, market_id: str, market_symbol: str, market_config: Dict, 
                                        testnet_price: float, mainnet_price: float) -> tuple:
        """
        Gradually build orderbook depth when prices are aligned
        Returns: (new_orders, orders_to_cancel)
        """
        orders = []
        orders_to_cancel = []
        
        try:
            order_size = Decimal(str(market_config["order_size"]))
            center_price = mainnet_price
            
            # Track depth stage for this market
            current_stage = self.orderbook_depth_stage.get(market_id, 0)
            
            # Define spread ranges for each stage (same as derivative trader)
            spread_ranges = [
                (0.005, 0.015),  # Stage 0: 0.5%-1.5% (tight)
                (0.015, 0.03),   # Stage 1: 1.5%-3% (medium)
                (0.03, 0.05),    # Stage 2: 3%-5% (wide)
                (0.05, 0.08),    # Stage 3: 5%-8% (deep)
            ]
            
            # Cycle through stages
            min_spread, max_spread = spread_ranges[current_stage % len(spread_ranges)]
            
            # Place 5-8 SMALL orders per side at VARIED prices for organic look
            num_orders_per_side = random.randint(5, 8)
            
            log(f"📏 Depth stage {current_stage}: spread range {min_spread*100:.1f}%-{max_spread*100:.1f}%", self.wallet_id)
            
            for i in range(num_orders_per_side):
                # Random spread within this stage's range - each order at different price
                spread = random.uniform(min_spread, max_spread)
                offset = spread
                
                # Smaller sizes (20%-50% of base) but more orders for organic look
                size_mult = random.uniform(0.2, 0.5)
                actual_size = (order_size * Decimal(str(size_mult))).quantize(Decimal('0.001'))
                
                # Buy order
                buy_price = Decimal(str(center_price * (1 - offset)))
                buy_price = buy_price.quantize(Decimal('0.0001') if buy_price > 10 else Decimal('0.00001'))
                
                orders.append(self.composer.spot_order(
                    market_id=market_id,
                    subaccount_id=self.address.get_subaccount_id(0),
                    fee_recipient=self.address.to_acc_bech32(),
                    price=buy_price,
                    quantity=actual_size,
                    order_type="BUY",
                    cid=None
                ))
                
                # Sell order
                sell_price = Decimal(str(center_price * (1 + offset)))
                sell_price = sell_price.quantize(Decimal('0.0001') if sell_price > 10 else Decimal('0.00001'))
                
                orders.append(self.composer.spot_order(
                    market_id=market_id,
                    subaccount_id=self.address.get_subaccount_id(0),
                    fee_recipient=self.address.to_acc_bech32(),
                    price=sell_price,
                    quantity=actual_size,
                    order_type="SELL",
                    cid=None
                ))
            
            # Advance to next depth stage
            self.orderbook_depth_stage[market_id] = current_stage + 1
            
            log(f"📝 Created {len(orders)} gradual orders ({num_orders_per_side} buys + {num_orders_per_side} sells)", self.wallet_id)
            
            # Cancel more orders to match higher creation rate (5-8 created, cancel 4-6)
            num_to_cancel = random.randint(4, 6)
            orders_to_cancel = await self.get_open_orders_to_cancel(market_id, num_to_cancel)
            
        except Exception as e:
            log(f"❌ Error creating gradual orders for {market_symbol}: {e}", self.wallet_id)
            orders_to_cancel = []
            
        return orders, orders_to_cancel
    
    async def aggressive_price_push(self, market_id: str, market_symbol: str, market_config: Dict,
                                     testnet_price: float, mainnet_price: float) -> list:
        """
        Aggressive price push for EXTREME gaps (>100%)
        Handles all edge cases: no liquidity, one-sided books, huge spreads
        """
        orders = []
        try:
            order_size = Decimal(str(market_config["order_size"]))
            
            # STEP 1: Analyze current orderbook to understand market structure
            orderbook = await self.fetch_spot_orderbook_v2_failover(market_id=market_id, depth=10, force_chain=self.force_chain_queries)
            buys = orderbook['orderbook'].get('buys', []) if orderbook and 'orderbook' in orderbook else []
            sells = orderbook['orderbook'].get('sells', []) if orderbook and 'orderbook' in orderbook else []
            
            # Get market metadata for price scaling
            metadata = await self.get_market_metadata(market_id)
            price_scale = metadata['price_scale_factor']
            
            # Determine direction
            push_down = testnet_price > mainnet_price
            
            # Calculate intermediate target (move 20-30% towards mainnet each cycle)
            price_diff = testnet_price - mainnet_price
            step_percentage = random.uniform(0.20, 0.30)
            target_price = testnet_price - (price_diff * step_percentage)
            
            # EDGE CASE 1: Empty orderbook - create two-sided market first
            if not buys and not sells:
                log(f"⚠️ EMPTY ORDERBOOK - creating initial two-sided market around target ${target_price:.6f}", self.wallet_id)
                # Create 5 buy and 5 sell orders around target price to establish a market
                for i in range(5):
                    spread = 0.01 + (i * 0.01)  # 1%, 2%, 3%, 4%, 5%
                    
                    buy_price = Decimal(str(target_price * (1 - spread)))
                    buy_price = buy_price.quantize(Decimal('0.000001') if buy_price < 1 else Decimal('0.0001'))
                    sell_price = Decimal(str(target_price * (1 + spread)))
                    sell_price = sell_price.quantize(Decimal('0.000001') if sell_price < 1 else Decimal('0.0001'))
                    
                    size = (order_size * Decimal(str(random.uniform(0.5, 1.5))))
                    # Quantize to whole numbers for assets like HDRO
                    size = size.quantize(Decimal('1') if size >= 1 else Decimal('0.001'))
                    
                    orders.append(self.composer.spot_order(
                        market_id=market_id, subaccount_id=self.address.get_subaccount_id(0),
                        fee_recipient=self.address.to_acc_bech32(), price=buy_price, quantity=size,
                        order_type="BUY", cid=None
                    ))
                    orders.append(self.composer.spot_order(
                        market_id=market_id, subaccount_id=self.address.get_subaccount_id(0),
                        fee_recipient=self.address.to_acc_bech32(), price=sell_price, quantity=size,
                        order_type="SELL", cid=None
                    ))
                log(f"🏗️ Created {len(orders)} orders to establish initial market", self.wallet_id)
                return orders
            
            # EDGE CASE 2: One-sided orderbook
            if push_down and not buys:
                # Need to push DOWN but no buyers - create buy orders to enable selling
                log(f"⚠️ No buy orders exist - creating buy ladder at target ${target_price:.6f} to enable price push", self.wallet_id)
                for i in range(8):
                    price_offset = i * 0.02  # 0%, 2%, 4%, 6%, etc below target
                    buy_price = Decimal(str(target_price * (1 - price_offset)))
                    buy_price = buy_price.quantize(Decimal('0.000001') if buy_price < 1 else Decimal('0.0001'))
                    size = (order_size * Decimal(str(random.uniform(1.0, 2.0))))
                    size = size.quantize(Decimal('1') if size >= 1 else Decimal('0.001'))
                    
                    orders.append(self.composer.spot_order(
                        market_id=market_id, subaccount_id=self.address.get_subaccount_id(0),
                        fee_recipient=self.address.to_acc_bech32(), price=buy_price, quantity=size,
                        order_type="BUY", cid=None
                    ))
                log(f"🏗️ Created {len(orders)} buy orders to establish bid side", self.wallet_id)
                return orders
                
            if not push_down and not sells:
                # Need to push UP but no sellers - create sell orders to enable buying
                log(f"⚠️ No sell orders exist - creating sell ladder at target ${target_price:.6f} to enable price push", self.wallet_id)
                for i in range(8):
                    price_offset = i * 0.02  # 0%, 2%, 4%, 6%, etc above target
                    sell_price = Decimal(str(target_price * (1 + price_offset)))
                    sell_price = sell_price.quantize(Decimal('0.000001') if sell_price < 1 else Decimal('0.0001'))
                    size = (order_size * Decimal(str(random.uniform(1.0, 2.0))))
                    size = size.quantize(Decimal('1') if size >= 1 else Decimal('0.001'))
                    
                    orders.append(self.composer.spot_order(
                        market_id=market_id, subaccount_id=self.address.get_subaccount_id(0),
                        fee_recipient=self.address.to_acc_bech32(), price=sell_price, quantity=size,
                        order_type="SELL", cid=None
                    ))
                log(f"🏗️ Created {len(orders)} sell orders to establish ask side", self.wallet_id)
                return orders
            
            # NORMAL CASE: Place aggressive orders to move price
            if push_down:
                # Get best bid to understand where buyers are
                best_bid = float(Decimal(str(buys[0]['price'])) * price_scale) if buys else target_price
                
                # Calculate how much LOWER than best bid we should go (5-15% below)
                undercut_pct = random.uniform(0.05, 0.15)  # 5-15% below best bid
                sell_price_target = best_bid * (1 - undercut_pct)
                # But never go below our final target
                sell_price_target = max(sell_price_target, target_price)
                
                log(f"📉 Pushing price DOWN: best_bid=${best_bid:.6f}, selling at ${sell_price_target:.6f} (target=${target_price:.6f})", self.wallet_id)
                
                # Place aggressive sells AT and slightly BELOW best bid to force trades
                # If only 1 wallet is being used, increase orders to match 3-wallet impact
                num_orders = random.randint(25, 35)  # ~3x single wallet for equivalent impact
                for i in range(num_orders):
                    # Spread orders from best_bid down to sell_price_target
                    price_offset_pct = random.uniform(0, undercut_pct)
                    order_price = Decimal(str(best_bid * (1 - price_offset_pct)))
                    order_price = order_price.quantize(Decimal('0.000001') if order_price < 1 else Decimal('0.0001'))
                    
                    size_mult = random.uniform(2.0, 4.0)  # Even larger for aggressive push
                    actual_size = (order_size * Decimal(str(size_mult)))
                    actual_size = actual_size.quantize(Decimal('1') if actual_size >= 1 else Decimal('0.001'))
                    
                    orders.append(self.composer.spot_order(
                        market_id=market_id, subaccount_id=self.address.get_subaccount_id(0),
                        fee_recipient=self.address.to_acc_bech32(), price=order_price, quantity=actual_size,
                        order_type="SELL", cid=None
                    ))
            else:
                # Get best ask to understand where sellers are
                best_ask = float(Decimal(str(sells[0]['price'])) * price_scale) if sells else target_price
                
                # Calculate how much HIGHER than best ask we should go (5-15% above)
                overbid_pct = random.uniform(0.05, 0.15)  # 5-15% above best ask
                buy_price_target = best_ask * (1 + overbid_pct)
                # But never go above our final target
                buy_price_target = min(buy_price_target, target_price)
                
                log(f"📈 Pushing price UP: best_ask=${best_ask:.6f}, buying at ${buy_price_target:.6f} (target=${target_price:.6f})", self.wallet_id)
                
                # Place aggressive buys AT and slightly ABOVE best ask to force trades
                # If only 1 wallet is being used, increase orders to match 3-wallet impact
                num_orders = random.randint(25, 35)  # ~3x single wallet for equivalent impact
                for i in range(num_orders):
                    # Spread orders from best_ask up to buy_price_target
                    price_offset_pct = random.uniform(0, overbid_pct)
                    order_price = Decimal(str(best_ask * (1 + price_offset_pct)))
                    order_price = order_price.quantize(Decimal('0.000001') if order_price < 1 else Decimal('0.0001'))
                    
                    size_mult = random.uniform(2.0, 4.0)  # Even larger for aggressive push
                    actual_size = (order_size * Decimal(str(size_mult)))
                    actual_size = actual_size.quantize(Decimal('1') if actual_size >= 1 else Decimal('0.001'))
                    
                    orders.append(self.composer.spot_order(
                        market_id=market_id, subaccount_id=self.address.get_subaccount_id(0),
                        fee_recipient=self.address.to_acc_bech32(), price=order_price, quantity=actual_size,
                        order_type="BUY", cid=None
                    ))
            
            log(f"🚀 Created {len(orders)} aggressive {'SELL' if push_down else 'BUY'} orders for price push", self.wallet_id)
            
        except Exception as e:
            log(f"❌ Error creating aggressive push orders for {market_symbol}: {e}", self.wallet_id)
        
        return orders
    
    async def create_beautiful_orderbook(self, market_id: str, market_symbol: str, market_config: Dict, 
                                         testnet_price: float, mainnet_price: float) -> list:
        """
        Create a beautiful, natural-looking orderbook with deep liquidity
        Used when prices are not aligned (> 2% difference)
        """
        orders = []
        order_details_log = []  # Track order details for logging
        
        try:
            order_size = Decimal(str(market_config["order_size"]))
            
            # Use mainnet price as the center for orderbook
            center_price = mainnet_price
            
            # Create beautiful staircase orderbook with smooth depth
            # Start tight near center, gradually widen
            order_levels = []
            base_spread = 0.0001  # Start at 0.01% from center
            
            # Create 14 levels on each side with gradually increasing spread
            for level in range(14):
                if level < 5:
                    # Tight levels near center (0.01% - 0.1%)
                    spread = base_spread * (level + 1) * 2
                    size_mult = 1.5 - (level * 0.05)  # Gradually decrease size
                elif level < 10:
                    # Medium levels (0.1% - 0.5%)
                    spread = 0.001 + (level - 5) * 0.0008
                    size_mult = 1.2 - ((level - 5) * 0.08)
                else:
                    # Wide levels (0.5% - 2%)
                    spread = 0.005 + (level - 10) * 0.004
                    size_mult = 0.8 - ((level - 10) * 0.08)
                
                order_levels.append((spread, size_mult))
            
            # Create orders at each level
            for level_idx, (spread, size_mult) in enumerate(order_levels):
                # Add slight randomization for natural look
                spread_jitter = random.uniform(0.95, 1.05)
                size_jitter = random.uniform(0.9, 1.1)
                
                actual_spread = spread * spread_jitter
                actual_size = order_size * Decimal(str(size_mult * size_jitter))
                
                # Quantize to market's min_quantity_tick_size (critical for order acceptance!)
                actual_size = self.quantize_order_size(actual_size, market_symbol)
                
                # Calculate prices for this level
                buy_price = Decimal(str(center_price * (1 - actual_spread)))
                sell_price = Decimal(str(center_price * (1 + actual_spread)))
                
                # Smart rounding based on price level for natural look
                if buy_price > 10:
                    buy_price = buy_price.quantize(Decimal('0.0001'))
                    sell_price = sell_price.quantize(Decimal('0.0001'))
                else:
                    buy_price = buy_price.quantize(Decimal('0.00001'))
                    sell_price = sell_price.quantize(Decimal('0.00001'))
                
                # Create buy order (POST-ONLY to sit in orderbook)
                buy_order = self.composer.spot_order(
                    market_id=market_id,
                    subaccount_id=self.address.get_subaccount_id(0),
                    fee_recipient=self.address.to_acc_bech32(),
                    price=buy_price,
                    quantity=actual_size,
                    order_type="BUY",
                    cid=None
                )
                orders.append(buy_order)
                order_details_log.append(('BUY', buy_price, actual_size))
                
                # Create sell order (POST-ONLY to sit in orderbook)
                sell_order = self.composer.spot_order(
                    market_id=market_id,
                    subaccount_id=self.address.get_subaccount_id(0),
                    fee_recipient=self.address.to_acc_bech32(),
                    price=sell_price,
                    quantity=actual_size,
                    order_type="SELL",
                    cid=None
                )
                orders.append(sell_order)
                order_details_log.append(('SELL', sell_price, actual_size))
            
            log(f"📖 Created beautiful orderbook with {len(orders)} staircase levels", self.wallet_id)
            
            # Log all order details for transparency
            buy_orders = [o for o in order_details_log if o[0] == 'BUY']
            sell_orders = [o for o in order_details_log if o[0] == 'SELL']
            
            log(f"", self.wallet_id)
            log(f"📋 ═══════════════════════════════════════════════════", self.wallet_id)
            if buy_orders:
                log(f"🟢 BUY ORDERS ({len(buy_orders)}):", self.wallet_id)
                for idx, (side, price, qty) in enumerate(buy_orders, 1):
                    log(f"  #{idx:2d} │ Price: ${float(price):>12.8f} │ Size: {float(qty):>12.2f}", self.wallet_id)
            
            log(f"", self.wallet_id)
            if sell_orders:
                log(f"🔴 SELL ORDERS ({len(sell_orders)}):", self.wallet_id)
                for idx, (side, price, qty) in enumerate(sell_orders, 1):
                    log(f"  #{idx:2d} │ Price: ${float(price):>12.8f} │ Size: {float(qty):>12.2f}", self.wallet_id)
            log(f"📋 ═══════════════════════════════════════════════════", self.wallet_id)
            log(f"", self.wallet_id)
            
        except Exception as e:
            log(f"❌ Error creating beautiful orderbook for {market_symbol}: {e}", self.wallet_id)
            
        return orders
    
    async def get_open_orders_to_cancel(self, market_id: str, num_to_cancel: int = 3) -> list:
        """
        Fetch open orders for a market and select oldest ones to cancel
        
        Returns: List of order data dicts (market_id, subaccount_id, order_hash) for cancellation
        """
        try:
            from pyinjective.client.model.pagination import PaginationOption
            
            # Fetch open orders for this market
            orders_response = await self.indexer_client.fetch_spot_orders(
                market_ids=[market_id],
                subaccount_id=self.address.get_subaccount_id(0),
                pagination=PaginationOption(limit=100)
            )
            
            if not orders_response or 'orders' not in orders_response:
                log(f"⚠️ No orders response from API for cancellation", self.wallet_id)
                return []
            
            orders = orders_response['orders']
            if len(orders) == 0:
                log(f"⚠️ No open orders found to cancel (orderbook may be too fresh)", self.wallet_id)
                return []
            
            log(f"📋 Found {len(orders)} open orders, selecting {min(num_to_cancel, len(orders))} to cancel", self.wallet_id)
            
            # Sort by order_hash to get consistent ordering
            sorted_orders = sorted(orders, key=lambda x: x.get('orderHash', ''))
            
            # Select oldest orders to cancel
            orders_to_cancel = []
            for order in sorted_orders[:num_to_cancel]:
                # Extract order details from the order object
                order_type = order.get('orderType', '')
                is_buy = order_type.lower() == 'buy' or order_type.lower() == 'buy_po'
                
                # Spot orders are always limit orders (not market)
                is_market_order = False
                
                # Spot orders don't have conditionals
                is_conditional = False
                
                order_data = self.composer.order_data(
                    market_id=market_id,
                    subaccount_id=self.address.get_subaccount_id(0),
                    order_hash=order.get('orderHash'),
                    is_buy=is_buy,
                    is_market_order=is_market_order,
                    is_conditional=is_conditional
                )
                orders_to_cancel.append(order_data)
            
            log(f"🗑️ Selected {len(orders_to_cancel)} orders for cancellation", self.wallet_id)
            return orders_to_cancel
            
        except Exception as e:
            log(f"❌ Error fetching orders to cancel: {e}", self.wallet_id)
            return []
    
    async def send_batch_orders(self, spot_orders: list, spot_orders_to_cancel: list = None):
        """
        Professional batch order sender with intelligent sequence recovery
        """
        if spot_orders_to_cancel is None:
            spot_orders_to_cancel = []
            
        total_orders = len(spot_orders)
        total_cancellations = len(spot_orders_to_cancel)
        max_retries = 3
        base_delay = 0.5
        
        # Circuit breaker: If too many consecutive sequence errors, pause trading
        if self.consecutive_sequence_errors >= self.max_sequence_errors:
            log(f"🛑 Circuit breaker activated! Too many sequence errors ({self.consecutive_sequence_errors}). Cooling down...", self.wallet_id)
            await asyncio.sleep(5.0)
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
                    # Create batch update message
                    msg = self.composer.msg_batch_update_orders(
                        sender=self.address.to_acc_bech32(),
                        spot_orders_to_create=spot_orders,
                        derivative_orders_to_create=[],
                        spot_orders_to_cancel=spot_orders_to_cancel,
                        derivative_orders_to_cancel=[]
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
                    
                    if total_cancellations > 0:
                        log(f"✅ Placed {total_orders} orders, cancelled {total_cancellations} | TX: {tx_hash}", self.wallet_id)
                    else:
                        log(f"✅ Placed {total_orders} orders | TX: {tx_hash}", self.wallet_id)
                    
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
                
                # Check for TIMEOUT errors (code=30) - these are blockchain congestion, not our fault
                if 'timeout height' in error_str or 'code=30' in error_str:
                    log(f"⏰ TX timeout (blockchain congestion) - recreating broadcaster", self.wallet_id)
                    # Timeout errors mess up broadcaster's sequence - recreate it
                    await self.recreate_broadcaster()
                    
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt) * 2  # Longer wait for congestion
                        log(f"🔄 Waiting {delay}s for blockchain congestion to clear...", self.wallet_id)
                        await asyncio.sleep(delay)
                        continue
                
                # Check if it's a sequence mismatch error
                elif 'sequence mismatch' in error_str or 'incorrect account sequence' in error_str:
                    self.consecutive_sequence_errors += 1
                    self.trading_stats['sequence_errors'] += 1
                    
                    # Extract expected sequence from error if possible
                    expected_seq = self.extract_expected_sequence(str(e))
                    if expected_seq is not None:
                        log(f"🔧 Sequence mismatch! Blockchain expects: {expected_seq}", self.wallet_id)
                    
                    # Recreate broadcaster to reset sequence state
                    log(f"🔄 Recreating broadcaster to fix sequence...", self.wallet_id)
                    await self.recreate_broadcaster()
                    
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        log(f"🔄 Retrying in {delay}s after sequence fix...", self.wallet_id)
                        await asyncio.sleep(delay)
                        continue
                
                # Other errors
                else:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        log(f"⚠️ Error sending batch (attempt {attempt + 1}/{max_retries}): {error_str[:100]}", self.wallet_id)
                        await asyncio.sleep(delay)
                    else:
                        total_orders = len(spot_orders)
                        self.trading_stats['failed_orders'] += total_orders
                        log(f"❌ Failed to send batch after {max_retries} attempts: {error_str[:150]}", self.wallet_id)
    
    async def proactive_sequence_check(self):
        """Proactively check and refresh sequence if needed"""
        current_time = time.time()
        time_since_refresh = current_time - self.last_sequence_refresh
        
        # Refresh sequence every 30 seconds or if we haven't refreshed in a while
        if time_since_refresh > 30:
            log(f"🔄 Proactive sequence refresh ({time_since_refresh:.1f}s since last refresh)", self.wallet_id)
            await self.refresh_sequence(force=True)
    
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
            gas_price = await self.async_client.current_chain_gas_price()
            gas_price = int(gas_price * 1.3)
            
            self.broadcaster = MsgBroadcasterWithPk.new_using_gas_heuristics(
                network=self.network,
                private_key=self.private_key,
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
                
                # Skip if recently refreshed (unless forced)
                if not force and time_since_refresh < 1.0:
                    return
                
                await self.async_client.fetch_account(self.address.to_acc_bech32())
                old_sequence = self.sequence
                self.sequence = self.async_client.sequence
                self.account_number = self.async_client.number
                self.last_sequence_refresh = current_time
                
                if old_sequence != self.sequence or force:
                    log(f"🔄 Sequence updated: {old_sequence} → {self.sequence}", self.wallet_id)
                    
                # Add small delay to ensure sequence is properly updated
                await asyncio.sleep(0.5)
                
            except Exception as e:
                log(f"❌ Failed to refresh sequence: {e}", self.wallet_id)
    
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
    
    async def get_market_metadata(self, market_id: str) -> Dict:
        """Fetch and cache market metadata for proper price scaling"""
        if market_id in self.market_metadata:
            return self.market_metadata[market_id]
        
        try:
            # Fetch market details from indexer
            market = await self.indexer_client.fetch_spot_market(market_id=market_id)
            
            if market and 'market' in market:
                market_data = market['market']
                
                # Decimals are in nested tokenMeta objects
                base_decimals = 18  # default
                quote_decimals = 6  # default
                
                if 'baseTokenMeta' in market_data:
                    base_decimals = int(market_data['baseTokenMeta'].get('decimals', 18))
                if 'quoteTokenMeta' in market_data:
                    quote_decimals = int(market_data['quoteTokenMeta'].get('decimals', 6))
                
                metadata = {
                    'base_decimals': base_decimals,
                    'quote_decimals': quote_decimals,
                    'min_price_tick_size': market_data.get('min_price_tick_size'),
                    'min_quantity_tick_size': market_data.get('min_quantity_tick_size')
                }
                
                # Calculate price scale factor: prices need to be multiplied by 10^(base_decimals - quote_decimals)
                # This converts from (quote_unit per base_unit) to (quote_token per base_token)
                decimal_diff = metadata['base_decimals'] - metadata['quote_decimals']
                metadata['price_scale_factor'] = Decimal(10) ** decimal_diff if decimal_diff != 0 else Decimal(1)
                
                self.market_metadata[market_id] = metadata
                log(f"📊 Loaded market metadata: base_decimals={metadata['base_decimals']}, quote_decimals={metadata['quote_decimals']}, scale=10^{decimal_diff}", self.wallet_id)
                return metadata
        except Exception as e:
            log(f"⚠️ Could not fetch market metadata: {e}, using default scaling", self.wallet_id)
        
        # Default fallback
        return {
            'base_decimals': 18,
            'quote_decimals': 6,
            'price_scale_factor': Decimal('0.000000000001')  # 10^-12
        }
    
    async def get_market_price(self, market_id: str, market_symbol: str = "") -> float:
        """Get current testnet market price using LAST TRADE PRICE"""
        max_retries = 3
        retry_delay = 2.0  # Increased from 1.0 to 2.0
        
        for attempt in range(max_retries):
            try:
                # FIRST: Try to get last trade price
                try:
                    from pyinjective.client.model.pagination import PaginationOption
                    trades = await asyncio.wait_for(
                        self.indexer_client.fetch_spot_trades(
                            market_ids=[market_id],
                            pagination=PaginationOption(limit=1)
                        ),
                        timeout=5.0
                    )
                    
                    if trades and 'trades' in trades and len(trades['trades']) > 0:
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
                        
                        # Get market metadata for proper scaling
                        metadata = await self.get_market_metadata(market_id)
                        price_scale_factor = metadata['price_scale_factor']
                        
                        last_trade_price = float(trade_price * price_scale_factor)
                        log(f"📈 Using LAST TRADE price: ${last_trade_price:.4f} for {market_symbol}", self.wallet_id)
                        return last_trade_price
                        
                except Exception as trade_error:
                    # Don't log full error on first attempt for cleaner output
                    if attempt == max_retries - 1:
                        log(f"⚠️ Could not get last trade price after retries: {str(trade_error)[:100]}", self.wallet_id)
                
                # FALLBACK: Use orderbook mid-price if no recent trades
                orderbook = await asyncio.wait_for(
                    self.fetch_spot_orderbook_v2_failover(market_id=market_id, depth=10, force_chain=self.force_chain_queries),
                    timeout=15.0  # Increased timeout
                )
                
                if orderbook and 'orderbook' in orderbook:
                    buys = orderbook['orderbook'].get('buys', [])
                    sells = orderbook['orderbook'].get('sells', [])
                    
                    # Get market metadata for proper scaling
                    metadata = await self.get_market_metadata(market_id)
                    price_scale_factor = metadata['price_scale_factor']
                    
                    if buys and sells:
                        best_bid = Decimal(str(buys[0]['price']))
                        best_ask = Decimal(str(sells[0]['price']))
                        best_bid_scaled = best_bid * price_scale_factor
                        best_ask_scaled = best_ask * price_scale_factor
                        mid_price = float((best_bid_scaled + best_ask_scaled) / 2)
                        log(f"📊 Using ORDERBOOK mid-price: ${mid_price:.4f} for {market_symbol}", self.wallet_id)
                        return mid_price
                    elif buys:
                        best_bid = Decimal(str(buys[0]['price']))
                        best_bid_scaled = best_bid * price_scale_factor
                        return float(best_bid_scaled)
                    elif sells:
                        best_ask = Decimal(str(sells[0]['price']))
                        best_ask_scaled = best_ask * price_scale_factor
                        return float(best_ask_scaled)
                
                return 0.0
                
            except Exception as e:
                if attempt < max_retries - 1:
                    # Only log on last retry to reduce noise
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    error_msg = str(e)
                    if '503' in error_msg or 'UNAVAILABLE' in error_msg:
                        log(f"⚠️ Indexer API unavailable (503) - will use mainnet price", self.wallet_id)
                    else:
                        log(f"❌ Error getting market price: {error_msg[:150]}", self.wallet_id)
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
                    
                    # Find market by base/quote symbols
                    market_id = None
                    for market in markets_response['markets']:
                        base_symbol = market.get('baseTokenMeta', {}).get('symbol', '')
                        quote_symbol = market.get('quoteTokenMeta', {}).get('symbol', '')
                        
                        if (base_symbol.upper() == market_symbol.split('/')[0].upper() and 
                            quote_symbol.upper() == market_symbol.split('/')[1].upper()):
                            market_id = market.get('marketId')
                            break
                    
                    if not market_id:
                        return 0.0
                
                # Get mainnet orderbook
                orderbook = await asyncio.wait_for(
                    mainnet_indexer.fetch_spot_orderbook_v2(market_id=market_id, depth=10),
                    timeout=10.0
                )
                
                if orderbook and 'orderbook' in orderbook:
                    buys = orderbook['orderbook'].get('buys', [])
                    sells = orderbook['orderbook'].get('sells', [])
                    
                    # Fetch mainnet market metadata for proper scaling
                    mainnet_market = await mainnet_indexer.fetch_spot_market(market_id=market_id)
                    if mainnet_market and 'market' in mainnet_market:
                        market_data = mainnet_market['market']
                        
                        # Decimals are in nested tokenMeta objects
                        base_decimals = 18  # default
                        quote_decimals = 6  # default
                        
                        if 'baseTokenMeta' in market_data:
                            base_decimals = int(market_data['baseTokenMeta'].get('decimals', 18))
                        if 'quoteTokenMeta' in market_data:
                            quote_decimals = int(market_data['quoteTokenMeta'].get('decimals', 6))
                        
                        decimal_diff = base_decimals - quote_decimals
                        price_scale_factor = Decimal(10) ** decimal_diff if decimal_diff != 0 else Decimal(1)
                    else:
                        # Fallback to default
                        price_scale_factor = Decimal('0.000000000001')  # 10^-12
                    
                    if buys and sells:
                        best_bid = Decimal(str(buys[0]['price']))
                        best_ask = Decimal(str(sells[0]['price']))
                        best_bid_scaled = best_bid * price_scale_factor
                        best_ask_scaled = best_ask * price_scale_factor
                        mid_price = float((best_bid_scaled + best_ask_scaled) / 2)
                        return mid_price
                    elif buys:
                        best_bid = Decimal(str(buys[0]['price']))
                        best_bid_scaled = best_bid * price_scale_factor
                        return float(best_bid_scaled)
                    elif sells:
                        best_ask = Decimal(str(sells[0]['price']))
                        best_ask_scaled = best_ask * price_scale_factor
                        return float(best_ask_scaled)
                
                return 0.0
                
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    return 0.0
    
    def get_trading_summary(self) -> str:
        """Get trading summary"""
        runtime = time.time() - self.start_time
        hours, remainder = divmod(runtime, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        summary = f"\n{'='*60}\n"
        summary += f"📊 ENHANCED SPOT TRADING SUMMARY - {self.wallet_id.upper()}\n"
        summary += f"{'='*60}\n"
        summary += f"⏱️  Runtime: {int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}\n"
        summary += f"📦 Total Orders: {self.trading_stats['total_orders']}\n"
        summary += f"✅ Successful: {self.trading_stats['successful_orders']}\n"
        summary += f"❌ Failed: {self.trading_stats['failed_orders']}\n"
        summary += f"🔄 Total Transactions: {self.trading_stats['total_transactions']}\n"
        summary += f"⚠️  Sequence Errors: {self.trading_stats['sequence_errors']}\n"
        
        if self.trading_stats['markets']:
            summary += f"\n📈 Per Market:\n"
            for market, stats in self.trading_stats['markets'].items():
                summary += f"  {market}: {stats['orders']} orders, {stats['transactions']} transactions\n"
        
        summary += f"{'='*60}"
        return summary

async def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python spot_trader.py <wallet_id> [market_symbol]")
        print("Examples:")
        print("  python spot_trader.py wallet1                 # Trade all enabled spot markets")
        print("  python spot_trader.py wallet1 INJ/USDT       # Trade only INJ/USDT")
        print("  python spot_trader.py wallet1 stINJ/INJ      # Trade only stINJ/INJ")
        sys.exit(1)
    
    wallet_id = sys.argv[1]
    target_market = sys.argv[2] if len(sys.argv) > 2 else None
    
    trader = EnhancedSpotTrader(wallet_id, target_market=target_market)
    
    try:
        await trader.run()
    except KeyboardInterrupt:
        log(f"🛑 Enhanced Spot Trader stopped by user", wallet_id)
        # Show trading summary
        summary = trader.get_trading_summary()
        print(summary)
        log(f"📊 Trading session ended for {wallet_id}", wallet_id)

if __name__ == "__main__":
    asyncio.run(main())
