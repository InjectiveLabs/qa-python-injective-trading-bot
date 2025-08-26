import asyncio
from typing import Dict, Optional, List
from decimal import Decimal
from datetime import datetime, timedelta
import time

from core.client import injective_client
from core.price_feed import price_feed
from core.markets import market_manager
from models.market import MarketData
from utils.logger import get_logger

logger = get_logger(__name__)


class PriceMonitor:
    """Monitors price discrepancies between testnet and reference prices."""
    
    def __init__(self):
        self.monitoring_active = False
        self.monitoring_interval = 30  # seconds
        self.deviation_threshold = 5.0  # percentage
        self.price_history: Dict[str, List[Dict]] = {}
        self.alerts: List[Dict] = []
        self.max_alerts = 100
        
        # Price correction tracking
        self.correction_active: Dict[str, bool] = {}
        self.correction_start_time: Dict[str, datetime] = {}
        self.correction_cooldown = 300  # seconds
    
    async def initialize(self):
        """Initialize the price monitor."""
        await price_feed.initialize()
        logger.info("Price monitor initialized")
    
    async def start_monitoring(self):
        """Start continuous price monitoring."""
        if self.monitoring_active:
            logger.warning("Price monitoring already active")
            return
        
        self.monitoring_active = True
        logger.info("Starting price monitoring...")
        
        while self.monitoring_active:
            try:
                await self._monitor_prices()
                await asyncio.sleep(self.monitoring_interval)
            except Exception as e:
                logger.error(f"Error in price monitoring: {e}")
                await asyncio.sleep(10)  # Wait before retrying
    
    async def stop_monitoring(self):
        """Stop price monitoring."""
        self.monitoring_active = False
        logger.info("Price monitoring stopped")
    
    async def _monitor_prices(self):
        """Monitor prices for all configured markets."""
        for market_symbol, market_data in market_manager.market_data.items():
            try:
                await self._check_market_price(market_symbol, market_data)
            except Exception as e:
                logger.error(f"Error monitoring {market_symbol}: {e}")
    
    async def _check_market_price(self, market_symbol: str, market_data: MarketData):
        """Check price for a specific market."""
        # Get testnet price from orderbook
        testnet_price = await self._get_testnet_price(market_symbol, market_data)
        if testnet_price is None:
            logger.warning(f"Could not get testnet price for {market_symbol}")
            return
        
        # Extract base symbol for reference price
        base_symbol = market_data.base_denom
        if not base_symbol:
            # Fallback: extract from market symbol
            if '/' in market_symbol:
                base_symbol = market_symbol.split('/')[0]
            else:
                logger.warning(f"No base symbol found for {market_symbol}")
                return
        
        if base_symbol == "inj":
            base_symbol = "INJ"
        elif base_symbol == "btc":
            base_symbol = "BTC"
        elif base_symbol == "eth":
            base_symbol = "ETH"
        elif base_symbol == "atom":
            base_symbol = "ATOM"
        
        # Get reference price
        reference_price = await price_feed.get_reference_price(base_symbol, "USDT")
        if reference_price is None:
            logger.warning(f"Could not get reference price for {base_symbol}")
            return
        
        # Calculate deviation
        deviation = await self._calculate_deviation(testnet_price, reference_price, market_symbol)
        if deviation is None:
            return
        
        # Store price history
        self._store_price_history(market_symbol, testnet_price, reference_price, deviation)
        
        # Check for alerts
        await self._check_deviation_alert(market_symbol, deviation)
        
        # Log current status
        logger.info(f"{market_symbol}: Testnet={testnet_price:.6f}, Reference={reference_price:.6f}, "
                   f"Deviation={deviation['deviation_percent']:.2f}%")
    
    async def _get_testnet_price(self, market_symbol: str, market_data: MarketData) -> Optional[Decimal]:
        """Get current testnet price from orderbook."""
        try:
            if market_data.type.value == "spot":
                orderbook = await injective_client.get_spot_orderbook(market_data.market_id, depth=5)
            else:
                orderbook = await injective_client.get_derivative_orderbook(market_data.market_id, depth=5)
            
            if not orderbook or 'orderbook' not in orderbook:
                return None
            
            orderbook_data = orderbook['orderbook']
            
            # Calculate mid price from best bid and ask
            bids = orderbook_data.get('bids', [])
            asks = orderbook_data.get('asks', [])
            
            if not bids or not asks:
                logger.warning(f"No bids or asks for {market_symbol}")
                return None
            
            best_bid = Decimal(str(bids[0]['price']))
            best_ask = Decimal(str(asks[0]['price']))
            
            # Convert from wei if needed
            if best_bid < 0.001:  # Likely in wei
                best_bid = best_bid * Decimal('1000000000000000000')
                best_ask = best_ask * Decimal('1000000000000000000')
            
            mid_price = (best_bid + best_ask) / 2
            return mid_price
            
        except Exception as e:
            logger.error(f"Error getting testnet price for {market_symbol}: {e}")
            return None
    
    async def _calculate_deviation(self, testnet_price: Decimal, reference_price: Decimal, market_symbol: str) -> Optional[Dict]:
        """Calculate price deviation."""
        if reference_price == 0:
            return None
        
        deviation_percent = ((testnet_price - reference_price) / reference_price) * 100
        
        return {
            "testnet_price": testnet_price,
            "reference_price": reference_price,
            "deviation_percent": deviation_percent,
            "is_overvalued": testnet_price > reference_price,
            "is_undervalued": testnet_price < reference_price,
            "timestamp": datetime.now().isoformat()
        }
    
    def _store_price_history(self, market_symbol: str, testnet_price: Decimal, reference_price: Decimal, deviation: Dict):
        """Store price history for analysis."""
        if market_symbol not in self.price_history:
            self.price_history[market_symbol] = []
        
        history_entry = {
            "timestamp": datetime.now().isoformat(),
            "testnet_price": float(testnet_price),
            "reference_price": float(reference_price),
            "deviation_percent": deviation["deviation_percent"],
            "is_overvalued": deviation["is_overvalued"],
            "is_undervalued": deviation["is_undervalued"]
        }
        
        self.price_history[market_symbol].append(history_entry)
        
        # Keep only last 100 entries
        if len(self.price_history[market_symbol]) > 100:
            self.price_history[market_symbol] = self.price_history[market_symbol][-100:]
    
    async def _check_deviation_alert(self, market_symbol: str, deviation: Dict):
        """Check if deviation exceeds threshold and create alert."""
        deviation_percent = abs(deviation["deviation_percent"])
        
        if deviation_percent > self.deviation_threshold:
            alert = {
                "market_symbol": market_symbol,
                "deviation_percent": deviation["deviation_percent"],
                "testnet_price": deviation["testnet_price"],
                "reference_price": deviation["reference_price"],
                "is_overvalued": deviation["is_overvalued"],
                "is_undervalued": deviation["is_undervalued"],
                "timestamp": datetime.now().isoformat(),
                "severity": "high" if deviation_percent > 10 else "medium"
            }
            
            self.alerts.append(alert)
            
            # Keep only recent alerts
            if len(self.alerts) > self.max_alerts:
                self.alerts = self.alerts[-self.max_alerts:]
            
            logger.warning(f"🚨 PRICE DEVIATION ALERT: {market_symbol} deviates by {deviation_percent:.2f}% "
                          f"({'overvalued' if deviation['is_overvalued'] else 'undervalued'})")
    
    def is_correction_needed(self, market_symbol: str) -> bool:
        """Check if price correction is needed for a market."""
        if market_symbol not in self.price_history or not self.price_history[market_symbol]:
            return False
        
        latest = self.price_history[market_symbol][-1]
        deviation_percent = abs(latest["deviation_percent"])
        
        # Check if deviation exceeds threshold
        if deviation_percent < self.deviation_threshold:
            return False
        
        # Check cooldown
        if market_symbol in self.correction_active and self.correction_active[market_symbol]:
            if market_symbol in self.correction_start_time:
                elapsed = (datetime.now() - self.correction_start_time[market_symbol]).total_seconds()
                if elapsed < self.correction_cooldown:
                    return False
        
        return True
    
    def get_correction_direction(self, market_symbol: str) -> Optional[str]:
        """Get the direction for price correction."""
        if market_symbol not in self.price_history or not self.price_history[market_symbol]:
            return None
        
        latest = self.price_history[market_symbol][-1]
        
        if latest["is_overvalued"]:
            return "sell"  # Need to push price down
        elif latest["is_undervalued"]:
            return "buy"   # Need to push price up
        
        return None
    
    def start_correction(self, market_symbol: str):
        """Mark that correction has started for a market."""
        self.correction_active[market_symbol] = True
        self.correction_start_time[market_symbol] = datetime.now()
        logger.info(f"Price correction started for {market_symbol}")
    
    def stop_correction(self, market_symbol: str):
        """Mark that correction has stopped for a market."""
        self.correction_active[market_symbol] = False
        if market_symbol in self.correction_start_time:
            del self.correction_start_time[market_symbol]
        logger.info(f"Price correction stopped for {market_symbol}")
    
    def get_price_summary(self) -> Dict:
        """Get summary of current price status."""
        summary = {
            "monitoring_active": self.monitoring_active,
            "markets": {},
            "alerts_count": len(self.alerts),
            "recent_alerts": self.alerts[-5:] if self.alerts else []
        }
        
        for market_symbol, history in self.price_history.items():
            if history:
                latest = history[-1]
                summary["markets"][market_symbol] = {
                    "current_deviation": latest["deviation_percent"],
                    "testnet_price": latest["testnet_price"],
                    "reference_price": latest["reference_price"],
                    "is_overvalued": latest["is_overvalued"],
                    "is_undervalued": latest["is_undervalued"],
                    "correction_active": self.correction_active.get(market_symbol, False),
                    "last_update": latest["timestamp"]
                }
        
        return summary
    
    def get_alerts(self, limit: int = 10) -> List[Dict]:
        """Get recent alerts."""
        return self.alerts[-limit:] if self.alerts else []
    
    def clear_alerts(self):
        """Clear all alerts."""
        self.alerts.clear()
        logger.info("Price alerts cleared")


# Global price monitor instance
price_monitor = PriceMonitor()
