#!/usr/bin/env python3
"""
Enhanced Multi-Wallet Parallel Trader for Injective Testnet
Advanced market making system with inter-wallet trading and dynamic order management

WHAT THIS ENHANCED SCRIPT DOES:
- Uses batch update orders to solve sequencing issues
- Enables wallets to trade between each other with random matching
- Automatically refreshes orders when mainnet price changes by 2%
- Tracks order fills using chainstreamer to avoid cancelling matched orders
- Creates realistic market activity with randomized order sizes and timing
- Maintains fresh orderbooks that follow mainnet price movements
"""

import asyncio
import json
import signal
import sys
import os
import random
import time
from typing import Dict, List, Optional, Set, Tuple, Any
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass, field

# Injective blockchain libraries
from pyinjective.async_client_v2 import AsyncClient
from pyinjective.indexer_client import IndexerClient
from pyinjective.core.network import Network
from pyinjective.core.broadcaster import MsgBroadcasterWithPk
from pyinjective import PrivateKey, Address

# Add parent directory to path to import from utils
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import the secure wallet loader
from utils.secure_wallet_loader import load_wallets_from_env

# Load the markets configuration
print("📁 Loading market configuration...")
with open('config/markets_config.json', 'r') as f:
    markets_config = json.load(f)

# Load wallet configuration securely
wallets_config = load_wallets_from_env()

@dataclass
class OrderInfo:
    """Track individual order information"""
    order_hash: str
    market_id: str
    side: str
    price: float
    quantity: float
    timestamp: datetime
    wallet_id: str
    is_inter_wallet: bool = False
    matched_quantity: float = 0.0
    status: str = "active"  # active, partial_filled, filled, cancelled

@dataclass
class MarketState:
    """Track market state and price history"""
    market_id: str
    market_symbol: str
    last_mainnet_price: float = 0.0
    last_testnet_price: float = 0.0
    last_refresh_time: datetime = field(default_factory=datetime.now)
    price_change_percent: float = 0.0
    active_orders: List[Dict] = field(default_factory=list)
    inter_wallet_orders: List[OrderInfo] = field(default_factory=list)

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
        
        # Check if log file is too large (>10MB) and rotate if needed
        log_file_path = "logs/enhanced_trading.log"
        if os.path.exists(log_file_path) and os.path.getsize(log_file_path) > 10 * 1024 * 1024:
            backup_name = f"logs/enhanced_trading_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            os.rename(log_file_path, backup_name)
            print(f"📁 Log file rotated: {backup_name}")
        
        with open(log_file_path, "a", encoding="utf-8") as log_file:
            log_file.write(log_entry)
    except Exception as e:
        print(f"⚠️ Failed to write to log file: {e}")

