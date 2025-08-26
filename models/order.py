"""
Order data models for the Injective Market Making Bot.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


class OrderSide(str, Enum):
    """Order side enumeration."""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type enumeration."""
    LIMIT = "limit"
    MARKET = "market"


class OrderStatus(str, Enum):
    """Order status enumeration."""
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Order(BaseModel):
    """Order model."""
    order_id: str
    market_id: str
    wallet_id: str
    side: OrderSide
    order_type: OrderType = OrderType.LIMIT
    price: float
    quantity: float
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    average_price: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    tx_hash: Optional[str] = None
    error_message: Optional[str] = None
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 8) if v is not None else None,
            datetime: lambda v: v.isoformat() if v else None
        }


class OrderRequest(BaseModel):
    """Order request model."""
    market_id: str
    wallet_id: str
    side: OrderSide
    order_type: OrderType = OrderType.LIMIT
    price: float
    quantity: float
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 8) if v is not None else None
        }


class OrderResponse(BaseModel):
    """Order response model."""
    success: bool
    order_id: Optional[str] = None
    tx_hash: Optional[str] = None
    error_message: Optional[str] = None
    order: Optional[Order] = None


class OrderUpdate(BaseModel):
    """Order update model for real-time updates."""
    order_id: str
    market_id: str
    wallet_id: str
    status: OrderStatus
    filled_quantity: float
    average_price: Optional[float] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 8) if v is not None else None,
            datetime: lambda v: v.isoformat() if v else None
        }
