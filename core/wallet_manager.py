"""
Multi-wallet management for the Injective Market Making Bot.
"""

import asyncio
import json
from typing import Dict, List, Optional, Any
from pathlib import Path

from config.settings import settings
from core.client import injective_client
from models.wallet import WalletConfig, WalletData, WalletBalance, WalletStatus
from utils.logger import get_logger

logger = get_logger(__name__)

class WalletManager:
    """Manages multiple wallets for trading operations."""
    
    def __init__(self):
        self.wallets: Dict[str, WalletConfig] = {}
        self.wallet_data: Dict[str, WalletData] = {}
        self._initialized = False
        self._wallet_index = 0  # For round-robin distribution
    
    async def initialize(self) -> None:
        """Initialize the wallet manager."""
        try:
            # Load wallet configurations
            await self._load_wallet_configs()
            
            # Initialize wallet data
            await self._initialize_wallet_data()
            
            self._initialized = True
            logger.info(f"Wallet manager initialized with {len(self.wallets)} wallets")
            
        except Exception as e:
            logger.error(f"Failed to initialize wallet manager: {e}")
            raise
    
    async def _load_wallet_configs(self) -> None:
        """Load wallet configurations from JSON file."""
        try:
            config_path = Path(settings.wallets_config_file)
            if not config_path.exists():
                logger.warning(f"Wallet config file not found: {config_path}")
                return
            
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            wallets_config = config_data.get('wallets', [])
            
            for wallet_config in wallets_config:
                if wallet_config.get('enabled', False):
                    wallet_id = wallet_config['id']
                    self.wallets[wallet_id] = WalletConfig(
                        id=wallet_id,
                        name=wallet_config.get('name', f'Wallet {wallet_id}'),
                        private_key=wallet_config.get('private_key', ''),
                        enabled=wallet_config.get('enabled', False),
                        max_orders_per_market=wallet_config.get('max_orders_per_market', 5),
                        balance_threshold=wallet_config.get('balance_threshold', 100)
                    )
            
            logger.info(f"Loaded {len(self.wallets)} wallet configurations")
            
        except Exception as e:
            logger.error(f"Failed to load wallet configs: {e}")
            raise
    
    async def _initialize_wallet_data(self) -> None:
        """Initialize wallet data for configured wallets."""
        try:
            for wallet_id, config in self.wallets.items():
                if config.enabled and config.private_key:
                    try:
                        # Create wallet instance using the correct pattern
                        from pyinjective import PrivateKey, Address
                        private_key = PrivateKey.from_hex(config.private_key)
                        address = private_key.to_public_key().to_address()
                        
                        # Initialize sequence and account number (commented out due to 404 error)
                        # await address.async_init_num_seq(settings.tendermint_rpc)
                        
                        # Create wallet data
                        self.wallet_data[wallet_id] = WalletData(
                            id=wallet_id,
                            name=config.name,
                            address=address.to_acc_bech32(),
                            status=WalletStatus.ACTIVE,
                            balances={}
                        )
                        
                        logger.debug(f"Initialized wallet data for {wallet_id}")
                        
                    except Exception as e:
                        logger.error(f"Failed to initialize wallet {wallet_id}: {e}")
                        self.wallet_data[wallet_id] = WalletData(
                            id=wallet_id,
                            name=config.name,
                            address="",
                            status=WalletStatus.ERROR,
                            balances={}
                        )
            
        except Exception as e:
            logger.error(f"Failed to initialize wallet data: {e}")
            raise
    
    async def get_enabled_wallets(self) -> Dict[str, WalletConfig]:
        """Get all enabled wallets."""
        return {k: v for k, v in self.wallets.items() if v.enabled}
    
    async def get_wallet_config(self, wallet_id: str) -> Optional[WalletConfig]:
        """Get wallet configuration for a specific wallet."""
        return self.wallets.get(wallet_id)
    
    async def get_wallet_data(self, wallet_id: str) -> Optional[WalletData]:
        """Get wallet data for a specific wallet."""
        return self.wallet_data.get(wallet_id)
    
    async def get_wallet_balance(self, wallet_id: str, denom: str = "inj") -> Optional[float]:
        """Get wallet balance for a specific token."""
        try:
            wallet_data = await self.get_wallet_data(wallet_id)
            if not wallet_data:
                return None
            
            balance = await injective_client.get_account_balance(wallet_data.address)
            
            if balance and 'balances' in balance:
                for bal in balance['balances']:
                    if bal['denom'] == denom:
                        amount = float(bal['amount'])
                        # Convert from wei for INJ
                        if denom == "inj":
                            amount = amount / 1e18
                        return amount
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Failed to get wallet balance for {wallet_id}: {e}")
            return None
    
    async def get_subaccount_balance(self, wallet_id: str, subaccount_id: str, denom: str = "inj") -> Optional[float]:
        """Get subaccount balance for a specific token."""
        try:
            balance = await injective_client.get_subaccount_balances(subaccount_id)
            
            if balance and 'balances' in balance:
                for bal in balance['balances']:
                    if bal['denom'] == denom:
                        amount = float(bal['available'])
                        # Convert from wei for INJ
                        if denom == "inj":
                            amount = amount / 1e18
                        return amount
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Failed to get subaccount balance for {subaccount_id}: {e}")
            return None
    
    async def update_wallet_balances(self, wallet_id: str) -> None:
        """Update balances for a specific wallet."""
        try:
            wallet_data = await self.get_wallet_data(wallet_id)
            if not wallet_data:
                return
            
            # Update main account balance
            balance = await injective_client.get_account_balance(wallet_data.address)
            if balance and 'balances' in balance:
                for bal in balance['balances']:
                    denom = bal['denom']
                    amount = float(bal['amount'])
                    
                    # Convert from wei for INJ
                    if denom == "inj":
                        amount = amount / 1e18
                    
                    wallet_data.balances[denom] = WalletBalance(
                        denom=denom,
                        amount=amount,
                        available=amount
                    )
            
            logger.debug(f"Updated balances for wallet {wallet_id}")
            
        except Exception as e:
            logger.error(f"Failed to update wallet balances for {wallet_id}: {e}")
    
    async def update_all_balances(self) -> None:
        """Update balances for all enabled wallets."""
        try:
            for wallet_id in self.wallets.keys():
                if self.wallets[wallet_id].enabled:
                    await self.update_wallet_balances(wallet_id)
            
            logger.debug("Updated balances for all wallets")
            
        except Exception as e:
            logger.error(f"Failed to update all wallet balances: {e}")
    
    async def get_wallet_orders(self, wallet_id: str, market_id: str) -> Dict[str, Any]:
        """Get orders for a specific wallet and market."""
        try:
            wallet_data = await self.get_wallet_data(wallet_id)
            if not wallet_data:
                return {}
            
            # Get orders from Injective
            subaccount_id = wallet_data.address + "0"  # Simple subaccount ID
            orders = await injective_client.get_spot_orders(market_id, subaccount_id)
            
            return orders or {}
            
        except Exception as e:
            logger.error(f"Failed to get wallet orders: {e}")
            return {}
    
    def get_wallet_for_market(self, market_id: str) -> Optional[str]:
        """Get the best available wallet for a market using round-robin distribution."""
        try:
            # Get all enabled wallets
            enabled_wallets = [
                wallet_id for wallet_id, config in self.wallets.items() 
                if config.enabled
            ]
            
            if not enabled_wallets:
                logger.warning("No enabled wallets available")
                return None
            
            # Round-robin distribution - cycle through wallets
            selected_wallet = enabled_wallets[self._wallet_index % len(enabled_wallets)]
            self._wallet_index += 1
            
            logger.debug(f"Selected wallet {selected_wallet} for market {market_id} (round-robin #{self._wallet_index})")
            return selected_wallet
            
        except Exception as e:
            logger.error(f"Failed to get wallet for market: {e}")
            return None
    
    def can_place_order(self, wallet_id: str, market_id: str) -> bool:
        """Check if a wallet can place an order for a market."""
        try:
            # Check if wallet exists and is enabled
            if wallet_id not in self.wallets:
                return False
            
            wallet_config = self.wallets[wallet_id]
            if not wallet_config.enabled:
                return False
            
            # Check order count (simplified)
            # In the future, this could check actual order counts
            return True
            
        except Exception as e:
            logger.error(f"Failed to check if wallet can place order: {e}")
            return False
    
    def get_wallet_client(self, wallet_id: str):
        """Get the wallet client for trading operations."""
        try:
            # For now, return the main injective client
            # In the future, this could return wallet-specific clients
            return injective_client
            
        except Exception as e:
            logger.error(f"Failed to get wallet client: {e}")
            return None
    
    def update_order_count(self, wallet_id: str, count: int) -> None:
        """Update the order count for a wallet."""
        try:
            # For now, just log the update
            # In the future, this could track actual order counts
            logger.debug(f"Updated order count for wallet {wallet_id}: +{count}")
            
        except Exception as e:
            logger.error(f"Failed to update order count: {e}")
    
    def is_initialized(self) -> bool:
        """Check if wallet manager is initialized."""
        return self._initialized

# Global wallet manager instance
wallet_manager = WalletManager()
