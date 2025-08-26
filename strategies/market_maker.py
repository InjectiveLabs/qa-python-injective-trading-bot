"""
Market making strategy for the Injective Market Making Bot.
"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from decimal import Decimal

from strategies.base_strategy import BaseStrategy
from models.order import OrderRequest, OrderSide, OrderType
from models.market import MarketConfig
from core.markets import market_manager
from core.wallet_manager import wallet_manager
from core.client import injective_client
from utils.logger import get_logger
from utils.helpers import calculate_order_prices, calculate_price_deviation
from models.order import OrderResponse

logger = get_logger(__name__)


class MarketMakerStrategy(BaseStrategy):
    """Market making strategy implementation."""
    
    def __init__(self, wallet_id: str = None):
        """Initialize market maker strategy."""
        super().__init__("MarketMaker")
        self.wallet_id = wallet_id  # Specific wallet for this strategy instance
        self.market_orders: Dict[str, Dict[str, List[str]]] = {}  # market_id -> {side -> [order_ids]}
        self.last_rebalance = datetime.utcnow()
        
        # Price correction settings
        self.price_correction_enabled = True
        self.correction_threshold = 0.05  # 5% deviation threshold
        self.correction_cooldown = 300  # 5 minutes
        self.last_correction_time = datetime.utcnow()
        self.max_correction_orders = 3
        
        # Emergency order settings
        self.emergency_threshold = 0.20  # 20% deviation threshold
        self.emergency_order_size = 50  # Larger order size for emergency
        self.emergency_cooldown = 600  # 10 minutes
        self.last_emergency_time = datetime.utcnow()
        
        # Sequential execution settings to avoid sequence conflicts
        self.execution_delay = 5.0  # 5 seconds between orders
        self.last_order_time = datetime.utcnow()
        
        # Wallet-specific client
        self.wallet_client = None
        
    async def _create_wallet_client(self):
        """Create a separate complete Injective client setup for this wallet."""
        try:
            from pyinjective.async_client_v2 import AsyncClient
            from pyinjective.indexer_client import IndexerClient
            from pyinjective.core.network import Network
            from pyinjective.core.broadcaster import MsgBroadcasterWithPk
            from pyinjective import PrivateKey, Address
            
            if not self.wallet_id:
                logger.warning("No wallet_id provided, using main client")
                self.wallet_client = injective_client
                return
                
            # Get wallet private key
            if self.wallet_id not in wallet_manager.wallets:
                logger.error(f"Wallet {self.wallet_id} not found in wallet manager")
                self.wallet_client = injective_client
                return
                
            wallet_config = wallet_manager.wallets[self.wallet_id]
            
            # Create network configuration
            network = Network.testnet()
            
            # Create separate AsyncClient for this wallet
            async_client = AsyncClient(network)
            composer = await async_client.composer()
            
            # Create separate IndexerClient for this wallet
            indexer_client = IndexerClient(network)
            
            # Initialize wallet
            private_key = PrivateKey.from_hex(wallet_config.private_key)
            address = private_key.to_public_key().to_address()
            
            # Fetch account info for this wallet (this sets sequence and account number)
            await async_client.fetch_account(address.to_acc_bech32())
            
            # Initialize broadcaster for this wallet
            gas_price = await async_client.current_chain_gas_price()
            gas_price = int(gas_price * 1.1)  # Add 10% buffer
            
            broadcaster = MsgBroadcasterWithPk.new_using_gas_heuristics(
                network=network,
                private_key=wallet_config.private_key,
                gas_price=gas_price,
                client=async_client,
                composer=composer,
            )
            
            # Create wallet-specific client object
            self.wallet_client = {
                'network': network,
                'async_client': async_client,
                'indexer_client': indexer_client,
                'composer': composer,
                'broadcaster': broadcaster,
                'private_key': private_key,
                'address': address
            }
            
            logger.info(f"✅ Created separate client for {self.wallet_id}: {address.to_acc_bech32()}")
            logger.info(f"   Sequence: {async_client.get_sequence()}")
            logger.info(f"   Account Number: {async_client.get_number()}")
            
        except Exception as e:
            logger.error(f"❌ Failed to create wallet client for {self.wallet_id}: {e}")
            # Fall back to main client
            self.wallet_client = injective_client
        
    async def initialize(self, markets: List[str]) -> bool:
        """
        Initialize market maker strategy for specific markets.
        
        Args:
            markets: List of market IDs to trade
            
        Returns:
            True if initialization successful
        """
        try:
            logger.info("Initializing market maker strategy", markets=markets)
            
            # Create wallet-specific client first
            await self._create_wallet_client()
            
            self.markets = markets
            
            # Initialize market orders tracking
            for market_id in markets:
                self.market_orders[market_id] = {"buy": [], "sell": []}
            
            # Cancel any existing orders for these markets
            await self.cancel_all_orders()
            
            logger.info("Market maker strategy initialized successfully")
            return True
            
        except Exception as e:
            logger.error("Failed to initialize market maker strategy", error=str(e))
            return False
    
    async def execute(self) -> bool:
        """
        Execute market making logic.
        
        Returns:
            True if execution successful
        """
        try:
            if not self.is_running:
                return False
            
            logger.info("🔄 Executing market maker strategy...")
            
            # Update market prices
            logger.info("📊 Updating market prices...")
            try:
                await self._update_market_prices()
                logger.info("✅ Market prices updated successfully")
            except Exception as e:
                logger.error(f"❌ Failed to update market prices: {e}")
                return False
            
            # Check for price deviations and apply corrections
            logger.info("🔍 Checking price deviations...")
            try:
                await self._check_price_deviations()
                logger.info("✅ Price deviations checked successfully")
            except Exception as e:
                logger.error(f"❌ Failed to check price deviations: {e}")
                return False
            
            # Check and correct prices if needed (new price correction logic)
            if self.price_correction_enabled:
                logger.info("🎯 Running price correction logic...")
                try:
                    await self._check_and_correct_prices()
                    logger.info("✅ Price correction logic completed")
                except Exception as e:
                    logger.error(f"❌ Failed to run price correction: {e}")
                    return False
            else:
                logger.info("⏸️  Price correction disabled")
            
            # Rebalance orders if needed
            logger.info("⚖️  Checking order rebalancing...")
            try:
                await self._rebalance_orders()
                logger.info("✅ Order rebalancing checked successfully")
            except Exception as e:
                logger.error(f"❌ Failed to check order rebalancing: {e}")
                return False
            
            # Place market orders if we don't have any and prices are misaligned
            logger.info("📝 Checking if we need to place market orders...")
            for market_id in self.markets:
                current_orders = self.market_orders.get(market_id, {"buy": [], "sell": []})
                total_orders = len(current_orders["buy"]) + len(current_orders["sell"])
                logger.info(f"   {market_id}: {total_orders} current orders")
                
                if total_orders == 0:
                    logger.info(f"   📝 No orders for {market_id}, placing market orders...")
                    logger.info(f"   🚀 Calling _place_market_orders for {market_id}")
                    await self._place_market_orders(market_id)
                    logger.info(f"   ✅ Finished _place_market_orders for {market_id}")
                else:
                    logger.info(f"   ✅ {market_id} already has {total_orders} orders")
                    
                    # Check for price corrections if we have orders
                    await self._check_and_correct_prices()
            
            self.last_update = datetime.utcnow()
            logger.info("✅ Market maker execution completed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to execute market maker strategy: {e}")
            return False
    
    async def start(self) -> bool:
        """
        Start the market maker strategy.
        
        Returns:
            True if start successful
        """
        try:
            logger.info("🚀 Starting market maker strategy...")
            
            self.is_running = True
            
            # Place initial orders for all markets
            logger.info(f"📝 Placing initial orders for markets: {self.markets}")
            for market_id in self.markets:
                logger.info(f"🎯 Placing initial orders for {market_id}...")
                await self._place_market_orders(market_id)
            
            logger.info("✅ Market maker strategy started successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start market maker strategy: {e}")
            self.is_running = False
            return False
    
    async def stop(self) -> None:
        """Stop the market maker strategy."""
        try:
            logger.info("Stopping market maker strategy")
            
            self.is_running = False
            
            # Note: Orders are NOT automatically cancelled on shutdown
            # Use cancel_all_orders() manually if needed
            logger.info("Market maker strategy stopped (orders remain active)")
            
        except Exception as e:
            logger.error("Error stopping market maker strategy", error=str(e))
    
    async def _update_market_prices(self) -> None:
        """Update market and oracle prices for all markets."""
        try:
            # Update all market data at once
            await market_manager.update_market_data()
            logger.debug("Market prices updated")
        except Exception as e:
            logger.error(f"Failed to update market prices: {e}")
    
    async def _check_price_deviations(self) -> None:
        """Check for price deviations and apply corrections."""
        for market_id in self.markets:
            market_data = await market_manager.get_market_data(market_id)
            market_config = await market_manager.get_market_config(market_id)
            
            if not market_data or not market_config:
                continue
            
            # Check if price correction is enabled
            if not market_config.price_correction.enabled:
                continue
            
            # Calculate price deviation
            if market_data.current_price and market_data.oracle_price:
                deviation = calculate_price_deviation(
                    market_data.current_price,
                    market_data.oracle_price
                )
                
                threshold = market_config.price_correction.deviation_threshold
                
                if abs(deviation) > threshold:
                    logger.info("Price deviation detected", 
                              market_id=market_id,
                              deviation=deviation,
                              threshold=threshold)
                    
                    # Use the current and oracle prices for correction
                    if market_data.current_price and market_data.oracle_price:
                        await self._place_price_correction_orders(market_id, market_data.oracle_price, market_data.current_price)
    
    async def _check_and_correct_prices(self) -> None:
        """Check price differences and place correction orders if needed."""
        try:
            logger.info(f"🔍 Checking prices for markets: {self.markets}")
            
            for market_id in self.markets:
                logger.info(f"📊 Analyzing {market_id}...")
                
                # Get real market price from external source
                from core.price_feed import price_feed
                real_market_price = await price_feed.get_reference_price("INJ", "USDT")
                if not real_market_price:
                    logger.warning(f"❌ Could not get real market price for {market_id}")
                    continue
                
                # Get testnet orderbook price
                testnet_price = await market_manager.get_market_price(market_id)
                if not testnet_price:
                    logger.warning(f"❌ Could not get testnet orderbook price for {market_id}")
                    continue
                
                # Calculate price difference
                price_diff = abs(float(testnet_price) - float(real_market_price))
                price_diff_percent = (price_diff / float(real_market_price)) * 100
                
                logger.info(f"📊 Price Analysis - {market_id}:", 
                           mainnet_price=f"${float(real_market_price):.4f}",
                           testnet_price=f"${float(testnet_price):.4f}",
                           difference=f"${price_diff:.4f}",
                           difference_percent=f"{price_diff_percent:.2f}%")
                
                # Check if correction is needed
                if price_diff_percent > self.correction_threshold:
                    logger.info(f"🚨 Price correction needed! Difference: {price_diff_percent:.2f}%")
                    
                    # Check for emergency situation (>20% deviation)
                    if price_diff_percent > self.emergency_threshold:
                        logger.warning(f"🚨🚨 EMERGENCY: Extreme price deviation detected! {price_diff_percent:.2f}%")
                        logger.warning(f"🚨🚨 Placing emergency market orders to correct price!")
                        await self._place_emergency_market_orders(market_id, real_market_price, testnet_price)
                    else:
                        # Check cooldown for normal correction
                        current_time = asyncio.get_event_loop().time()
                        if current_time - self.last_correction_time > self.correction_cooldown:
                            logger.info(f"🎯 Placing price correction orders...")
                            await self._place_price_correction_orders(market_id, real_market_price, testnet_price)
                            self.last_correction_time = current_time
                        else:
                            remaining_cooldown = self.correction_cooldown - (current_time - self.last_correction_time)
                            logger.info(f"⏰ Correction on cooldown, {remaining_cooldown:.0f}s remaining")
                else:
                    logger.info(f"✅ Prices within acceptable range ({price_diff_percent:.2f}% < {self.correction_threshold}%)")
                    
        except Exception as e:
            logger.error(f"Error checking prices: {e}")
    
    async def _place_price_correction_orders(self, market_id: str, real_price: float, testnet_price: float) -> None:
        """Place orders to correct the price difference."""
        try:
            market_config = await market_manager.get_market_config(market_id)
            if not market_config:
                logger.error("No market config found")
                return
            
            logger.info("Placing price correction orders", market_id=market_id)
            
            # Determine correction strategy
            if testnet_price > real_price:
                # Testnet price is too high - place aggressive sell orders
                logger.info("Testnet price too HIGH - placing SELL orders")
                await self._place_aggressive_sell_orders(market_id, real_price, market_config)
            else:
                # Testnet price is too low - place aggressive buy orders
                logger.info("Testnet price too LOW - placing BUY orders")
                await self._place_aggressive_buy_orders(market_id, real_price, market_config)
                
        except Exception as e:
            logger.error(f"Error placing correction orders: {e}")
    
    async def _place_aggressive_sell_orders(self, market_id: str, target_price: float, market_config) -> None:
        """Place aggressive sell orders to bring price down using parallel execution."""
        try:
            target_price_float = float(target_price)
            
            # Calculate sell prices slightly above target
            sell_prices_raw = [
                target_price_float * 1.02,  # 2% above target
                target_price_float * 1.01,  # 1% above target
                target_price_float * 1.005  # 0.5% above target
            ]
            
            # Round to tick size (0.001)
            tick_size = 0.001
            sell_prices = [round(price / tick_size) * tick_size for price in sell_prices_raw]
            
            logger.info(f"🚀 Creating aggressive SELL orders at ${sell_prices[0]:.4f}, ${sell_prices[1]:.4f}, ${sell_prices[2]:.4f}")
            
            # Place orders in parallel for each price level
            for i, price in enumerate(sell_prices[:self.max_correction_orders]):
                logger.info(f"📉 Placing parallel aggressive SELL orders at ${price:.4f}")
                
                # Place multiple orders in parallel for this price level
                orders = await self._place_parallel_orders(
                    market_id=market_id,
                    side="SELL",
                    price=price,
                    quantity=market_config.order_size,
                    order_type="LIMIT"
                )
                
                if orders:
                    logger.info(f"✅ Placed {len(orders)} aggressive SELL orders at ${price:.4f}")
                else:
                    logger.warning(f"❌ Failed to place aggressive SELL orders at ${price:.4f}")
                    break
                    
        except Exception as e:
            logger.error(f"Error placing aggressive sell orders: {e}")
    
    async def _place_aggressive_buy_orders(self, market_id: str, target_price: float, market_config) -> None:
        """Place aggressive buy orders to bring price up using parallel execution."""
        try:
            target_price_float = float(target_price)
            
            # Calculate buy prices slightly below target
            buy_prices_raw = [
                target_price_float * 0.98,  # 2% below target
                target_price_float * 0.99,  # 1% below target
                target_price_float * 0.995  # 0.5% below target
            ]
            
            # Round to tick size (0.001)
            tick_size = 0.001
            buy_prices = [round(price / tick_size) * tick_size for price in buy_prices_raw]
            
            logger.info(f"🚀 Creating aggressive BUY orders at ${buy_prices[0]:.4f}, ${buy_prices[1]:.4f}, ${buy_prices[2]:.4f}")
            
            # Place orders in parallel for each price level
            for i, price in enumerate(buy_prices[:self.max_correction_orders]):
                logger.info(f"📈 Placing parallel aggressive BUY orders at ${price:.4f}")
                
                # Place multiple orders in parallel for this price level
                orders = await self._place_parallel_orders(
                    market_id=market_id,
                    side="BUY",
                    price=price,
                    quantity=market_config.order_size,
                    order_type="LIMIT"
                )
                
                if orders:
                    logger.info(f"✅ Placed {len(orders)} aggressive BUY orders at ${price:.4f}")
                else:
                    logger.warning(f"❌ Failed to place aggressive BUY orders at ${price:.4f}")
                    break
                    
        except Exception as e:
            logger.error(f"Error placing aggressive buy orders: {e}")
    
    async def _place_emergency_market_orders(self, market_id: str, real_price: float, testnet_price: float) -> None:
        """Place emergency market orders for extreme price deviations."""
        try:
            market_config = await market_manager.get_market_config(market_id)
            if not market_config:
                logger.error("No market config found for emergency orders")
                return
            
            # Check cooldown
            import time
            current_time = time.time()
            if current_time - self.last_emergency_time < self.emergency_cooldown:
                remaining_cooldown = self.emergency_cooldown - (current_time - self.last_emergency_time)
                logger.info(f"Emergency orders on cooldown, {remaining_cooldown:.0f}s remaining")
                return
            
            logger.warning(f"🚨🚨 EMERGENCY: Placing market orders for extreme price deviation!")
            
            # Determine emergency action
            if testnet_price > real_price:
                # Testnet price too high - place emergency SELL market order
                logger.warning(f"🚨🚨 EMERGENCY: Placing SELL market order to crash price")
                await self._place_emergency_sell_market_order(market_id, market_config)
            else:
                # Testnet price too low - place emergency BUY market order
                logger.warning(f"🚨🚨 EMERGENCY: Placing BUY market order to pump price")
                await self._place_emergency_buy_market_order(market_id, market_config)
            
            self.last_emergency_time = current_time
            
        except Exception as e:
            logger.error(f"Error placing emergency market orders: {e}")
    
    async def _place_emergency_sell_market_order(self, market_id: str, market_config) -> None:
        """Place emergency SELL market order using parallel execution."""
        try:
            logger.warning(f"🚨🚨 Placing emergency SELL market orders in parallel...")
            
            # Place emergency orders in parallel using all available wallets
            orders = await self._place_parallel_orders(
                market_id=market_id,
                side="SELL",
                price=0.0,  # Market orders don't need price
                quantity=self.emergency_order_size,
                order_type="MARKET"
            )
            
            if orders:
                logger.warning(f"🚨🚨 EMERGENCY SELL market orders placed: {len(orders)} orders of {self.emergency_order_size} INJ each")
            else:
                logger.error(f"🚨🚨 EMERGENCY SELL market orders failed")
                
        except Exception as e:
            logger.error(f"Error placing emergency SELL market order: {e}")
    
    async def _place_emergency_buy_market_order(self, market_id: str, market_config) -> None:
        """Place emergency BUY market order using parallel execution."""
        try:
            logger.warning(f"🚨🚨 Placing emergency BUY market orders in parallel...")
            
            # Place emergency orders in parallel using all available wallets
            orders = await self._place_parallel_orders(
                market_id=market_id,
                side="BUY",
                price=0.0,  # Market orders don't need price
                quantity=self.emergency_order_size,
                order_type="MARKET"
            )
            
            if orders:
                logger.warning(f"🚨🚨 EMERGENCY BUY market orders placed: {len(orders)} orders of {self.emergency_order_size} INJ each")
            else:
                logger.error(f"🚨🚨 EMERGENCY BUY market orders failed")
                
        except Exception as e:
            logger.error(f"Error placing emergency BUY market order: {e}")
    
    async def _place_market_orders(self, market_id: str) -> None:
        """
        Place market making orders for a market using parallel execution.
        
        Args:
            market_id: Market ID
        """
        try:
            logger.info(f"📝 Placing market orders for {market_id}...")
            logger.info(f"🔍 Starting _place_market_orders for {market_id}")
            
            market_config = await market_manager.get_market_config(market_id)
            
            if not market_config:
                logger.warning(f"❌ No market config found for {market_id}")
                return
            
            # Get orderbook price as base price (instead of oracle price)
            orderbook_price = await market_manager.get_market_price(market_id)
            if not orderbook_price:
                logger.warning(f"❌ No orderbook price available for {market_id}")
                return
            
            logger.info(f"📊 {market_id} orderbook price: ${float(orderbook_price):.4f}")
            
            # Calculate order prices based on orderbook mid price
            bid_price, ask_price = calculate_order_prices(
                orderbook_price,
                market_config.spread_percent,
                "balanced"
            )
            
            # Place orders in parallel using multiple wallets
            logger.info(f"🚀 Placing parallel BUY orders: {market_config.order_size} INJ at ${bid_price:.4f}")
            buy_orders = await self._place_parallel_orders(
                market_id=market_id,
                side="BUY",
                price=bid_price,
                quantity=market_config.order_size,
                order_type="LIMIT"
            )
            
            logger.info(f"🚀 Placing parallel SELL orders: {market_config.order_size} INJ at ${ask_price:.4f}")
            sell_orders = await self._place_parallel_orders(
                market_id=market_id,
                side="SELL",
                price=ask_price,
                quantity=market_config.order_size,
                order_type="LIMIT"
            )
            
            total_orders = len(buy_orders) + len(sell_orders)
            logger.info(f"✅ Market orders placed for {market_id}: {total_orders} orders", 
                        orderbook_price=f"${float(orderbook_price):.4f}",
                        bid_price=f"${bid_price:.4f}",
                        ask_price=f"${ask_price:.4f}")
            
        except Exception as e:
            logger.error("Failed to place market orders", 
                        market_id=market_id, error=str(e))
    
    async def _place_buy_order(self, market_id: str, price: float, market_config: MarketConfig) -> None:
        """
        Place a buy order.
        
        Args:
            market_id: Market ID
            price: Order price
            market_config: Market configuration
        """
        try:
            order_request = OrderRequest(
                market_id=market_id,
                wallet_id="",  # Will be determined by wallet manager
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                price=price,
                quantity=market_config.order_size
            )
            
            response = await self.place_order(order_request)
            
            if response.success and response.order_id:
                self.market_orders[market_id]["buy"].append(response.order_id)
                logger.info(f"✅ BUY order placed successfully: {market_config.order_size} INJ at ${price:.4f}", 
                           market_id=market_id,
                           order_id=response.order_id)
            else:
                logger.warning(f"❌ Failed to place BUY order: {response.error_message}", 
                             market_id=market_id)
                
        except Exception as e:
            logger.error("Error placing buy order", 
                        market_id=market_id, error=str(e))
    
    async def _place_sell_order(self, market_id: str, price: float, market_config: MarketConfig) -> None:
        """
        Place a sell order.
        
        Args:
            market_id: Market ID
            price: Order price
            market_config: Market configuration
        """
        try:
            order_request = OrderRequest(
                market_id=market_id,
                wallet_id="",  # Will be determined by wallet manager
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT,
                price=price,
                quantity=market_config.order_size
            )
            
            response = await self.place_order(order_request)
            
            if response.success and response.order_id:
                self.market_orders[market_id]["sell"].append(response.order_id)
                logger.info(f"✅ SELL order placed successfully: {market_config.order_size} INJ at ${price:.4f}", 
                           market_id=market_id,
                           order_id=response.order_id)
            else:
                logger.warning(f"❌ Failed to place SELL order: {response.error_message}", 
                             market_id=market_id)
                
        except Exception as e:
            logger.error("Error placing sell order", 
                        market_id=market_id, error=str(e))
    
    async def _should_place_orders(self, market_id: str) -> bool:
        """Check if we should place orders based on price alignment with mainnet."""
        try:
            # Get mainnet price
            from core.price_feed import price_feed
            mainnet_price = await price_feed.get_reference_price("INJ", "USDT")
            if not mainnet_price:
                logger.warning(f"❌ Could not get mainnet price for {market_id}, placing orders anyway")
                return True
            
            # Get testnet price
            testnet_price = await market_manager.get_market_price(market_id)
            if not testnet_price:
                logger.warning(f"❌ Could not get testnet price for {market_id}, placing orders anyway")
                return True
            
            # Calculate price difference
            price_diff = abs(float(testnet_price) - float(mainnet_price))
            price_diff_percent = (price_diff / float(mainnet_price)) * 100
            
            logger.info(f"📊 Price check for {market_id}:", 
                       mainnet_price=f"${float(mainnet_price):.4f}",
                       testnet_price=f"${float(testnet_price):.4f}",
                       difference=f"{price_diff_percent:.2f}%")
            
            # If prices are within 2% of each other, don't place orders
            if price_diff_percent < 2.0:
                logger.info(f"✅ {market_id} prices are aligned (diff: {price_diff_percent:.2f}% < 2%), skipping orders")
                return False
            else:
                logger.info(f"📝 {market_id} prices are misaligned (diff: {price_diff_percent:.2f}% > 2%), placing orders")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error checking if should place orders for {market_id}: {e}")
            return True  # Place orders if we can't determine
    
    async def _rebalance_orders(self) -> None:
        """Rebalance orders if needed."""
        # Check if rebalancing is needed (e.g., based on time interval)
        # For now, just log that rebalancing would happen
        logger.debug("Checking for order rebalancing")
    
    async def cancel_all_orders(self) -> None:
        """Cancel all orders for all markets and wallets using batch cancel."""
        try:
            logger.info("🚨 Cancelling all market maker orders using batch cancel...")
            
            # Cancel orders tracked in base strategy
            await super().cancel_all_orders()
            
            # Use batch cancel for all wallets
            for wallet_id in wallet_manager.wallets.keys():
                if wallet_manager.wallets[wallet_id].enabled:
                    await self._batch_cancel_wallet_orders(wallet_id)
            
            # Clear market orders tracking
            for market_id in self.markets:
                self.market_orders[market_id] = {"buy": [], "sell": []}
            
            logger.info("✅ All market maker orders cancelled successfully using batch cancel")
            
        except Exception as e:
            logger.error(f"❌ Error cancelling all orders: {e}")
    
    async def _batch_cancel_wallet_orders(self, wallet_id: str) -> None:
        """Cancel all orders for a specific wallet using batch cancel."""
        try:
            # Get wallet data
            wallet_data = await wallet_manager.get_wallet_data(wallet_id)
            if not wallet_data:
                return
            
            logger.info(f"📝 Batch cancelling orders for wallet {wallet_id}...")
            
            # Collect all orders to cancel
            all_spot_orders_data = []
            all_derivative_orders_data = []
            
            # Process each market
            for market_id in self.markets:
                # Get market config
                market_config = await market_manager.get_market_config(market_id)
                if not market_config:
                    continue
                
                # Get orders from Injective
                subaccount_id = wallet_data.address + "0"
                
                if market_config.type.value == "spot":
                    orders = await injective_client.get_spot_orders(market_id, subaccount_id)
                else:
                    orders = await injective_client.get_derivative_orders(market_id, subaccount_id)
                
                if orders and 'orders' in orders and orders['orders']:
                    logger.info(f"   📊 Found {len(orders['orders'])} orders to cancel for {market_id}")
                    
                    for order in orders['orders']:
                        order_hash = order.get('orderHash')
                        if order_hash:
                            # Create OrderData for batch cancel
                            order_data = injective_client.composer.order_data_without_mask(
                                market_id=market_config.market_id,
                                subaccount_id=subaccount_id,
                                order_hash=order_hash
                            )
                            
                            if market_config.type.value == "spot":
                                all_spot_orders_data.append(order_data)
                            else:
                                all_derivative_orders_data.append(order_data)
            
            # Batch cancel spot orders
            if all_spot_orders_data:
                logger.info(f"   🚨 Batch cancelling {len(all_spot_orders_data)} spot orders...")
                try:
                    batch_cancel_msg = injective_client.composer.msg_batch_cancel_spot_orders(
                        sender=wallet_data.address,
                        orders_data=all_spot_orders_data
                    )
                    
                    response = await injective_client.message_broadcaster.broadcast([batch_cancel_msg])
                    
                    tx_hash = response.get('txhash') or response.get('txResponse', {}).get('txhash')
                    if tx_hash:
                        logger.info(f"   ✅ Successfully batch cancelled {len(all_spot_orders_data)} spot orders")
                        logger.info(f"   📝 Transaction hash: {tx_hash}")
                    else:
                        logger.warning(f"   ⚠️  Failed to batch cancel spot orders")
                        
                except Exception as e:
                    logger.error(f"   ❌ Error batch cancelling spot orders: {e}")
            
            # Batch cancel derivative orders
            if all_derivative_orders_data:
                logger.info(f"   🚨 Batch cancelling {len(all_derivative_orders_data)} derivative orders...")
                try:
                    batch_cancel_msg = injective_client.composer.msg_batch_cancel_derivative_orders(
                        sender=wallet_data.address,
                        orders_data=all_derivative_orders_data
                    )
                    
                    response = await injective_client.message_broadcaster.broadcast([batch_cancel_msg])
                    
                    tx_hash = response.get('txhash') or response.get('txResponse', {}).get('txhash')
                    if tx_hash:
                        logger.info(f"   ✅ Successfully batch cancelled {len(all_derivative_orders_data)} derivative orders")
                        logger.info(f"   📝 Transaction hash: {tx_hash}")
                    else:
                        logger.warning(f"   ⚠️  Failed to batch cancel derivative orders")
                        
                except Exception as e:
                    logger.error(f"   ❌ Error batch cancelling derivative orders: {e}")
            
        except Exception as e:
            logger.error(f"❌ Error batch cancelling orders for wallet {wallet_id}: {e}")
    
    async def _cancel_wallet_orders(self, wallet_id: str, market_id: str, market_config) -> None:
        """Cancel all orders for a specific wallet and market."""
        try:
            # Get wallet data
            wallet_data = await wallet_manager.get_wallet_data(wallet_id)
            if not wallet_data:
                return
            
            # Get orders from Injective
            subaccount_id = wallet_data.address + "0"
            if market_config.type.value == "spot":
                orders = await injective_client.get_spot_orders(market_id, subaccount_id)
            else:
                orders = await injective_client.get_derivative_orders(market_id, subaccount_id)
            
            if orders and 'orders' in orders:
                for order in orders['orders']:
                    order_id = order.get('orderId')
                    if order_id:
                        logger.info(f"   📝 Cancelling order {order_id} from {wallet_id}")
                        await self._cancel_single_order(wallet_id, market_id, order_id, market_config)
            
        except Exception as e:
            logger.error(f"❌ Error cancelling orders for wallet {wallet_id}: {e}")
    
    async def _cancel_single_order(self, wallet_id: str, market_id: str, order_id: str, market_config) -> None:
        """Cancel a single order."""
        try:
            # Get wallet data
            wallet_data = await wallet_manager.get_wallet_data(wallet_id)
            if not wallet_data:
                return
            
            subaccount_id = wallet_data.address + "0"
            
            # Use client's cancel methods
            if market_config.type.value == "spot":
                response = await injective_client.cancel_spot_order(
                    market_id=market_id,
                    subaccount_id=subaccount_id,
                    order_hash=order_id
                )
            else:
                response = await injective_client.cancel_derivative_order(
                    market_id=market_id,
                    subaccount_id=subaccount_id,
                    order_hash=order_id
                )
            
            if response.get('txhash'):
                logger.info(f"   ✅ Order {order_id} cancelled successfully")
            else:
                logger.warning(f"   ⚠️  Failed to cancel order {order_id}")
                
        except Exception as e:
            logger.error(f"   ❌ Error cancelling order {order_id}: {e}")
    
    async def _place_parallel_orders(self, market_id: str, side: str, price: float, quantity: float, order_type: str = "LIMIT") -> List[OrderResponse]:
        """
        Place orders in parallel using multiple wallets with detailed price tracking.
        
        Args:
            market_id: Market ID
            side: Order side (BUY/SELL)
            price: Order price
            quantity: Order quantity
            order_type: Order type (LIMIT/MARKET)
            
        Returns:
            List of order responses
        """
        try:
            # Get all enabled wallets first
            enabled_wallets = [wallet_id for wallet_id, config in wallet_manager.wallets.items() 
                             if config.enabled and wallet_manager.can_place_order(wallet_id, market_id)]
            
            if not enabled_wallets:
                logger.warning(f"⚠️ No enabled wallets available for {market_id}")
                return []
            
            # Log wallet information
            logger.info(f"👛 Using {len(enabled_wallets)} wallets: {enabled_wallets}")
            
            # Get current prices before placing orders
            logger.info(f"🔍 Fetching current prices for {market_id}...")
            
            # Get mainnet price
            mainnet_price = await self._get_mainnet_price(market_id)
            if mainnet_price:
                logger.info(f"📊 Mainnet Price: ${mainnet_price:.4f}")
            else:
                logger.warning(f"⚠️ Could not fetch mainnet price for {market_id}")
            
            # Get testnet price
            testnet_price = await self._get_testnet_price(market_id)
            if testnet_price:
                logger.info(f"📊 Testnet Price: ${testnet_price:.4f}")
            else:
                logger.warning(f"⚠️ Could not fetch testnet price for {market_id}")
            
            # Calculate price difference
            if mainnet_price and testnet_price:
                price_diff = abs(mainnet_price - testnet_price)
                price_diff_percent = (price_diff / mainnet_price) * 100
                logger.info(f"📈 Price Difference: ${price_diff:.4f} ({price_diff_percent:.2f}%)")
                
                if mainnet_price > testnet_price:
                    logger.info(f"📈 Testnet is ${price_diff:.4f} BELOW mainnet price")
                else:
                    logger.info(f"📉 Testnet is ${price_diff:.4f} ABOVE mainnet price")
            
            if not enabled_wallets:
                logger.warning(f"⚠️ No enabled wallets available for {market_id}")
                return []
            
            logger.info(f"🚀 Placing {side} orders in parallel using {len(enabled_wallets)} wallets...")
            
            # Create order requests for all wallets
            order_requests = []
            for wallet_id in enabled_wallets:
                order_request = OrderRequest(
                    market_id=market_id,
                    wallet_id=wallet_id,
                    side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
                    order_type=OrderType.LIMIT if order_type == "LIMIT" else OrderType.MARKET,
                    price=price,
                    quantity=quantity
                )
                order_requests.append(order_request)
            
            # Place orders in parallel
            tasks = []
            for order_request in order_requests:
                if order_type == "LIMIT":
                    task = self.place_order(order_request)
                else:
                    task = self.place_market_order(order_request)
                tasks.append(task)
            
            # Execute orders sequentially to avoid sequence mismatch
            results = []
            for i, task in enumerate(tasks):
                try:
                    result = await task
                    results.append(result)
                    # Add delay between orders to prevent sequence mismatch
                    if i < len(tasks) - 1:
                        await asyncio.sleep(3.0)  # 3 second delay
                except Exception as e:
                    results.append(e)
            
            # Process results
            successful_orders = []
            failed_orders = []
            
            for i, result in enumerate(results):
                wallet_id = enabled_wallets[i]
                if isinstance(result, Exception):
                    logger.error(f"❌ Failed to place order for wallet {wallet_id}: {result}")
                    failed_orders.append(result)
                elif result.success:
                    logger.info(f"✅ Order placed successfully for wallet {wallet_id}: {result.order_id}")
                    successful_orders.append(result)
                else:
                    logger.error(f"❌ Order failed for wallet {wallet_id}: {result.error_message}")
                    failed_orders.append(result)
            
            # Log summary
            logger.info(f"📊 Parallel Order Summary:")
            logger.info(f"   ✅ Successful: {len(successful_orders)}")
            logger.info(f"   ❌ Failed: {len(failed_orders)}")
            logger.info(f"   📈 Total: {len(enabled_wallets)}")
            
            # Wait a moment for orders to be processed
            await asyncio.sleep(2)
            
            # Get updated testnet price after orders
            updated_testnet_price = await self._get_testnet_price(market_id)
            if updated_testnet_price and testnet_price:
                price_movement = updated_testnet_price - testnet_price
                movement_percent = (price_movement / testnet_price) * 100
                logger.info(f"📊 Updated Testnet Price: ${updated_testnet_price:.4f}")
                logger.info(f"📈 Price Movement: ${price_movement:.4f} ({movement_percent:.2f}%)")
                
                if mainnet_price:
                    new_diff = abs(mainnet_price - updated_testnet_price)
                    new_diff_percent = (new_diff / mainnet_price) * 100
                    improvement = price_diff - new_diff if mainnet_price and testnet_price else 0
                    logger.info(f"🎯 New Price Difference: ${new_diff:.4f} ({new_diff_percent:.2f}%)")
                    if improvement > 0:
                        logger.info(f"✅ Price moved CLOSER to mainnet by ${improvement:.4f}")
                    elif improvement < 0:
                        logger.info(f"⚠️ Price moved AWAY from mainnet by ${abs(improvement):.4f}")
                    else:
                        logger.info(f"➡️ No significant price movement")
            
            return successful_orders
            
        except Exception as e:
            logger.error(f"❌ Error in parallel order placement: {e}")
            return []
    
    async def _get_mainnet_price(self, market_id: str) -> Optional[float]:
        """Get current mainnet price for a market."""
        try:
            from core.price_feed import price_feed
            # Extract base symbol from market_id (e.g., "INJ/USDT" -> "INJ")
            base_symbol = market_id.split('/')[0]
            price = await price_feed.get_reference_price(base_symbol, "USDT")
            return float(price) if price else None
        except Exception as e:
            logger.error(f"❌ Error fetching mainnet price for {market_id}: {e}")
            return None
    
    async def _get_testnet_price(self, market_id: str) -> Optional[float]:
        """Get current testnet price for a market."""
        try:
            from core.markets import market_manager
            price = await market_manager.get_market_price(market_id)
            return float(price) if price else None
        except Exception as e:
            logger.error(f"❌ Error fetching testnet price for {market_id}: {e}")
            return None
    
    def get_market_maker_status(self) -> Dict[str, Any]:
        """
        Get market maker strategy status.
        
        Returns:
            Market maker status dictionary
        """
        status = self.get_strategy_info()
        status.update({
            "market_orders": self.market_orders,
            "last_rebalance": self.last_rebalance.isoformat(),
            "price_correction": {
                "enabled": self.price_correction_enabled,
                "threshold": self.correction_threshold,
                "cooldown": self.correction_cooldown,
                "last_correction_time": self.last_correction_time,
                "max_correction_orders": self.max_correction_orders
            },
            "emergency_orders": {
                "threshold": self.emergency_threshold,
                "order_size": self.emergency_order_size,
                "cooldown": self.emergency_cooldown,
                "last_emergency_time": self.last_emergency_time
            }
        })
        return status
