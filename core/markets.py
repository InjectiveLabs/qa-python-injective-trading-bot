"""
Market discovery and management for the Injective Market Making Bot.
"""

import asyncio
import json
from typing import Dict, List, Optional, Any
from pathlib import Path

from config.settings import settings
from core.client import injective_client
from models.market import MarketConfig, MarketData, MarketType
from utils.logger import get_logger

logger = get_logger(__name__)

class MarketManager:
    """Manages market discovery, configuration, and price updates."""
    
    def __init__(self):
        self.market_configs: Dict[str, MarketConfig] = {}
        self.market_data: Dict[str, MarketData] = {}
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the market manager."""
        try:
            # Load market configurations
            await self._load_market_configs()
            
            # Initialize market data
            await self._initialize_market_data()
            
            self._initialized = True
            logger.info(f"Market manager initialized with {len(self.market_configs)} markets")
            
        except Exception as e:
            logger.error(f"Failed to initialize market manager: {e}")
            raise
    
    async def _load_market_configs(self) -> None:
        """Load market configurations from JSON file."""
        try:
            config_path = Path(settings.config_file)
            if not config_path.exists():
                logger.warning(f"Market config file not found: {config_path}")
                return
            
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            markets_config = config_data.get('markets', {})
            
            for market_symbol, market_config in markets_config.items():
                if market_config.get('enabled', False):
                    self.market_configs[market_symbol] = MarketConfig(
                        market_id=market_config.get('market_id', ''),
                        enabled=market_config.get('enabled', False),
                        type=MarketType(market_config.get('type', 'spot')),
                        spread_percent=market_config.get('spread_percent', 0.5),
                        order_size=market_config.get('order_size', 10),
                        min_spread=market_config.get('min_spread', 0.1),
                        max_spread=market_config.get('max_spread', 2.0),
                        max_wallets=market_config.get('max_wallets', 3),
                        orders_per_wallet=market_config.get('orders_per_wallet', 2),
                        price_correction=market_config.get('price_correction', {})
                    )
            
            logger.info(f"Loaded {len(self.market_configs)} market configurations")
            
        except Exception as e:
            logger.error(f"Failed to load market configs: {e}")
            raise
    
    async def _initialize_market_data(self) -> None:
        """Initialize market data for configured markets."""
        try:
            # Get all available markets from Injective
            spot_markets_response = await injective_client.get_spot_markets()
            derivative_markets_response = await injective_client.get_derivative_markets()
            
            # Create dictionaries for easy lookup by market ID
            spot_markets = {}
            derivative_markets = {}
            
            if spot_markets_response and 'markets' in spot_markets_response:
                for market in spot_markets_response['markets']:
                    market_id = market.get('marketId')
                    if market_id:
                        spot_markets[market_id] = market
            
            if derivative_markets_response and 'markets' in derivative_markets_response:
                for market in derivative_markets_response['markets']:
                    market_id = market.get('marketId')
                    if market_id:
                        derivative_markets[market_id] = market
            
            # Initialize market data for configured markets
            for market_symbol, config in self.market_configs.items():
                market_info = None
                
                if config.type == MarketType.SPOT:
                    market_info = spot_markets.get(config.market_id)
                elif config.type == MarketType.DERIVATIVE:
                    market_info = derivative_markets.get(config.market_id)
                
                if market_info:
                    base_token = market_info.get('baseTokenMeta', {})
                    quote_token = market_info.get('quoteTokenMeta', {})
                    
                    base_denom = base_token.get('symbol', market_info.get('baseDenom', ''))
                    quote_denom = quote_token.get('symbol', market_info.get('quoteDenom', ''))
                    
                    # Fallback: extract from market symbol if still empty
                    if not base_denom and '/' in market_symbol:
                        base_denom = market_symbol.split('/')[0]
                    if not quote_denom and '/' in market_symbol:
                        quote_denom = market_symbol.split('/')[1]
                    
                    self.market_data[market_symbol] = MarketData(
                        market_id=config.market_id,
                        base_denom=base_denom,
                        quote_denom=quote_denom,
                        type=config.type,
                        is_active=market_info.get('marketStatus') == 'active'
                    )
                    logger.debug(f"Initialized market data for {market_symbol}: {base_denom}/{quote_denom}")
                else:
                    logger.warning(f"Market {market_symbol} not found in available markets (ID: {config.market_id})")
                    # Fallback: use symbol parsing for basic functionality
                    if '/' in market_symbol:
                        base, quote = market_symbol.split('/', 1)
                        self.market_data[market_symbol] = MarketData(
                            market_id=config.market_id,
                            base_denom=base,
                            quote_denom=quote,
                            type=config.type,
                            is_active=True
                        )
                        logger.info(f"Created fallback market data for {market_symbol}: {base}/{quote}")
            
        except Exception as e:
            logger.error(f"Failed to initialize market data: {e}")
            raise
    
    async def get_enabled_markets(self) -> Dict[str, MarketConfig]:
        """Get all enabled markets."""
        return {k: v for k, v in self.market_configs.items() if v.enabled}
    
    async def get_market_config(self, market_id: str) -> Optional[MarketConfig]:
        """Get market configuration for a specific market."""
        return self.market_configs.get(market_id)
    
    async def get_market_data(self, market_id: str) -> Optional[MarketData]:
        """Get market data for a specific market."""
        return self.market_data.get(market_id)
    
    async def get_market_price(self, market_id: str) -> Optional[float]:
        """Get current market price from orderbook."""
        try:
            config = await self.get_market_config(market_id)
            if not config:
                return None
            
            # Use the actual market ID from config, not the symbol
            actual_market_id = config.market_id
            
            if config.type == MarketType.SPOT:
                orderbook = await injective_client.get_spot_orderbook(actual_market_id)
            else:
                orderbook = await injective_client.get_derivative_orderbook(actual_market_id)
            
            if not orderbook or 'orderbook' not in orderbook:
                return None
            
            orderbook_data = orderbook['orderbook']
            buys = orderbook_data.get('buys', [])
            sells = orderbook_data.get('sells', [])
            
            if buys and sells:
                # Get market details for price scaling
                markets = await injective_client.get_spot_markets()
                price_scale_factor = 1.0  # Default scaling
                
                if markets and 'markets' in markets:
                    for market in markets['markets']:
                        if market.get('marketId') == actual_market_id:
                            base_decimals = market.get('baseTokenMeta', {}).get('decimals', 18)
                            quote_decimals = market.get('quoteTokenMeta', {}).get('decimals', 6)
                            price_scale_factor = 10 ** (base_decimals - quote_decimals)
                            break
                
                # Apply price scaling to convert to USDT
                best_bid_raw = float(buys[0]['price'])
                best_ask_raw = float(sells[0]['price'])
                best_bid = best_bid_raw * price_scale_factor
                best_ask = best_ask_raw * price_scale_factor
                
                mid_price = (best_bid + best_ask) / 2
                return mid_price
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get market price for {market_id}: {e}")
            return None
    
    async def get_oracle_price(self, market_id: str) -> Optional[float]:
        """Get oracle price for a market using external price feed."""
        try:
            market_data = await self.get_market_data(market_id)
            if not market_data:
                return None
            
            # Use external price feed instead of non-existent oracle method
            from core.price_feed import price_feed
            oracle_price = await price_feed.get_reference_price(
                market_data.base_denom, 
                market_data.quote_denom
            )
            
            if oracle_price:
                return float(oracle_price)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get oracle price for {market_id}: {e}")
            return None
    
    async def calculate_price_deviation(self, market_id: str) -> Optional[float]:
        """Calculate price deviation between market and oracle prices."""
        try:
            market_price = await self.get_market_price(market_id)
            oracle_price = await self.get_oracle_price(market_id)
            
            if market_price and oracle_price and oracle_price > 0:
                deviation = abs(market_price - oracle_price) / oracle_price * 100
                return deviation
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to calculate price deviation for {market_id}: {e}")
            return None
    
    async def update_market_data(self) -> None:
        """Update market data for all enabled markets."""
        try:
            for market_id in self.market_configs.keys():
                if self.market_configs[market_id].enabled:
                    # Update price data
                    market_price = await self.get_market_price(market_id)
                    oracle_price = await self.get_oracle_price(market_id)
                    deviation = await self.calculate_price_deviation(market_id)
                    
                    if market_id in self.market_data:
                        self.market_data[market_id].current_price = market_price
                        self.market_data[market_id].oracle_price = oracle_price
                        self.market_data[market_id].price_deviation = deviation
            
            logger.debug("Market data updated")
            
        except Exception as e:
            logger.error(f"Failed to update market data: {e}")
    
    def is_initialized(self) -> bool:
        """Check if market manager is initialized."""
        return self._initialized

# Global market manager instance
market_manager = MarketManager()
