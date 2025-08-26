import asyncio
import aiohttp
import requests
from typing import Dict, Optional, List
from decimal import Decimal
from datetime import datetime, timedelta
import time

from pyinjective.core.network import Network
from pyinjective.indexer_client import IndexerClient
from utils.logger import get_logger

logger = get_logger(__name__)


class PriceFeed:
    """External price feed service for reference prices."""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.price_cache: Dict[str, Dict] = {}
        self.cache_duration = 30  # seconds
        self.last_update: Dict[str, float] = {}
        
        # Injective clients
        self.mainnet_network: Optional[Network] = None
        self.mainnet_indexer: Optional[IndexerClient] = None
        
        # API endpoints (fallback)
        self.coingecko_base = "https://api.coingecko.com/api/v3"
        self.cryptocompare_base = "https://min-api.cryptocompare.com/data"
        
        # Rate limiting
        self.request_delay = 0.1  # seconds between requests
        self.last_request_time = 0
    
    async def initialize(self):
        """Initialize the HTTP session and Injective mainnet client."""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=10)
            self.session = aiohttp.ClientSession(timeout=timeout)
        
        # Initialize mainnet client for oracle prices using explicit endpoint
        if not self.mainnet_indexer:
            # Use built-in mainnet network for reliability
            self.mainnet_network = Network.mainnet()
            self.mainnet_indexer = IndexerClient(self.mainnet_network)
            logger.info("Injective mainnet indexer client initialized with built-in mainnet network")
        
        logger.info("Price feed service initialized")
    
    async def close(self):
        """Close the HTTP session."""
        if self.session:
            await self.session.close()
            logger.info("Price feed service closed")
    
    async def _rate_limit(self):
        """Implement rate limiting."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.request_delay:
            await asyncio.sleep(self.request_delay - time_since_last)
        self.last_request_time = time.time()
    
    def _is_cache_valid(self, symbol: str) -> bool:
        """Check if cached price is still valid."""
        if symbol not in self.last_update:
            return False
        return time.time() - self.last_update[symbol] < self.cache_duration
    
    async def get_price_coingecko(self, symbol: str, quote: str = "usdt") -> Optional[Decimal]:
        """Get price from CoinGecko API."""
        try:
            await self._rate_limit()
            
            # Map symbols to CoinGecko IDs
            symbol_mapping = {
                "INJ": "injective-protocol",
                "BTC": "bitcoin",
                "ETH": "ethereum",
                "ATOM": "cosmos",
                "USDT": "tether"
            }
            
            coin_id = symbol_mapping.get(symbol.upper(), symbol.lower())
            
            url = f"{self.coingecko_base}/simple/price"
            params = {
                "ids": coin_id,
                "vs_currencies": quote.lower()
            }
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if coin_id in data and quote.lower() in data[coin_id]:
                        price = Decimal(str(data[coin_id][quote.lower()]))
                        logger.debug(f"CoinGecko price for {symbol}/{quote}: {price}")
                        return price
                    else:
                        logger.warning(f"Price not found in CoinGecko response: {data}")
                elif response.status == 429:
                    logger.warning("CoinGecko rate limit hit, will retry later")
                else:
                    logger.warning(f"CoinGecko API error: {response.status}")
                    
        except Exception as e:
            logger.error(f"Error fetching price from CoinGecko for {symbol}: {e}")
        
        return None
    

    
    # async def get_price_cryptocompare(self, symbol: str, quote: str = "USDT") -> Optional[Decimal]:
    #     """Get price from CryptoCompare API (fallback)."""
    #     # Removed - using only Injective mainnet
    #     return None
    
    async def get_price_injective_mainnet(self, symbol: str, quote: str = "USDT") -> Optional[Decimal]:
        """Get price from Injective mainnet spot market."""
        try:
            # Debug logging
            logger.info(f"🔍 Fetching mainnet price for {symbol}/{quote}")
            
            # Retry logic for mainnet connection
            max_retries = 3
            retry_delay = 1  # seconds
            
            for attempt in range(max_retries):
                try:
                    # Get spot markets
                    markets_response = await self.mainnet_indexer.fetch_spot_markets()
                    
                    if not markets_response or 'markets' not in markets_response:
                        logger.warning(f"No spot markets found on mainnet (attempt {attempt + 1})")
                        continue
                    
                    # Find the specific market using correct field names
                    market_id = None
                    for market in markets_response['markets']:
                        # Use the correct field names from the SDK response
                        base_symbol = market.get('baseTokenMeta', {}).get('symbol', '')
                        quote_symbol = market.get('quoteTokenMeta', {}).get('symbol', '')
                        
                        if (base_symbol.upper() == symbol.upper() and 
                            quote_symbol.upper() == quote.upper()):
                            market_id = market.get('marketId')
                            break
                    
                    if not market_id:
                        logger.warning(f"Market {symbol}/{quote} not found on mainnet (attempt {attempt + 1})")
                        continue
                    
                    # Get orderbook
                    orderbook_response = await self.mainnet_indexer.fetch_spot_orderbook_v2(market_id, depth=5)
                    
                    if not orderbook_response or 'orderbook' not in orderbook_response:
                        logger.warning(f"No orderbook data for {market_id} on mainnet (attempt {attempt + 1})")
                        continue
                    
                    orderbook = orderbook_response['orderbook']
                    bids = orderbook.get('buys', [])
                    asks = orderbook.get('sells', [])
                    
                    if not bids or not asks:
                        logger.warning(f"Insufficient orderbook data for {market_id} on mainnet (attempt {attempt + 1})")
                        continue
                    
                    # Calculate mid price
                    best_bid = Decimal(str(bids[0]['price']))
                    best_ask = Decimal(str(asks[0]['price']))
                    
                    # Convert from wei format (18 decimals for INJ, 6 for USDT)
                    # Price is in USDT per INJ, so we need to account for the decimal difference
                    # INJ has 18 decimals, USDT has 6 decimals
                    # So the price needs to be multiplied by 10^(18-6) = 10^12
                    price_scale_factor = Decimal('1000000000000')  # 10^12
                    best_bid_scaled = best_bid * price_scale_factor
                    best_ask_scaled = best_ask * price_scale_factor
                    
                    mid_price = (best_bid_scaled + best_ask_scaled) / 2
                    
                    logger.info(f"✅ Mainnet spot price for {symbol}/{quote}: ${mid_price:.4f}")
                    return mid_price
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Mainnet connection attempt {attempt + 1} failed: {e}, retrying in {retry_delay}s...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        raise e
            
            logger.warning(f"Failed to fetch mainnet price for {symbol}/{quote} after {max_retries} attempts")
            return None
            
        except Exception as e:
            logger.debug(f"Mainnet price unavailable for {symbol} (falling back to external sources): {e}")
            return None
    
    async def get_reference_price(self, symbol: str, quote: str = "USDT") -> Optional[Decimal]:
        """Get reference price from Injective mainnet only."""
        cache_key = f"{symbol}_{quote}"
        
        # Check cache first
        if self._is_cache_valid(cache_key):
            cached_data = self.price_cache.get(cache_key, {})
            if "price" in cached_data:
                logger.debug(f"Using cached price for {symbol}/{quote}: {cached_data['price']}")
                return cached_data["price"]
        
        # Get price from Injective mainnet only
        price = await self.get_price_injective_mainnet(symbol, quote)
        source = "injective_mainnet"
        
        # Cache the result
        if price is not None:
            self.price_cache[cache_key] = {
                "price": price,
                "source": source,
                "timestamp": datetime.now().isoformat()
            }
            self.last_update[cache_key] = time.time()
            logger.info(f"Mainnet price for {symbol}/{quote}: ${float(price):.4f}")
        else:
            logger.error(f"Failed to get mainnet price for {symbol}/{quote}")
        
        return price
    
    async def get_multiple_prices(self, symbols: List[str], quote: str = "USDT") -> Dict[str, Optional[Decimal]]:
        """Get prices for multiple symbols efficiently."""
        results = {}
        
        for symbol in symbols:
            price = await self.get_reference_price(symbol, quote)
            results[symbol] = price
        
        return results
    
    async def get_price_deviation(self, testnet_price: Decimal, symbol: str, quote: str = "USDT") -> Optional[Dict]:
        """Calculate price deviation between testnet and reference price."""
        reference_price = await self.get_reference_price(symbol, quote)
        
        if reference_price is None or reference_price == 0:
            logger.warning(f"Cannot calculate deviation: reference price unavailable for {symbol}")
            return None
        
        # Convert both to Decimal for consistent arithmetic
        testnet_decimal = Decimal(str(testnet_price))
        reference_decimal = Decimal(str(reference_price))
        
        deviation_percent = ((testnet_decimal - reference_decimal) / reference_decimal) * 100
        
        return {
            "testnet_price": testnet_decimal,
            "reference_price": reference_decimal,
            "deviation_percent": deviation_percent,
            "is_overvalued": testnet_decimal > reference_decimal,
            "is_undervalued": testnet_decimal < reference_decimal,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_cached_prices(self) -> Dict[str, Dict]:
        """Get all cached prices."""
        return self.price_cache.copy()
    
    def clear_cache(self):
        """Clear the price cache."""
        self.price_cache.clear()
        self.last_update.clear()
        logger.info("Price cache cleared")


# Global price feed instance
price_feed = PriceFeed()
