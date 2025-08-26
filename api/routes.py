"""
REST API routes for the Injective Market Making Bot.
"""

from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from models.order import OrderRequest, OrderResponse
from models.market import MarketConfig
from models.wallet import WalletConfig
from core.markets import market_manager
from core.wallet_manager import wallet_manager
from strategies.market_maker import MarketMakerStrategy
from utils.logger import get_logger

logger = get_logger(__name__)

# Create API router
router = APIRouter()

# Global strategy instance
market_maker_strategy = MarketMakerStrategy()


@router.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Injective Market Making Bot API", "status": "running"}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "market_manager": market_manager.is_initialized,
        "wallet_manager": wallet_manager.is_initialized,
        "strategy_running": market_maker_strategy.is_running
    }


# Market endpoints
@router.get("/markets")
async def get_markets():
    """Get all markets."""
    try:
        markets = []
        for market_id, market_data in market_manager.markets.items():
            market_summary = market_manager.get_market_price_summary(market_id)
            markets.append({
                "market_id": market_id,
                "market_data": market_data.dict(),
                "price_summary": market_summary.dict() if market_summary else None
            })
        
        return {"markets": markets}
    except Exception as e:
        logger.error("Failed to get markets", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/markets/{market_id}")
async def get_market(market_id: str):
    """Get specific market information."""
    try:
        market_data = market_manager.get_market_data(market_id)
        if not market_data:
            raise HTTPException(status_code=404, detail="Market not found")
        
        market_config = market_manager.get_market_config(market_id)
        price_summary = market_manager.get_market_price_summary(market_id)
        orderbook = market_manager.orderbooks.get(market_id)
        
        return {
            "market_id": market_id,
            "market_data": market_data.dict(),
            "market_config": market_config.dict() if market_config else None,
            "price_summary": price_summary.dict() if price_summary else None,
            "orderbook": orderbook.dict() if orderbook else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get market", market_id=market_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/markets/{market_id}/price")
async def get_market_price(market_id: str):
    """Get current market price."""
    try:
        price = await market_manager.update_market_price(market_id)
        if price is None:
            raise HTTPException(status_code=404, detail="Price not available")
        
        return {"market_id": market_id, "price": price}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get market price", market_id=market_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/markets/{market_id}/oracle")
async def get_oracle_price(market_id: str):
    """Get oracle price for a market."""
    try:
        price = await market_manager.update_oracle_price(market_id)
        if price is None:
            raise HTTPException(status_code=404, detail="Oracle price not available")
        
        return {"market_id": market_id, "oracle_price": price}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get oracle price", market_id=market_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# Wallet endpoints
