"""
Base strategy class for the Injective Market Making Bot.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime
from models.order import Order, OrderRequest, OrderResponse, OrderType, OrderSide
from models.market import MarketConfig
from models.wallet import WalletData
from core.markets import market_manager
from core.wallet_manager import wallet_manager
from core.client import injective_client
from utils.logger import get_logger
import asyncio

logger = get_logger(__name__)


class BaseStrategy(ABC):
    """Base class for all trading strategies."""
    
    def __init__(self, strategy_name: str):
        """
        Initialize base strategy.
        
        Args:
            strategy_name: Name of the strategy
        """
        self.strategy_name = strategy_name
        self.is_running = False
        self.markets: List[str] = []
        self.orders: Dict[str, Order] = {}
        self.last_update = datetime.utcnow()
        
    @abstractmethod
    async def initialize(self, markets: List[str]) -> bool:
        """
        Initialize strategy for specific markets.
        
        Args:
            markets: List of market IDs to trade
            
        Returns:
            True if initialization successful
        """
        pass
    
    @abstractmethod
    async def execute(self) -> bool:
        """
        Execute the strategy logic.
        
        Returns:
            True if execution successful
        """
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop the strategy."""
        pass
    
    async def place_order(self, order_request: OrderRequest) -> OrderResponse:
        """
        Place an order using the appropriate wallet.
        
        Args:
            order_request: Order request details
            
        Returns:
            Order response
        """
        try:
            # Get wallet for this market (or use strategy-specific wallet if provided)
            if hasattr(self, 'wallet_id') and self.wallet_id:
                wallet_id = self.wallet_id
            else:
                wallet_id = wallet_manager.get_wallet_for_market(order_request.market_id)
            if not wallet_id:
                return OrderResponse(
                    success=False,
                    error_message="No available wallet for market"
                )
            
            # Check if wallet can place order
            if not wallet_manager.can_place_order(wallet_id, order_request.market_id):
                return OrderResponse(
                    success=False,
                    error_message="Wallet cannot place order"
                )
            
            # Get wallet client
            client = wallet_manager.get_wallet_client(wallet_id)
            if not client:
                return OrderResponse(
                    success=False,
                    error_message="Wallet client not available"
                )
            
            # Get market config for market ID
            market_config = await market_manager.get_market_config(order_request.market_id)
            if not market_config:
                return OrderResponse(
                    success=False,
                    error_message="Market config not found"
                )
            
            # Convert price to Decimal for precision
            from decimal import Decimal
            price_decimal = Decimal(str(order_request.price))
            quantity_decimal = Decimal(str(order_request.quantity))
            
            # Round price to tick size (0.001) to avoid blockchain rejection
            tick_size = Decimal("0.001")
            price_rounded = (price_decimal / tick_size).quantize(Decimal("1")) * tick_size
            
            # Get wallet data for the selected wallet
            wallet_data = await wallet_manager.get_wallet_data(wallet_id)
            if not wallet_data:
                return OrderResponse(
                    success=False,
                    error_message=f"Wallet data not found for {wallet_id}"
                )
            
            # Use wallet-specific client if available, otherwise use main client
            if hasattr(self, 'wallet_client') and self.wallet_client and isinstance(self.wallet_client, dict):
                # Use wallet-specific client
                client = self.wallet_client
                order_msg = client['composer'].msg_create_spot_limit_order(
                    sender=client['address'].to_acc_bech32(),
                    market_id=market_config.market_id,
                    subaccount_id=client['address'].get_subaccount_id(0),
                    fee_recipient=client['address'].to_acc_bech32(),
                    price=price_rounded,
                    quantity=quantity_decimal,
                    order_type=order_request.side.value.upper(),
                    cid=None
                )
                wallet_broadcaster = client['broadcaster']
            else:
                # Use main client
                order_msg = injective_client.composer.msg_create_spot_limit_order(
                    sender=injective_client.address.to_acc_bech32(),
                    market_id=market_config.market_id,
                    subaccount_id=injective_client.address.get_subaccount_id(0),
                    fee_recipient=injective_client.address.to_acc_bech32(),
                    price=price_rounded,
                    quantity=quantity_decimal,
                    order_type=order_request.side.value.upper(),
                    cid=None
                )
                wallet_broadcaster = injective_client.message_broadcaster
            
            # Broadcast order using wallet-specific broadcaster
            logger.info(f"📤 Broadcasting {order_request.side.value.upper()} order: {quantity_decimal} INJ at ${float(price_rounded):.4f} using wallet {wallet_id}")
            response = await wallet_broadcaster.broadcast([order_msg])
            
            # Extract transaction hash and order ID
            tx_hash = response.get('txhash', 'unknown')
            order_id = f"{order_request.market_id}_{datetime.utcnow().timestamp()}"
            
            # Create order object
            order = Order(
                order_id=order_id,
                market_id=order_request.market_id,
                wallet_id=wallet_id,
                side=order_request.side,
                order_type=order_request.order_type,
                price=order_request.price,
                quantity=order_request.quantity,
                status="pending"
            )
            
            # Store order
            self.orders[order.order_id] = order
            
            # Update wallet order count
            wallet_manager.update_order_count(wallet_id, 1)
            
            logger.info(f"✅ Order placed successfully!", 
                       order_id=order.order_id,
                       market_id=order_request.market_id,
                       wallet_id=wallet_id,
                       side=order_request.side.value.upper(),
                       price=f"${float(price_rounded):.4f}",
                       quantity=f"{float(quantity_decimal):.2f} INJ",
                       tx_hash=tx_hash)
            
            return OrderResponse(
                success=True,
                order_id=order.order_id,
                order=order
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to place order: {str(e)}", 
                        market_id=order_request.market_id,
                        side=order_request.side.value.upper(),
                        price=f"${order_request.price:.4f}",
                        quantity=f"{order_request.quantity:.2f} INJ")
            return OrderResponse(
                success=False,
                error_message=str(e)
            )
    
    async def place_market_order(self, order_request: OrderRequest) -> OrderResponse:
        """
        Place a market order for immediate execution.
        Note: Injective doesn't have native market orders, so we simulate with aggressive limit orders.
        
        Args:
            order_request: Order request details (price will be ignored for market orders)
            
        Returns:
            Order response
        """
        try:
            # Get wallet for this market (or use strategy-specific wallet if provided)
            if hasattr(self, 'wallet_id') and self.wallet_id:
                wallet_id = self.wallet_id
            else:
                wallet_id = wallet_manager.get_wallet_for_market(order_request.market_id)
            if not wallet_id:
                return OrderResponse(
                    success=False,
                    error_message="No available wallet for market"
                )
            
            # Check if wallet can place order
            if not wallet_manager.can_place_order(wallet_id, order_request.market_id):
                return OrderResponse(
                    success=False,
                    error_message="Wallet cannot place order"
                )
            
            # Get wallet client
            client = wallet_manager.get_wallet_client(wallet_id)
            if not client:
                return OrderResponse(
                    success=False,
                    error_message="Wallet client not available"
                )
            
            # Get market config for market ID
            market_config = await market_manager.get_market_config(order_request.market_id)
            if not market_config:
                return OrderResponse(
                    success=False,
                    error_message="Market config not found"
                )
            
            # Convert quantity to Decimal for precision
            from decimal import Decimal
            quantity_decimal = Decimal(str(order_request.quantity))
            
            # For market orders, we use aggressive pricing (0.1% from current market price)
            # Get current market price
            market_data = await market_manager.get_market_data(order_request.market_id)
            if not market_data or not market_data.current_price:
                return OrderResponse(
                    success=False,
                    error_message="Cannot get current market price for market order"
                )
            
            current_price = Decimal(str(market_data.current_price))
            
            # Calculate aggressive price (0.1% from current price)
            if order_request.side == OrderSide.BUY:
                # For buy orders, place slightly above current price
                price_rounded = current_price * Decimal("1.001")
            else:
                # For sell orders, place slightly below current price
                price_rounded = current_price * Decimal("0.999")
            
            # Round to tick size (0.001)
            tick_size = Decimal("0.001")
            price_rounded = (price_rounded / tick_size).quantize(Decimal("1")) * tick_size
            
            # Get wallet data for the selected wallet
            wallet_data = await wallet_manager.get_wallet_data(wallet_id)
            if not wallet_data:
                return OrderResponse(
                    success=False,
                    error_message=f"Wallet data not found for {wallet_id}"
                )
            
            # Use wallet-specific client if available, otherwise use main client
            if hasattr(self, 'wallet_client') and self.wallet_client and isinstance(self.wallet_client, dict):
                # Use wallet-specific client
                client = self.wallet_client
                order_msg = client['composer'].msg_create_spot_limit_order(
                    sender=client['address'].to_acc_bech32(),
                    market_id=market_config.market_id,
                    subaccount_id=client['address'].get_subaccount_id(0),
                    fee_recipient=client['address'].to_acc_bech32(),
                    price=price_rounded,
                    quantity=quantity_decimal,
                    order_type=order_request.side.value.upper(),
                    cid=None
                )
                wallet_broadcaster = client['broadcaster']
            else:
                # Use main client
                order_msg = injective_client.composer.msg_create_spot_limit_order(
                    sender=injective_client.address.to_acc_bech32(),
                    market_id=market_config.market_id,
                    subaccount_id=injective_client.address.get_subaccount_id(0),
                    fee_recipient=injective_client.address.to_acc_bech32(),
                    price=price_rounded,
                    quantity=quantity_decimal,
                    order_type=order_request.side.value.upper(),
                    cid=None
                )
                wallet_broadcaster = injective_client.message_broadcaster
            
            # Broadcast order using wallet-specific broadcaster
            logger.info(f"🚨🚨 Broadcasting EMERGENCY {order_request.side.value.upper()} market order: {quantity_decimal} INJ at ${float(price_rounded):.4f} using wallet {wallet_id}")
            response = await wallet_broadcaster.broadcast([order_msg])
            
            # Extract order ID from response
            order_id = f"{order_request.market_id}_market_{datetime.utcnow().timestamp()}"
            
            # Create order object
            order = Order(
                order_id=order_id,
                market_id=order_request.market_id,
                wallet_id=wallet_id,
                side=order_request.side,
                order_type=OrderType.MARKET,
                price=float(price_rounded),  # Store the aggressive price used
                quantity=order_request.quantity,
                status="pending"
            )
            
            # Store order
            self.orders[order.order_id] = order
            
            # Update wallet order count
            wallet_manager.update_order_count(wallet_id, 1)
            
            logger.info("Market order (aggressive limit) placed successfully", 
                       order_id=order.order_id,
                       market_id=order_request.market_id,
                       wallet_id=wallet_id,
                       side=order_request.side,
                       price=float(price_rounded),
                       quantity=order_request.quantity,
                       response=response)
            
            return OrderResponse(
                success=True,
                order_id=order.order_id,
                order=order
            )
            
        except Exception as e:
            logger.error("Failed to place market order", 
                        market_id=order_request.market_id,
                        error=str(e))
            return OrderResponse(
                success=False,
                error_message=str(e)
            )
    
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if cancellation successful
        """
        try:
            if order_id not in self.orders:
                logger.warning("Order not found", order_id=order_id)
                return False
            
            order = self.orders[order_id]
            
            # Get wallet client
            client = wallet_manager.get_wallet_client(order.wallet_id)
            if not client:
                logger.error("Wallet client not available", wallet_id=order.wallet_id)
                return False
            
            # Cancel order using Injective SDK
            # TODO: Implement actual order cancellation
            
            # Update order status
            order.status = "cancelled"
            logger.info("Order cancelled", order_id=order_id)
            return True
            
        except Exception as e:
            logger.error("Failed to cancel order", order_id=order_id, error=str(e))
            return False
    
    async def get_orders(self, market_id: Optional[str] = None) -> List[Order]:
        """
        Get all orders or orders for a specific market.
        
        Args:
            market_id: Optional market ID to filter orders
            
        Returns:
            List of orders
        """
        if market_id:
            return [order for order in self.orders.values() if order.market_id == market_id]
        return list(self.orders.values())
    
    async def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get a specific order by ID.
        
        Args:
            order_id: Order ID
            
        Returns:
            Order object or None if not found
        """
        return self.orders.get(order_id)
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """
        Get strategy information.
        
        Returns:
            Strategy info dictionary
        """
        return {
            "strategy_name": self.strategy_name,
            "is_running": self.is_running,
            "markets": self.markets,
            "total_orders": len(self.orders),
            "last_update": self.last_update.isoformat()
        }
