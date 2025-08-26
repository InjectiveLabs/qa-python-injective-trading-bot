"""
Settings configuration for the Injective Market Making Bot.
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Settings(BaseSettings):
    """Application settings."""
    
    # Injective Network Configuration
    cosmos_chain_id: str = Field(default="injective-888", env="COSMOS_CHAIN_ID")
    cosmos_grpc: str = Field(
        default="tcp://testnet.sentry.chain.grpc.injective.network:443",
        env="COSMOS_GRPC"
    )
    tendermint_rpc: str = Field(
        default="https://testnet.sentry.tm.injective.network:443",
        env="TENDERMINT_RPC"
    )
    exchange_grpc: str = Field(
        default="https://testnet.sentry.exchange.grpc.injective.network:443",
        env="EXCHANGE_GRPC"
    )
    
    # Wallet Configuration
    cosmos_private_key: str = Field(env="COSMOS_PRIVATE_KEY")
    
    # Gas Configuration
    gas_prices: str = Field(default="500000000inj", env="GAS_PRICES")
    
    # Logging
    log_level: str = Field(default="debug", env="LOG_LEVEL")
    
    # Configuration Files
    config_file: str = Field(default="markets_config.json", env="CONFIG_FILE")
    wallets_config_file: str = Field(default="wallets_config.json", env="WALLETS_CONFIG_FILE")
    
    # Server Configuration
    ui_port: int = Field(default=8080, env="UI_PORT")
    api_port: int = Field(default=8000, env="API_PORT")
    
    # Feature Flags
    price_monitoring_enabled: bool = Field(default=True, env="PRICE_MONITORING_ENABLED")
    default_deviation_threshold: float = Field(default=5.0, env="DEFAULT_DEVIATION_THRESHOLD")
    
    # Trading Configuration
    default_spread_percent: float = 0.5
    default_order_size: float = 10.0
    rebalance_interval: int = 30  # seconds
    price_update_interval: int = 10  # seconds
    price_monitoring_interval: int = 5  # seconds
    
    # Risk Management
    max_order_size: float = 1000.0
    max_total_exposure: float = 10000.0
    max_deviation_threshold: float = 20.0
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
