"""
Market data models for the Injective Market Making Bot.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class MarketType(str, Enum):
    """Market type enumeration."""
    SPOT = "spot"
    DERIVATIVE = "derivative"


class PriceCorrectionConfig(BaseModel):
    """Price correction configuration."""
    enabled: bool = True
    deviation_threshold: float = Field(default=5.0, ge=0.1, le=50.0)
    correction_aggressiveness: float = Field(default=0.7, ge=0.1, le=1.0)
    max_correction_size: float = Field(default=100.0, ge=1.0)
    correction_cooldown: int = Field(default=300, ge=60)  # seconds


class MarketConfig(BaseModel):
    """Market configuration model."""
    market_id: str
    enabled: bool = True
    type: MarketType = MarketType.SPOT
    spread_percent: float = Field(default=0.5, ge=0.01, le=10.0)
    order_size: float = Field(default=10.0, ge=0.1)
    min_spread: float = Field(default=0.1, ge=0.01)
    max_spread: float = Field(default=2.0, ge=0.1)
    max_wallets: int = Field(default=3, ge=1, le=10)
    orders_per_wallet: int = Field(default=2, ge=1, le=10)
    price_correction: PriceCorrectionConfig = Field(default_factory=PriceCorrectionConfig)


class MarketData(BaseModel):
    """Market data model."""
    market_id: str
    base_denom: str
    quote_denom: str
    type: MarketType
    current_price: Optional[float] = None
    oracle_price: Optional[float] = None
    price_deviation: Optional[float] = None
    last_updated: Optional[str] = None
    is_active: bool = True
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 8) if v is not None else None
        }


class OrderBookLevel(BaseModel):
    """Order book level model."""
    price: float
    quantity: float
    side: str  # "buy" or "sell"


class OrderBook(BaseModel):
    """Order book model."""
    market_id: str
    bids: list[OrderBookLevel] = []
    asks: list[OrderBookLevel] = []
    timestamp: Optional[str] = None
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 8) if v is not None else None
        }
