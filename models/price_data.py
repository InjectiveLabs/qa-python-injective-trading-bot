"""
Price data models for the Injective Market Making Bot.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


class PriceSource(str, Enum):
    """Price source enumeration."""
    ORACLE = "oracle"
    MARKET = "market"
    EXTERNAL = "external"


class PriceData(BaseModel):
    """Price data model."""
    market_id: str
    price: float
    source: PriceSource
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    volume_24h: Optional[float] = None
    change_24h: Optional[float] = None
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 8) if v is not None else None,
            datetime: lambda v: v.isoformat() if v else None
        }


class PriceDeviation(BaseModel):
    """Price deviation model."""
    market_id: str
    testnet_price: float
    oracle_price: float
    deviation_percent: float
    deviation_amount: float
    is_overvalued: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    exceeds_threshold: bool = False
    threshold: float = 5.0
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 8) if v is not None else None,
            datetime: lambda v: v.isoformat() if v else None
        }


class PriceCorrectionAction(BaseModel):
    """Price correction action model."""
    market_id: str
    deviation: PriceDeviation
    action_type: str  # "increase_buy", "increase_sell", "reduce_buy", "reduce_sell"
    aggressiveness: float
    target_price: float
    order_size_multiplier: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 8) if v is not None else None,
            datetime: lambda v: v.isoformat() if v else None
        }


class PriceAlert(BaseModel):
    """Price alert model."""
    market_id: str
    alert_type: str  # "deviation", "correction", "threshold"
    message: str
    severity: str  # "low", "medium", "high", "critical"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class MarketPriceSummary(BaseModel):
    """Market price summary model."""
    market_id: str
    current_price: Optional[float] = None
    oracle_price: Optional[float] = None
    price_deviation: Optional[float] = None
    volume_24h: Optional[float] = None
    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    spread_percent: Optional[float] = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 8) if v is not None else None,
            datetime: lambda v: v.isoformat() if v else None
        }