class EnhancedWalletTrader:
    """
    Enhanced wallet trader with batch orders, inter-wallet trading, and dynamic order management
    """
    
    def __init__(self, wallet_id: str, private_key: str, markets_config: List[Dict]):
        self.wallet_id = wallet_id
        self.private_key = private_key
        self.markets_config = markets_config
        
        # Network setup
        self.network = Network.testnet()
        
        # Client connections
        self.async_client = None
        self.indexer_client = None
        self.composer = None
        self.broadcaster = None
        self.address = None
        
        # Account information
        self.sequence = 0
        self.account_number = 0
        
        # Control flags
        self.is_running = False
        self.in_cooldown = False
        self.cooldown_until = 0
        
        # Enhanced order tracking
        self.market_states: Dict[str, MarketState] = {}
        self.order_tracking: Dict[str, OrderInfo] = {}  # order_hash -> OrderInfo
        self.inter_wallet_orders: List[OrderInfo] = []
        
        # Other traders for inter-wallet trading
        self.other_traders: Dict[str, 'EnhancedWalletTrader'] = {}
        
        # Trading statistics
        self.trading_stats = {
            'total_trades': 0,
            'successful_trades': 0,
            'failed_trades': 0,
            'inter_wallet_trades': 0,
            'orders_refreshed': 0,
            'markets': {}
        }
        
        # Chainstreamer for order tracking
        self.chainstreamer_task = None
        self.order_fill_events = asyncio.Queue()
        
    async def initialize(self):
        """Initialize the enhanced wallet trader"""
        try:
            log(f"🔧 Initializing enhanced trader {self.wallet_id}...", self.wallet_id)
            
            # Create clients
            self.async_client = AsyncClient(self.network)
            self.indexer_client = IndexerClient(self.network)
            self.composer = await self.async_client.composer()
            
            # Set up wallet identity
            private_key_obj = PrivateKey.from_hex(self.private_key)
            self.address = private_key_obj.to_public_key().to_address()
            
            # Get account information
            await self.async_client.fetch_account(self.address.to_acc_bech32())
            self.sequence = self.async_client.sequence
            self.account_number = self.async_client.number
            
            # Set up broadcaster with enhanced settings for network congestion
            gas_price = await self.get_gas_price_with_retry()
            gas_price = int(gas_price * 1.3)  # Increased gas price for faster processing
            
            self.broadcaster = MsgBroadcasterWithPk.new_using_gas_heuristics(
                network=self.network,
                private_key=self.private_key,
                gas_price=gas_price
            )
            
            # Set timeout height offset for network congestion (increased for better reliability)
            self.broadcaster.timeout_height_offset = 120  # Increased from 60 to 120 blocks
            
            # Initialize market states
            await self.initialize_market_states()
            
            # Start chainstreamer for order tracking
            await self.start_chainstreamer()
            
            log(f"✅ Enhanced trader initialized: {self.address.to_acc_bech32()}", self.wallet_id)
            log(f"   Sequence: {self.sequence}, Account: {self.account_number}", self.wallet_id)
            
        except Exception as e:
            log(f"❌ Failed to initialize enhanced trader: {e}", self.wallet_id)
            raise
    
    async def initialize_market_states(self):
        """Initialize market states for all enabled markets"""
        for market_symbol, market_config in markets_config['markets'].items():
            if market_config.get('enabled', False):
                market_id = market_config.get('testnet_market_id', market_config.get('market_id'))
                self.market_states[market_id] = MarketState(
                    market_id=market_id,
                    market_symbol=market_symbol
                )
                log(f"📊 Initialized market state for {market_symbol}", self.wallet_id, market_id)
    
    async def start_chainstreamer(self):
        """Start chainstreamer to track order fills and account updates"""
        try:
            log(f"🔗 Starting chainstreamer for real-time order tracking", self.wallet_id)
            
            # Create chainstream filters for this wallet
            subaccount_id = self.address.get_subaccount_id(0)
            
            # Get all market IDs we're trading
            market_ids = list(self.market_states.keys())
            
            # Create filters
            spot_orders_filter = self.composer.chain_stream_orders_filter(
                subaccount_ids=[subaccount_id], 
                market_ids=market_ids
            )
            
            # Bank balances filter for sequence updates
            bank_balances_filter = self.composer.chain_stream_bank_balances_filter(
                accounts=[self.address.to_acc_bech32()]
            )
            
            # Start chainstream task
            self.chainstreamer_task = asyncio.create_task(
                self.async_client.listen_chain_stream_updates(
                    callback=self.chain_stream_event_processor,
                    on_end_callback=self.stream_closed_processor,
                    on_status_callback=self.stream_error_processor,
                    spot_orders_filter=spot_orders_filter,
                    bank_balances_filter=bank_balances_filter,
                )
            )
            
            log(f"✅ Chainstreamer started successfully", self.wallet_id)
            
        except Exception as e:
            log(f"❌ Failed to start chainstreamer: {e}", self.wallet_id)
    
    async def chain_stream_event_processor(self, event: Dict[str, Any]):
        """Process chainstream events for order tracking and sequence management"""
        try:
            # Handle order updates
            if 'spot_orders' in event:
                await self.process_order_updates(event['spot_orders'])
            
            # Handle bank balance updates (for sequence tracking)
            if 'bank_balances' in event:
                await self.process_balance_updates(event['bank_balances'])
                
        except Exception as e:
            log(f"❌ Error processing chainstream event: {e}", self.wallet_id)
    
    async def process_order_updates(self, order_events):
        """Process order update events from chainstream"""
        try:
            for order_event in order_events:
                order_hash = order_event.get('order_hash', '')
                order_state = order_event.get('state', '')
                
                # Remove filled or cancelled orders from tracking
                if order_state in ['filled', 'cancelled']:
                    if order_hash in self.order_tracking:
                        order_info = self.order_tracking[order_hash]
                        log(f"🗑️ Order {order_hash[:16]}... {order_state} - removing from tracking", 
                            self.wallet_id, order_info.market_id)
                        
                        # Remove from all tracking structures
                        del self.order_tracking[order_hash]
                        
                        # Remove from market state
                        for market_id, market_state in self.market_states.items():
                            if order_hash in market_state.active_orders:
                                del market_state.active_orders[order_hash]
                        
                        # Remove from inter-wallet orders
                        self.inter_wallet_orders = [
                            order for order in self.inter_wallet_orders 
                            if order.order_hash != order_hash
                        ]
                        
                        log(f"✅ Order cleanup completed for {order_hash[:16]}...", self.wallet_id)
                
                # Update order status
                elif order_state in ['booked', 'partial_filled']:
                    if order_hash in self.order_tracking:
                        self.order_tracking[order_hash].status = order_state
                        log(f"📝 Order {order_hash[:16]}... status updated to {order_state}", self.wallet_id)
                        
        except Exception as e:
            log(f"❌ Error processing order updates: {e}", self.wallet_id)
    
    async def process_balance_updates(self, balance_events):
        """Process balance update events for sequence management"""
        try:
            # Balance updates can indicate sequence changes
            # We should refresh our sequence number when we see balance changes
            await self.refresh_sequence()
            
        except Exception as e:
            log(f"❌ Error processing balance updates: {e}", self.wallet_id)
    
    def stream_error_processor(self, exception):
        """Handle chainstream errors"""
        log(f"❌ Chainstream error: {exception}", self.wallet_id)
    
    def stream_closed_processor(self):
        """Handle chainstream closure"""
        log(f"🛑 Chainstream closed", self.wallet_id)
    
    # Note: check_order_statuses method removed - now using ChainStream for real-time tracking
    
    def get_market_config(self, market_id: str) -> Optional[Dict]:
        """Get market configuration by market ID"""
        for market_symbol, market_config in markets_config['markets'].items():
            if market_config.get('testnet_market_id') == market_id or market_config.get('market_id') == market_id:
                return market_config
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
                    await asyncio.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                else:
                    log(f"❌ Error getting market price after {max_retries} attempts: {e}", self.wallet_id, market_id)
                    return 0.0
    
    async def get_mainnet_price(self, market_symbol: str, mainnet_market_id: str = None) -> float:
        """Get current mainnet market price with retry logic"""
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                mainnet_network = Network.mainnet()
                mainnet_indexer = IndexerClient(mainnet_network)
                
                if mainnet_market_id:
                    market_id = mainnet_market_id
                else:
                    # Search for market ID
                    markets_response = await asyncio.wait_for(
                        mainnet_indexer.fetch_spot_markets(),
                        timeout=10.0
                    )
                    
                    if not markets_response or 'markets' not in markets_response:
                        return 0.0
                    
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
                
                # Get orderbook
                orderbook = await asyncio.wait_for(
                    mainnet_indexer.fetch_spot_orderbook_v2(market_id=market_id, depth=10),
                    timeout=10.0
                )
                
                if orderbook and 'orderbook' in orderbook:
                    buys = orderbook['orderbook'].get('buys', [])
                    sells = orderbook['orderbook'].get('sells', [])
                    
                    if buys and sells:
                        best_bid = Decimal(str(buys[0]['price']))
                        best_ask = Decimal(str(sells[0]['price']))
                        
                        # Scale prices
                        if 'stinj' in market_symbol.lower():
                            price_scale_factor = Decimal('1')
                        else:
                            price_scale_factor = Decimal('1000000000000')
                        
                        best_bid_scaled = best_bid * price_scale_factor
                        best_ask_scaled = best_ask * price_scale_factor
                        
                        mid_price = float((best_bid_scaled + best_ask_scaled) / 2)
                        return mid_price
                
                return 0.0
                
            except Exception as e:
                if attempt < max_retries - 1:
                    log(f"⚠️ Error getting mainnet price (attempt {attempt + 1}/{max_retries}): {e}", self.wallet_id)
                    await asyncio.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                else:
                    log(f"❌ Error getting mainnet price after {max_retries} attempts: {e}", self.wallet_id)
                    return 0.0
    
    async def refresh_sequence(self):
        """Refresh sequence number from blockchain with retry logic"""
        max_retries = 3
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            try:
                await self.async_client.fetch_account(self.address.to_acc_bech32())
                old_sequence = self.sequence
                self.sequence = self.async_client.sequence
                self.account_number = self.async_client.number
                if old_sequence != self.sequence:
                    log(f"🔄 Sequence updated: {old_sequence} → {self.sequence}", self.wallet_id)
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    log(f"⚠️ Failed to refresh sequence (attempt {attempt + 1}/{max_retries}): {e}", self.wallet_id)
                    await asyncio.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                else:
                    log(f"❌ Failed to refresh sequence after {max_retries} attempts: {e}", self.wallet_id)
                    return False

    async def recreate_broadcaster(self):
        """Recreate broadcaster to reset its internal sequence counter"""
        try:
            # Refresh sequence from blockchain first
            await self.refresh_sequence()
            
            gas_price = await self.get_gas_price_with_retry()
            gas_price = int(gas_price * 1.3)  # Increased gas price for faster processing
            
            self.broadcaster = MsgBroadcasterWithPk.new_using_gas_heuristics(
                network=self.network,
                private_key=self.private_key,
                gas_price=gas_price
            )
            
            # Set timeout height offset for network congestion
            self.broadcaster.timeout_height_offset = 120
            
            # Add delay to ensure broadcaster gets fresh sequence
            await asyncio.sleep(1.0)
            
        except Exception as e:
            log(f"❌ Failed to recreate broadcaster: {e}", self.wallet_id)

    async def get_gas_price_with_retry(self) -> int:
        """Get gas price with retry logic"""
        max_retries = 3
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            try:
                gas_price = await self.async_client.current_chain_gas_price()
                return int(gas_price)
            except Exception as e:
                if attempt < max_retries - 1:
                    log(f"⚠️ Failed to get gas price (attempt {attempt + 1}/{max_retries}): {e}", self.wallet_id)
                    await asyncio.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                else:
                    log(f"❌ Failed to get gas price after {max_retries} attempts, using default: {e}", self.wallet_id)
                    return 1000000000000  # Default gas price fallback

    async def place_batch_orders(self, market_id: str, orders_list: List[Dict], market_symbol: str) -> bool:
        """
        Place multiple orders using batch update to solve sequencing issues
        
        Args:
            market_id: Market ID to place orders on
            orders_list: List of order dictionaries with side, price, quantity
            market_symbol: Market symbol for logging
        """
        try:
            if not orders_list:
                return True
            
            log(f"🚀 Placing batch of {len(orders_list)} orders", self.wallet_id, market_id)
            
            # Add delay to prevent sequence conflicts between wallets
            await asyncio.sleep(random.uniform(1.0, 2.0))
            
            # Create order messages
            spot_orders_to_create = []
            derivative_orders_to_create = []
            
            market_config = self.get_market_config(market_id)
            if not market_config:
                log(f"❌ Market config not found for {market_id}", self.wallet_id)
                return False
            
            subaccount_id = self.address.get_subaccount_id(0)
            
            for order_data in orders_list:
                side = order_data['side']
                quantity = Decimal(str(order_data['quantity']))
                order_type = order_data.get('order_type', 'LIMIT')
                
                # Handle market orders differently
                if order_type == 'MARKET':
                    # For market orders, we create them as limit orders with very aggressive pricing
                    # This simulates market order behavior by ensuring immediate execution
                    if market_config.get('type') == 'spot':
                        # Get current market price and create aggressive limit order
                        # For buy market orders, use a very high price to ensure execution
                        # For sell market orders, use a very low price to ensure execution
                        if side == 'BUY':
                            # Use a price much higher than current to ensure immediate execution
                            aggressive_price = Decimal("999999.999")  # Very high price
                        else:
                            # Use a price much lower than current to ensure immediate execution
                            aggressive_price = Decimal("0.001")  # Very low price
                        
                        market_order = self.composer.spot_order(
                            market_id=market_id,
                            subaccount_id=subaccount_id,
                            fee_recipient=self.address.to_acc_bech32(),
                            price=aggressive_price,
                            quantity=quantity,
                            order_type=side.upper(),
                            cid=None
                        )
                        spot_orders_to_create.append(market_order)
                    else:
                        # For derivative market orders
                        if side == 'BUY':
                            aggressive_price = Decimal("999999.999")
                        else:
                            aggressive_price = Decimal("0.001")
                        
                        market_order = self.composer.derivative_order(
                            market_id=market_id,
                            subaccount_id=subaccount_id,
                            fee_recipient=self.address.to_acc_bech32(),
                            price=aggressive_price,
                            quantity=quantity,
                            order_type=side.upper(),
                            cid=None
                        )
                        derivative_orders_to_create.append(market_order)
                else:
                    # Handle limit orders
                    price = Decimal(str(order_data['price']))
                    
                    # Round price to valid tick size
                    tick_size = Decimal("0.001")
                    price_rounded = (price / tick_size).quantize(Decimal("1")) * tick_size
                    
                    # Create SpotOrder object for batch update
                    if market_config.get('type') == 'spot':
                        spot_order = self.composer.spot_order(
                            market_id=market_id,
                            subaccount_id=subaccount_id,
                            fee_recipient=self.address.to_acc_bech32(),
                            price=price_rounded,
                            quantity=quantity,
                            order_type=side.upper(),
                            cid=None
                        )
                        spot_orders_to_create.append(spot_order)
                    else:
                        # For derivative orders
                        derivative_order = self.composer.derivative_order(
                            market_id=market_id,
                            subaccount_id=subaccount_id,
                            fee_recipient=self.address.to_acc_bech32(),
                            price=price_rounded,
                            quantity=quantity,
                            order_type=side.upper(),
                            cid=None
                        )
                        derivative_orders_to_create.append(derivative_order)
            
            # Create batch update message
            msg = self.composer.msg_batch_update_orders(
                sender=self.address.to_acc_bech32(),
                derivative_orders_to_create=derivative_orders_to_create,
                spot_orders_to_create=spot_orders_to_create,
                derivative_orders_to_cancel=[],
                spot_orders_to_cancel=[]
            )
            
            # Update gas price and timeout before broadcasting
            gas_price = await self.get_gas_price_with_retry()
            gas_price = int(gas_price * 1.3)  # Increase gas price buffer to 30%
            self.broadcaster.update_gas_price(gas_price=gas_price)
            
            # Set longer timeout for batch transactions
            self.broadcaster.timeout_height_offset = 30  # 30 blocks timeout
            
            # Broadcast batch update with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = await self.broadcaster.broadcast([msg])
                    break  # Success, exit retry loop
                except Exception as e:
                    error_str = str(e).lower()
                    if ("timeout height" in error_str or "sequence mismatch" in error_str) and attempt < max_retries - 1:
                        log(f"⚠️ {error_str} error on attempt {attempt + 1}, retrying...", self.wallet_id, market_id)
                        # Recreate broadcaster to reset its internal sequence counter
                        await self.recreate_broadcaster()
                        # Longer delay for sequence mismatches to allow blockchain to catch up
                        delay = 8 + attempt * 3 if "sequence mismatch" in error_str else 2 + attempt
                        await asyncio.sleep(delay)
                        continue
                    else:
                        raise  # Re-raise if not a retryable error or max retries reached
            
            # Check response
            tx_hash = (response.get('txhash') or 
                      response.get('txResponse', {}).get('txhash') or
                      response.get('tx_response', {}).get('txhash') or
                      'unknown')
            
            if tx_hash and tx_hash != 'unknown':
                log(f"✅ Batch orders placed successfully! TX: {tx_hash}", self.wallet_id, market_id)
                
                # Store orders in market state for inter-wallet trading
                if market_id not in self.market_states:
                    self.market_states[market_id] = MarketState()
                
                # Generate order hashes for tracking
                for i, order_data in enumerate(orders_list):
                    # Create a unique order hash for tracking
                    order_hash = f"{self.wallet_id}_{market_id}_{int(time.time())}_{i}"
                    
                    self.market_states[market_id].active_orders.append({
                        'price': order_data['price'],
                        'quantity': order_data['quantity'],
                        'side': order_data['side'],
                        'timestamp': time.time(),
                        'is_inter_wallet': order_data.get('is_inter_wallet', False),
                        'order_hash': order_hash,
                        'tx_hash': tx_hash
                    })
                
                # Orders will be tracked automatically via ChainStream
                log(f"📝 Orders will be tracked via ChainStream", self.wallet_id, market_id)
                
                return True
            else:
                log(f"❌ Batch order placement failed", self.wallet_id, market_id)
                return False
                
        except Exception as e:
            log(f"❌ Error placing batch orders: {e}", self.wallet_id, market_id)
            # Handle different types of errors
            error_str = str(e).lower()
            if "sequence mismatch" in error_str:
                log(f"🔄 Sequence mismatch detected, refreshing sequence", self.wallet_id)
                await self.refresh_sequence()
                await self.enter_cooldown(5)  # Short cooldown for sequence issues
            elif "timeout height" in error_str:
                log(f"⏰ Transaction timeout detected, entering cooldown", self.wallet_id)
                await self.enter_cooldown(10)  # Longer cooldown for timeout issues
            elif "insufficient funds" in error_str:
                log(f"💰 Insufficient funds detected, entering cooldown", self.wallet_id)
                await self.enter_cooldown(30)  # Long cooldown for funding issues
            else:
                log(f"❓ Unknown error, entering short cooldown", self.wallet_id)
                await self.enter_cooldown(5)  # Default cooldown
            return False
    
    # Note: track_batch_orders method removed - now using ChainStream for automatic order tracking
    
    async def find_matching_orders_for_new_order(self, market_id: str, new_order: Dict) -> List[Dict]:
        """
        Find existing orders from OTHER wallets that can match with a new order from current wallet
        Returns list of matching orders that can be traded against
        """
        matches = []
        
        # Get the new order details
        new_side = new_order['side'].upper()
        new_price = float(new_order['price'])
        new_quantity = float(new_order['quantity'])
        
        # Get all active orders from OTHER wallets for this market
        for wallet_id, trader in self.other_traders.items():
            if market_id in trader.market_states:
                market_state = trader.market_states[market_id]
                for existing_order in market_state.active_orders:
                    existing_side = existing_order['side'].upper()
                    existing_price = float(existing_order['price'])
                    existing_quantity = float(existing_order['quantity'])
                    
                    # Skip if same side (can't match buy with buy or sell with sell)
                    if new_side == existing_side:
                        continue
                    
                    # Check if prices can match
                    can_match = False
                    if new_side == 'BUY' and existing_side == 'SELL':
                        # Buy order can match if buy price >= sell price
                        can_match = new_price >= existing_price
                    elif new_side == 'SELL' and existing_side == 'BUY':
                        # Sell order can match if sell price <= buy price
                        can_match = new_price <= existing_price
                    
                    if can_match:
                        # Calculate trade size (minimum of both quantities)
                        trade_quantity = min(new_quantity, existing_quantity)
                        
                        # Only create trade if quantity is meaningful (> 0.001)
                        if trade_quantity > 0.001:
                            # Use the existing order's price as the trade price
                            trade_price = existing_price
                            
                            matches.append({
                                'other_wallet_id': wallet_id,
                                'other_order': existing_order,
                                'trade_price': trade_price,
                                'trade_quantity': trade_quantity,
                                'market_id': market_id,
                                'new_order_side': new_side,
                                'existing_order_side': existing_side
                            })
        
        return matches
    
    async def execute_matching_trade(self, match: Dict) -> bool:
        """
        Execute a trade by placing an opposite order from the current wallet to match an existing order
        """
        max_retries = 2
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                other_wallet_id = match['other_wallet_id']
                trade_price = float(match['trade_price'])
                trade_quantity = float(match['trade_quantity'])
                market_id = match['market_id']
                new_order_side = match['new_order_side']
                existing_order_side = match['existing_order_side']
                
                # Validate price and quantity
                if trade_price <= 0 or trade_quantity <= 0:
                    log(f"❌ Invalid trade parameters: price={trade_price}, quantity={trade_quantity}", 
                        self.wallet_id, market_id)
                    return False
                
                log(f"🤝 Creating matching trade: {self.wallet_id} {existing_order_side} {trade_quantity} at ${trade_price} to match {other_wallet_id}'s {new_order_side} order", 
                    self.wallet_id, market_id)
                
                # Create the opposite order to match the existing order
                opposite_side = 'SELL' if new_order_side == 'BUY' else 'BUY'
                
                # Create a market order that will immediately match
                matching_order = {
                    'side': opposite_side,
                    'price': trade_price,  # Use the existing order's price
                    'quantity': trade_quantity,
                    'order_type': 'MARKET',  # This will be an aggressive limit order
                    'is_inter_wallet': True
                }
                
                # Place the matching order using the current wallet
                market_symbol = self.get_market_config(market_id).get('symbol', 'UNKNOWN')
                success = await self.place_batch_orders(market_id, [matching_order], market_symbol)
                
                if success:
                    log(f"✅ Successfully placed matching {opposite_side} order for {trade_quantity} at ${trade_price}", 
                        self.wallet_id, market_id)
                    
                    # Update statistics
                    self.trading_stats['inter_wallet_trades'] += 1
                    return True
                else:
                    if attempt < max_retries - 1:
                        log(f"⚠️ Failed to place matching order (attempt {attempt + 1}/{max_retries}), retrying...", 
                            self.wallet_id, market_id)
                        await asyncio.sleep(retry_delay * (attempt + 1))
                        continue
                    else:
                        log(f"❌ Failed to place matching order after {max_retries} attempts", self.wallet_id, market_id)
                        return False
                
            except Exception as e:
                if attempt < max_retries - 1:
                    log(f"⚠️ Error executing matching trade (attempt {attempt + 1}/{max_retries}): {e}", self.wallet_id, market_id)
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    log(f"❌ Error executing matching trade after {max_retries} attempts: {e}", self.wallet_id, market_id)
                    return False
    
    def get_market_config(self, market_id: str) -> Dict:
        """Get market configuration for a given market ID"""
        for symbol, config in self.markets_config.items():
            if config.get('testnet_market_id') == market_id:
                return config
        return {}
    
    async def process_inter_wallet_trading(self, market_id: str, new_orders: List[Dict]):
        """
        Process inter-wallet trading by checking if new orders can match existing orders from other wallets
        """
        try:
            if not new_orders:
                return
            
            # Add delay before processing inter-wallet trades to avoid sequence conflicts
            await asyncio.sleep(random.uniform(2.0, 4.0))  # 2-4 second delay
            
            executed_trades = 0
            
            # Check each new order for potential matches
            for new_order in new_orders:
                # Find matching orders from other wallets
                matches = await self.find_matching_orders_for_new_order(market_id, new_order)
                
                if matches:
                    # Execute the first match (most likely to succeed)
                    match = matches[0]
                    
                    # Add some randomness to make it more natural
                    if random.random() < 0.6:  # 60% chance to execute each match (reduced from 80%)
                        success = await self.execute_matching_trade(match)
                        if success:
                            executed_trades += 1
                            # Delay between trades to avoid sequence conflicts
                            await asyncio.sleep(random.uniform(1.0, 2.0))
                            break  # Only execute one trade per order to avoid conflicts
            
            if executed_trades > 0:
                log(f"✅ Executed {executed_trades} inter-wallet trades for {market_id}", 
                    self.wallet_id, market_id)
            
        except Exception as e:
            log(f"❌ Error in inter-wallet trading: {e}", self.wallet_id, market_id)

    async def create_enhanced_orderbook(self, market_id: str, testnet_price: float, mainnet_price: float, market_symbol: str, enable_inter_wallet_trading: bool = True, use_aggressive_mode: bool = True):
        """
        Create enhanced orderbook with batch orders and inter-wallet trading
        """
        try:
            if await self.check_cooldown():
                log(f"⏸️ {self.wallet_id} skipping order placement due to cooldown", self.wallet_id, market_id)
                return
            
            log(f"🎯 Creating enhanced orderbook for {market_symbol}", self.wallet_id, market_id)
            
            # Calculate price difference and direction
            price_diff = abs(testnet_price - mainnet_price)
            price_diff_percent = (price_diff / mainnet_price) * 100
            
            # Determine price correction direction
            if testnet_price < mainnet_price:
                correction_direction = "UP"
                log(f"📈 {self.wallet_id} - Price diff: {price_diff_percent:.2f}% | Need to move price UP", 
                    self.wallet_id, market_id)
            else:
                correction_direction = "DOWN"
                log(f"📉 {self.wallet_id} - Price diff: {price_diff_percent:.2f}% | Need to move price DOWN", 
                    self.wallet_id, market_id)
            
            # Create order list for batch placement
            orders_list = []
            
            # Generate randomized order sizes (larger sizes for more effective price correction)
            order_sizes = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0, 15.0, 18.0, 20.0, 25.0, 30.0, 35.0, 40.0]
            random.shuffle(order_sizes)
            order_sizes = order_sizes[:12]  # Use 12 orders total (6 per side)
            
            # Choose strategy based on mode
            if use_aggressive_mode:
                # AGGRESSIVE PRICE CORRECTION STRATEGY
                # Create orders that specifically target moving price toward mainnet
                
                if correction_direction == "UP":
                    # Testnet price is too low - need to push price UP
                    # Place aggressive BUY orders closer to mainnet price
                    # Place minimal SELL orders to avoid counteracting the upward pressure
                    
                    # Aggressive BUY orders targeting mainnet price (80% of orders)
                    buy_price_levels = [
                        testnet_price * 1.005,  # Just above current price
                        testnet_price * 1.010,  # 1% above
                        testnet_price * 1.015,  # 1.5% above
                        testnet_price * 1.020,  # 2% above
                        testnet_price * 1.025,  # 2.5% above
                        mainnet_price * 0.98,   # Close to mainnet (2% below)
                        mainnet_price * 0.985,  # Very close to mainnet
                        mainnet_price * 0.99,   # Almost at mainnet
                        mainnet_price * 0.995,  # Very close to mainnet
                        mainnet_price * 1.0,    # At mainnet price
                    ]
                    
                    # Minimal SELL orders to avoid counteracting (20% of orders)
                    sell_price_levels = [
                        mainnet_price * 1.01,   # Just above mainnet
                        mainnet_price * 1.02,   # 2% above mainnet
                    ]
                    
                    # Allocate more orders to BUY side for upward pressure
                    buy_sizes = order_sizes[:10]  # 10 aggressive buy orders
                    sell_sizes = order_sizes[10:12]  # Only 2 sell orders
                
                else:
                    # Testnet price is too high - need to push price DOWN
                    # Place aggressive SELL orders closer to mainnet price
                    # Place minimal BUY orders to avoid counteracting the downward pressure
                    
                    # Aggressive SELL orders targeting mainnet price (80% of orders)
                    sell_price_levels = [
                        testnet_price * 0.995,  # Just below current price
                        testnet_price * 0.990,  # 1% below
                        testnet_price * 0.985,  # 1.5% below
                        testnet_price * 0.980,  # 2% below
                        testnet_price * 0.975,  # 2.5% below
                        mainnet_price * 1.02,   # Close to mainnet (2% above)
                        mainnet_price * 1.015,  # Very close to mainnet
                        mainnet_price * 1.01,   # Almost at mainnet
                        mainnet_price * 1.005,  # Very close to mainnet
                        mainnet_price * 1.0,    # At mainnet price
                    ]
                    
                    # Minimal BUY orders to avoid counteracting (20% of orders)
                    buy_price_levels = [
                        mainnet_price * 0.99,   # Just below mainnet
                        mainnet_price * 0.98,   # 2% below mainnet
                    ]
                    
                    # Allocate more orders to SELL side for downward pressure
                    sell_sizes = order_sizes[:10]  # 10 aggressive sell orders
                    buy_sizes = order_sizes[10:12]  # Only 2 buy orders
            else:
                # NORMAL BALANCED TRADING MODE
                # Create balanced orderbook around current testnet price for normal market activity
                
                # Balanced BUY orders (below current testnet price)
                buy_price_levels = [
                    testnet_price * 0.995, testnet_price * 0.996, testnet_price * 0.997, 
                    testnet_price * 0.998, testnet_price * 0.999, testnet_price * 1.000
                ]
                
                # Balanced SELL orders (above current testnet price)
                sell_price_levels = [
                    testnet_price * 1.001, testnet_price * 1.002, testnet_price * 1.003, 
                    testnet_price * 1.004, testnet_price * 1.005, testnet_price * 1.006
                ]
                
                # Split order sizes between buy and sell (50/50)
                buy_sizes = order_sizes[:6]
                sell_sizes = order_sizes[6:12]
            
            # Create BUY orders (asymmetric distribution for price correction OR balanced for normal mode)
            for i in range(len(buy_sizes)):
                if i < len(buy_price_levels):  # Ensure we don't exceed price levels
                    orders_list.append({
                        'side': 'BUY',
                        'price': buy_price_levels[i],
                        'quantity': buy_sizes[i],
                        'is_inter_wallet': False,
                        'order_type': 'LIMIT'
                    })
            
            # Create SELL orders (asymmetric distribution for price correction)
            for i in range(len(sell_sizes)):
                if i < len(sell_price_levels):  # Ensure we don't exceed price levels
                    orders_list.append({
                        'side': 'SELL',
                        'price': sell_price_levels[i],
                        'quantity': sell_sizes[i],
                        'is_inter_wallet': False,
                        'order_type': 'LIMIT'
                    })
            
            # Add market orders based on mode
            if use_aggressive_mode:
                # Add aggressive market orders for immediate price impact
                if correction_direction == "UP":
                    # Add aggressive BUY market orders to push price up
                    market_orders_count = 6  # More aggressive buy orders
                    for i in range(market_orders_count):
                        # Very aggressive buy prices to create immediate upward pressure
                        aggressive_price = testnet_price * (1.003 + i * 0.002)  # 0.3% to 1.3% above current price
                        orders_list.append({
                            'side': 'BUY',
                            'price': aggressive_price,
                            'quantity': random.choice([1.0, 1.5, 2.0, 2.5, 3.0]),  # Larger quantities for impact
                            'is_inter_wallet': True,
                            'order_type': 'MARKET'
                        })
                else:
                    # Add aggressive SELL market orders to push price down
                    market_orders_count = 6  # More aggressive sell orders
                    for i in range(market_orders_count):
                        # Very aggressive sell prices to create immediate downward pressure
                        aggressive_price = testnet_price * (0.997 - i * 0.002)  # 0.3% to 1.3% below current price
                        orders_list.append({
                            'side': 'SELL',
                            'price': aggressive_price,
                            'quantity': random.choice([1.0, 1.5, 2.0, 2.5, 3.0]),  # Larger quantities for impact
                            'is_inter_wallet': True,
                            'order_type': 'MARKET'
                        })
            else:
                # Add balanced market orders for normal trading activity
                market_orders_count = 4  # Balanced market orders (2 buy, 2 sell)
                for i in range(market_orders_count):
                    if i % 2 == 0:  # Even indices = BUY
                        market_side = 'BUY'
                        aggressive_price = testnet_price * 1.01  # Slightly above testnet price
                    else:  # Odd indices = SELL
                        market_side = 'SELL'
                        aggressive_price = testnet_price * 0.99  # Slightly below testnet price
                    
                    orders_list.append({
                        'side': market_side,
                        'price': aggressive_price,
                        'quantity': random.choice([0.1, 0.2, 0.3, 0.4, 0.5]),  # Smaller quantities for normal trading
                        'is_inter_wallet': True,
                        'order_type': 'MARKET'
                    })
            
            # Place batch orders
            success = await self.place_batch_orders(market_id, orders_list, market_symbol)
            
            if success:
                # Count orders by side for logging
                buy_orders = sum(1 for order in orders_list if order['side'] == 'BUY')
                sell_orders = sum(1 for order in orders_list if order['side'] == 'SELL')
                mode_text = "AGGRESSIVE" if use_aggressive_mode else "NORMAL"
                log(f"✅ {mode_text} orderbook created: {len(orders_list)} orders placed ({buy_orders} BUY, {sell_orders} SELL) - Direction: {correction_direction}", 
                    self.wallet_id, market_id)
                self.trading_stats['successful_trades'] += len(orders_list)
                
                # Process inter-wallet trading after placing orders (only if enabled)
                if enable_inter_wallet_trading:
                    await self.process_inter_wallet_trading(market_id, orders_list)
            else:
                log(f"❌ Failed to create enhanced orderbook", self.wallet_id, market_id)
                self.trading_stats['failed_trades'] += len(orders_list)
            
        except Exception as e:
            log(f"❌ Error creating enhanced orderbook: {e}", self.wallet_id, market_id)
    
    async def refresh_orders_if_needed(self, market_id: str, current_mainnet_price: float, market_symbol: str):
        """
        Refresh orders if mainnet price has changed by more than 2%
        """
        try:
            market_state = self.market_states.get(market_id)
            if not market_state:
                return
            
            # Calculate price change percentage
            if market_state.last_mainnet_price > 0:
                price_change = abs(current_mainnet_price - market_state.last_mainnet_price)
                price_change_percent = (price_change / market_state.last_mainnet_price) * 100
                
                # Check if we need to refresh orders (2% threshold)
                if price_change_percent >= 2.0:
                    log(f"🔄 Price changed by {price_change_percent:.2f}% - refreshing orders", 
                        self.wallet_id, market_id)
                    
                    # Cancel existing orders
                    await self.cancel_all_orders(market_id)
                    
                    # Wait a moment for cancellations to process
                    await asyncio.sleep(3)
                    
                    # Get current testnet price
                    testnet_price = await self.get_market_price(market_id, market_symbol)
                    
                    if testnet_price > 0:
                        # Create new orders at updated prices
                        await self.create_enhanced_orderbook(market_id, testnet_price, current_mainnet_price, market_symbol, True, True)
                        
                        # Update market state
                        market_state.last_mainnet_price = current_mainnet_price
                        market_state.last_testnet_price = testnet_price
                        market_state.last_refresh_time = datetime.now()
                        market_state.price_change_percent = price_change_percent
                        
                        self.trading_stats['orders_refreshed'] += 1
                        
                        log(f"✅ Orders refreshed successfully", self.wallet_id, market_id)
            
            # Update last mainnet price
            market_state.last_mainnet_price = current_mainnet_price
            
        except Exception as e:
            log(f"❌ Error refreshing orders: {e}", self.wallet_id, market_id)
    
    async def cancel_all_orders(self, market_id: str):
        """Cancel all active orders for a market"""
        try:
            market_state = self.market_states.get(market_id)
            if not market_state or not market_state.active_orders:
                return
            
            log(f"🗑️ Cancelling {len(market_state.active_orders)} orders", self.wallet_id, market_id)
            
            # Create order data for cancellation
            spot_orders_to_cancel = []
            derivative_orders_to_cancel = []
            
            market_config = self.get_market_config(market_id)
            if not market_config:
                return
            
            subaccount_id = self.address.get_subaccount_id(0)
            
            for order_hash, order_info in market_state.active_orders.items():
                order_data = self.composer.order_data_without_mask(
                    market_id=market_id,
                    subaccount_id=subaccount_id,
                    order_hash=order_hash
                )
                
                if market_config.get('type') == 'spot':
                    spot_orders_to_cancel.append(order_data)
                else:
                    derivative_orders_to_cancel.append(order_data)
            
            # Create batch cancel message
            msg = self.composer.msg_batch_update_orders(
                sender=self.address.to_acc_bech32(),
                derivative_orders_to_create=[],
                spot_orders_to_create=[],
                derivative_orders_to_cancel=derivative_orders_to_cancel,
                spot_orders_to_cancel=spot_orders_to_cancel
            )
            
            # Broadcast cancellation
            response = await self.broadcaster.broadcast([msg])
            
            tx_hash = (response.get('txhash') or 
                      response.get('txResponse', {}).get('txhash') or
                      'unknown')
            
            if tx_hash and tx_hash != 'unknown':
                log(f"✅ Orders cancelled successfully! TX: {tx_hash}", self.wallet_id, market_id)
                
                # Clear tracking
                for order_hash in market_state.active_orders.keys():
                    if order_hash in self.order_tracking:
                        del self.order_tracking[order_hash]
                
                market_state.active_orders.clear()
                self.inter_wallet_orders = [
                    order for order in self.inter_wallet_orders 
                    if order.market_id != market_id
                ]
            else:
                log(f"❌ Failed to cancel orders", self.wallet_id, market_id)
                
        except Exception as e:
            log(f"❌ Error cancelling orders: {e}", self.wallet_id, market_id)
    
    async def execute_inter_wallet_trades(self, other_traders: List['EnhancedWalletTrader']):
        """
        Execute random trades between wallets to create realistic market activity
        """
        try:
            if not self.inter_wallet_orders or not other_traders:
                return
            
            # Randomly select orders to match
            orders_to_match = random.sample(
                self.inter_wallet_orders, 
                min(3, len(self.inter_wallet_orders))  # Match up to 3 orders
            )
            
            for order_info in orders_to_match:
                # Find a matching wallet
                matching_trader = random.choice(other_traders)
                
                # Create a matching order on the other wallet
                matching_side = "SELL" if order_info.side == "BUY" else "BUY"
                matching_price = order_info.price * (1.001 if matching_side == "SELL" else 0.999)
                matching_quantity = order_info.quantity * random.uniform(0.8, 1.2)  # Random size variation
                
                # Place matching order on other wallet
                matching_orders = [{
                    'side': matching_side,
                    'price': matching_price,
                    'quantity': matching_quantity,
                    'is_inter_wallet': True
                }]
                
                success = await matching_trader.place_batch_orders(
                    order_info.market_id, 
                    matching_orders, 
                    self.market_states[order_info.market_id].market_symbol
                )
                
                if success:
                    log(f"🤝 Inter-wallet trade executed: {matching_side} {matching_quantity} @ {matching_price}", 
                        self.wallet_id, order_info.market_id)
                    self.trading_stats['inter_wallet_trades'] += 1
                
                # Remove from inter-wallet orders list
                self.inter_wallet_orders.remove(order_info)
                
        except Exception as e:
            log(f"❌ Error executing inter-wallet trades: {e}", self.wallet_id)
    
    async def enter_cooldown(self, duration: int = 10):
        """Enter cooldown mode"""
        self.in_cooldown = True
        self.cooldown_until = time.time() + duration
        log(f"🛑 {self.wallet_id} entering {duration}s cooldown", self.wallet_id)
    
    async def check_cooldown(self) -> bool:
        """Check if wallet is in cooldown"""
        if self.in_cooldown:
            if time.time() >= self.cooldown_until:
                self.in_cooldown = False
                log(f"✅ {self.wallet_id} cooldown finished", self.wallet_id)
                return False
            else:
                remaining = int(self.cooldown_until - time.time())
                log(f"⏳ {self.wallet_id} in cooldown: {remaining}s remaining", self.wallet_id)
                return True
        return False
    
    async def trading_loop(self, testnet_market_id: str, market_symbol: str, mainnet_market_id: str = None, other_traders: List['EnhancedWalletTrader'] = None):
        """Enhanced trading loop with dynamic order management"""
        self.is_running = True
        log(f"🚀 Starting enhanced trading loop for {market_symbol}", self.wallet_id, testnet_market_id)
        
        while self.is_running:
            try:
                # Get current prices
                testnet_price = await self.get_market_price(testnet_market_id, market_symbol)
                mainnet_price = await self.get_mainnet_price(market_symbol, mainnet_market_id)
                
                if testnet_price > 0 and mainnet_price > 0:
                    # Check if we need to refresh orders
                    await self.refresh_orders_if_needed(testnet_market_id, mainnet_price, market_symbol)
                    
                    # Calculate price difference
                    price_diff = abs(testnet_price - mainnet_price)
                    price_diff_percent = (price_diff / mainnet_price) * 100
                    
                    # Log current situation
                    if 'stinj' in market_symbol.lower():
                        log(f"💰 {market_symbol} | Mainnet: {mainnet_price:.4f} INJ | Testnet: {testnet_price:.4f} INJ | Diff: {price_diff_percent:.2f}%", 
                            self.wallet_id, testnet_market_id)
                    else:
                        log(f"💰 {market_symbol} | Mainnet: ${mainnet_price:.4f} | Testnet: ${testnet_price:.4f} | Diff: {price_diff_percent:.2f}%", 
                            self.wallet_id, testnet_market_id)
                    
                    # Place orders if price difference is significant
                    if price_diff_percent > 2.0:  # 2.0% threshold for aggressive correction
                        # Use aggressive mode and disable inter-wallet trading
                        await self.create_enhanced_orderbook(testnet_market_id, testnet_price, mainnet_price, market_symbol, False, True)
                        log(f"🚫 Inter-wallet trading disabled (price diff: {price_diff_percent:.2f}% > 2%)", 
                            self.wallet_id, testnet_market_id)
                    else:
                        # When price difference is small (≤2%), use normal mode with inter-wallet trading
                        await self.create_enhanced_orderbook(testnet_market_id, testnet_price, mainnet_price, market_symbol, True, False)
                        if other_traders:
                            await self.execute_inter_wallet_trades(other_traders)
                
                # Wait before next iteration with random delay to prevent sequence conflicts
                # Use LONGER delays to allow orders to actually execute before replacing them
                if price_diff_percent > 2.0:  # If price difference is large, still give time for execution
                    base_delay = 15  # Longer delay to allow order execution
                    random_delay = random.uniform(5, 10)  # 5-10 seconds random delay
                else:
                    base_delay = 20  # Even longer delay for normal mode
                    random_delay = random.uniform(5, 15)  # 5-15 seconds random delay
                
                total_delay = base_delay + random_delay
                log(f"⏰ Waiting {total_delay:.1f}s before next iteration to allow order execution", self.wallet_id, testnet_market_id)
                await asyncio.sleep(total_delay)
                
            except Exception as e:
                log(f"❌ Error in trading loop: {e}", self.wallet_id, testnet_market_id)
                if self.is_running:
                    await asyncio.sleep(10)
    
    def stop(self):
        """Stop the enhanced trader"""
        self.is_running = False
        if self.chainstreamer_task:
            self.chainstreamer_task.cancel()
        log(f"🛑 Enhanced trader stopped", self.wallet_id)
    
    def get_trading_summary(self) -> str:
        """Get enhanced trading summary"""
        summary = f"\n{'='*80}\n"
        summary += f"📊 ENHANCED TRADING SUMMARY - {self.wallet_id.upper()}\n"
        summary += f"{'='*80}\n"
        summary += f"🎯 Total Trades: {self.trading_stats['total_trades']}\n"
        summary += f"✅ Successful: {self.trading_stats['successful_trades']}\n"
        summary += f"❌ Failed: {self.trading_stats['failed_trades']}\n"
        summary += f"🤝 Inter-Wallet Trades: {self.trading_stats['inter_wallet_trades']}\n"
        summary += f"🔄 Orders Refreshed: {self.trading_stats['orders_refreshed']}\n"
        summary += f"📈 Success Rate: {(self.trading_stats['successful_trades']/max(1, self.trading_stats['total_trades'])*100):.1f}%\n"
        summary += f"{'='*80}\n"
        return summary

