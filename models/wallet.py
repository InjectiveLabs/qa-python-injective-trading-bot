"""
Wallet data models for the Injective Market Making Bot.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


class WalletStatus(str, Enum):
    """Wallet status enumeration."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    DISABLED = "disabled"


class WalletConfig(BaseModel):
    """Wallet configuration model."""
    id: str
    name: str
    private_key: str
    enabled: bool = True
    max_orders_per_market: int = Field(default=5, ge=1, le=20)
    balance_threshold: float = Field(default=100.0, ge=0.1)


class WalletBalance(BaseModel):
    """Wallet balance model."""
    denom: str
    amount: float
    available: float
    locked: float = 0.0
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 8) if v is not None else None,
            datetime: lambda v: v.isoformat() if v else None
        }


class WalletData(BaseModel):
    """Wallet data model."""
    id: str
    name: str
    address: str
    status: WalletStatus = WalletStatus.ACTIVE
    balances: Dict[str, WalletBalance] = {}
    total_orders: int = 0
    active_orders: int = 0
    total_volume: float = 0.0
    last_activity: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 8) if v is not None else None,
            datetime: lambda v: v.isoformat() if v else None
        }


class WalletPerformance(BaseModel):
    """Wallet performance metrics."""
    wallet_id: str
    total_trades: int = 0
    total_volume: float = 0.0
    total_fees: float = 0.0
    pnl: float = 0.0
    win_rate: float = 0.0
    average_trade_size: float = 0.0
    last_trade_at: Optional[datetime] = None
    
    class Config:
        json_encoders = {
            float: lambda v: round(v, 8) if v is not None else None,
            datetime: lambda v: v.isoformat() if v else None
        }


class WalletDistributionConfig(BaseModel):
    """Wallet distribution configuration."""
    strategy: str = "round_robin"  # round_robin, weighted, random
    max_wallets_per_market: int = Field(default=3, ge=1, le=10)
    min_orders_per_wallet: int = Field(default=1, ge=1)
    wallet_weights: Optional[Dict[str, float]] = None  # For weighted distribution
