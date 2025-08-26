"""
Position data models for the Injective Market Making Bot.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


class PositionSide(str, Enum):
    """Position side enumeration."""
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class Position(BaseModel):
    """Position model."""
    market_id: str
    wallet_id: str
    side: PositionSide
    size: float
    entry_price: float
    current_price: Optional[float] = None
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    margin: float = 0.0
    leverage: float = 1.0
    liquidation_price: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 8) if v is not None else None,
            datetime: lambda v: v.isoformat() if v else None
        }


class PositionSummary(BaseModel):
    """Position summary model."""
    wallet_id: str
    total_positions: int = 0
    total_size: float = 0.0
    total_unrealized_pnl: float = 0.0
    total_realized_pnl: float = 0.0
    total_margin: float = 0.0
    average_leverage: float = 1.0
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 8) if v is not None else None,
            datetime: lambda v: v.isoformat() if v else None
        }


class Trade(BaseModel):
    """Trade model."""
    trade_id: str
    market_id: str
    wallet_id: str
    side: str  # "buy" or "sell"
    price: float
    quantity: float
    fee: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    order_id: Optional[str] = None
    tx_hash: Optional[str] = None
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 8) if v is not None else None,
            datetime: lambda v: v.isoformat() if v else None
        }