@router.get("/wallets")
async def get_wallets():
    """Get all wallets."""
    try:
        wallets = []
        for wallet_id, wallet_data in wallet_manager.wallets.items():
            performance = wallet_manager.get_wallet_performance(wallet_id)
            wallets.append({
                "wallet_id": wallet_id,
                "wallet_data": wallet_data.dict(),
                "performance": performance.dict() if performance else None
            })
        
        return {"wallets": wallets}
    except Exception as e:
        logger.error("Failed to get wallets", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wallets/{wallet_id}")
async def get_wallet(wallet_id: str):
    """Get specific wallet information."""
    try:
        wallet_data = wallet_manager.get_wallet_data(wallet_id)
        if not wallet_data:
            raise HTTPException(status_code=404, detail="Wallet not found")
        
        performance = wallet_manager.get_wallet_performance(wallet_id)
        
        return {
            "wallet_id": wallet_id,
            "wallet_data": wallet_data.dict(),
            "performance": performance.dict() if performance else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get wallet", wallet_id=wallet_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wallets/{wallet_id}/balances")
async def update_wallet_balances(wallet_id: str):
    """Update wallet balances."""
    try:
        success = await wallet_manager.update_wallet_balances(wallet_id)
        if not success:
            raise HTTPException(status_code=404, detail="Wallet not found")
        
        return {"message": "Balances updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update wallet balances", wallet_id=wallet_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# Strategy endpoints
@router.get("/strategy/status")
async def get_strategy_status():
    """Get strategy status."""
    try:
        return market_maker_strategy.get_market_maker_status()
    except Exception as e:
        logger.error("Failed to get strategy status", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/strategy/start")
async def start_strategy(background_tasks: BackgroundTasks):
    """Start the market making strategy."""
    try:
        if market_maker_strategy.is_running:
            return {"message": "Strategy already running"}
        
        # Get enabled markets
        enabled_markets = market_manager.get_enabled_markets()
        if not enabled_markets:
            raise HTTPException(status_code=400, detail="No enabled markets found")
        
        # Initialize and start strategy
        success = await market_maker_strategy.initialize(enabled_markets)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to initialize strategy")
        
        success = await market_maker_strategy.start()
        if not success:
            raise HTTPException(status_code=500, detail="Failed to start strategy")
        
        return {"message": "Strategy started successfully", "markets": enabled_markets}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start strategy", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/strategy/stop")
async def stop_strategy():
    """Stop the market making strategy."""
    try:
        if not market_maker_strategy.is_running:
            return {"message": "Strategy not running"}
        
        await market_maker_strategy.stop()
        return {"message": "Strategy stopped successfully"}
    except Exception as e:
        logger.error("Failed to stop strategy", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/strategy/execute")
async def execute_strategy():
    """Execute strategy once."""
    try:
        if not market_maker_strategy.is_running:
            raise HTTPException(status_code=400, detail="Strategy not running")
        
        success = await market_maker_strategy.execute()
        if not success:
            raise HTTPException(status_code=500, detail="Strategy execution failed")
        
        return {"message": "Strategy executed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to execute strategy", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# Order endpoints
@router.get("/orders")
async def get_orders(market_id: Optional[str] = None, wallet_id: Optional[str] = None):
    """Get all orders."""
    try:
        orders = []
        for order in market_maker_strategy.orders.values():
            if market_id and order.market_id != market_id:
                continue
            if wallet_id and order.wallet_id != wallet_id:
                continue
            orders.append(order.dict())
        
        return {"orders": orders}
    except Exception as e:
        logger.error("Failed to get orders", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/{order_id}")
async def get_order(order_id: str):
    """Get specific order."""
    try:
        order = market_maker_strategy.orders.get(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        return order.dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get order", order_id=order_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/orders")
async def place_order(order_request: OrderRequest):
    """Place a new order."""
    try:
        response = await market_maker_strategy.place_order(order_request)
        return response.dict()
    except Exception as e:
        logger.error("Failed to place order", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/orders/{order_id}")
async def cancel_order(order_id: str):
    """Cancel an order."""
    try:
        success = await market_maker_strategy.cancel_order(order_id)
        if not success:
            raise HTTPException(status_code=404, detail="Order not found or already cancelled")
        
        return {"message": "Order cancelled successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to cancel order", order_id=order_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/orders")
async def cancel_all_orders(market_id: Optional[str] = None):
    """Cancel all orders."""
    try:
        success = await market_maker_strategy.cancel_all_orders(market_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to cancel orders")
        
        return {"message": "All orders cancelled successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to cancel all orders", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# Configuration endpoints
@router.get("/config/markets")
async def get_market_configs():
    """Get all market configurations."""
    try:
        configs = {}
        for market_id, config in market_manager.market_configs.items():
            configs[market_id] = config.dict()
        
        return {"market_configs": configs}
    except Exception as e:
        logger.error("Failed to get market configs", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/wallets")
async def get_wallet_configs():
    """Get all wallet configurations."""
    try:
        configs = {}
        for wallet_id, config in wallet_manager.wallet_configs.items():
            configs[wallet_id] = config.dict()
        
        return {"wallet_configs": configs}
    except Exception as e:
        logger.error("Failed to get wallet configs", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