# Main function
async def main():
    """Main function for enhanced multi-wallet trader"""
    log("🚀 Starting Enhanced Multi-Wallet Parallel Trader")
    
    # Get enabled wallets
    enabled_wallets = []
    for wallet_config in wallets_config['wallets']:
        if wallet_config.get('enabled', False):
            enabled_wallets.append({
                'id': wallet_config['id'],
                'private_key': wallet_config['private_key']
            })
    
    if not enabled_wallets:
        log("❌ No enabled wallets found!")
        return
    
    log(f"📋 Found {len(enabled_wallets)} enabled wallets")
    
    # Get enabled markets
    enabled_markets = []
    for market_symbol, market_config in markets_config['markets'].items():
        if market_config.get('enabled', False) and market_config.get('type') == 'spot':
            enabled_markets.append({
                'symbol': market_symbol,
                'testnet_market_id': market_config.get('testnet_market_id', market_config.get('market_id')),
                'mainnet_market_id': market_config.get('mainnet_market_id'),
                'market_config': market_config
            })
    
    if not enabled_markets:
        log("❌ No enabled spot markets found!")
        return
    
    log(f"📊 Found {len(enabled_markets)} enabled spot markets")
    
    # Create and initialize enhanced traders
    traders = []
    for wallet_data in enabled_wallets:
        trader = EnhancedWalletTrader(wallet_data['id'], wallet_data['private_key'], markets_config['markets'])
        await trader.initialize()
        traders.append(trader)
    
    # Set up cross-references for inter-wallet trading
    for trader in traders:
        trader.other_traders = {t.wallet_id: t for t in traders if t != trader}
    
    # Start trading loops with staggered delays to prevent sequence conflicts
    tasks = []
    for i, trader in enumerate(traders):
        for j, market in enumerate(enabled_markets):
            # Pass other traders for inter-wallet trading
            other_traders = [t for t in traders if t != trader]
            
            # Add staggered delay to prevent all wallets from trading simultaneously
            delay = (i * len(enabled_markets) + j) * 2  # 2 seconds between each wallet/market combo
            
            async def delayed_start(trader, market_id, symbol, mainnet_id, other_traders, delay):
                if delay > 0:
                    await asyncio.sleep(delay)
                await trader.trading_loop(market_id, symbol, mainnet_id, other_traders)
            
            task = asyncio.create_task(delayed_start(
                trader,
                market['testnet_market_id'],
                market['symbol'],
                market['mainnet_market_id'],
                other_traders,
                delay
            ))
            tasks.append(task)
    
    # Set up signal handling
    shutdown_requested = False
    
    def signal_handler(signum, frame):
        nonlocal shutdown_requested
        if not shutdown_requested:
            shutdown_requested = True
            log("🛑 Received shutdown signal, stopping all enhanced traders...")
            for trader in traders:
                trader.stop()
            
            for task in tasks:
                if not task.done():
                    task.cancel()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    log(f"🎯 Started {len(tasks)} enhanced trading tasks ({len(traders)} wallets × {len(enabled_markets)} markets)")
    
    # Wait for tasks to complete
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except KeyboardInterrupt:
        log("🛑 Keyboard interrupt received")
    except asyncio.CancelledError:
        log("🛑 Tasks cancelled during shutdown")
    except Exception as e:
        log(f"❌ Error in main loop: {e}")
    finally:
        # Stop all traders
        log("🛑 Stopping all enhanced traders...")
        for trader in traders:
            trader.stop()
        
        # Cancel remaining tasks
        for task in tasks:
            if not task.done():
                task.cancel()
        
        # Wait for cleanup
        try:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5.0)
        except asyncio.TimeoutError:
            log("⚠️ Some tasks took too long to cancel")
        except Exception:
            pass
        
        log("✅ All enhanced traders stopped")
        
        # Show final summary
        log("\n" + "="*80)
        log("📊 FINAL ENHANCED TRADING SUMMARY")
        log("="*80)
        
        total_trades = 0
        total_successful = 0
        total_failed = 0
        total_inter_wallet = 0
        total_refreshed = 0
        
        for trader in traders:
            summary = trader.get_trading_summary()
            log(summary)
            
            total_trades += trader.trading_stats['total_trades']
            total_successful += trader.trading_stats['successful_trades']
            total_failed += trader.trading_stats['failed_trades']
            total_inter_wallet += trader.trading_stats['inter_wallet_trades']
            total_refreshed += trader.trading_stats['orders_refreshed']
        
        # Overall summary
        log(f"\n{'='*80}")
        log(f"🎯 OVERALL ENHANCED SUMMARY")
        log(f"{'='*80}")
        log(f"💰 Wallets: {len(traders)}")
        log(f"🎯 Total Trades: {total_trades}")
        log(f"✅ Successful: {total_successful}")
        log(f"❌ Failed: {total_failed}")
        log(f"🤝 Inter-Wallet Trades: {total_inter_wallet}")
        log(f"🔄 Orders Refreshed: {total_refreshed}")
        if total_trades > 0:
            log(f"📈 Overall Success Rate: {(total_successful/total_trades*100):.1f}%")
        log(f"{'='*80}")

if __name__ == "__main__":
    asyncio.run(main())
