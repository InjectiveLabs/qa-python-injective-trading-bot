"""
Injective client setup and management for the Market Making Bot.
"""

import asyncio
from typing import Optional, Dict, Any
from decimal import Decimal

from pyinjective.async_client_v2 import AsyncClient
from pyinjective.indexer_client import IndexerClient
from pyinjective.core.network import Network
from pyinjective.core.broadcaster import MsgBroadcasterWithPk
from pyinjective import PrivateKey, Address
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

class InjectiveClient:
    """Wrapper for Injective Python SDK V2 with proper client separation."""
    
    def __init__(self):
        self.network: Optional[Network] = None
        self.async_client: Optional[AsyncClient] = None
        self.indexer_client: Optional[IndexerClient] = None
        self.composer = None
        self.message_broadcaster: Optional[MsgBroadcasterWithPk] = None
        self.private_key: Optional[PrivateKey] = None
        self.address: Optional[Address] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize both IndexerClient and AsyncClient with network and wallet."""
        try:
            # Create network configuration
            self.network = Network.testnet()
            
            # Initialize IndexerClient for market data queries
            self.indexer_client = IndexerClient(self.network)
            
            # Initialize AsyncClient for trading operations
            self.async_client = AsyncClient(self.network)
            self.composer = await self.async_client.composer()
            
            # Initialize wallet
            if settings.cosmos_private_key:
                self.private_key = PrivateKey.from_hex(settings.cosmos_private_key)
                self.address = self.private_key.to_public_key().to_address()
                
                # Initialize sequence and account number (commented out due to 404 error)
                # await self.address.async_init_num_seq(settings.tendermint_rpc)
                
                # Initialize message broadcaster
                gas_price = await self.async_client.current_chain_gas_price()
                gas_price = int(gas_price * 1.1)  # Add 10% buffer
                
                self.message_broadcaster = MsgBroadcasterWithPk.new_using_simulation(
                    network=self.network,
                    private_key=settings.cosmos_private_key,
                    gas_price=gas_price,
                    client=self.async_client,
                    composer=self.composer,
                )
                
                logger.info(f"Wallet initialized: {self.address.to_acc_bech32()}")
            
            self._initialized = True
            logger.info("Injective V2 clients initialized successfully with human-readable format")
            
        except Exception as e:
            logger.error(f"Failed to initialize Injective V2 clients: {e}")
            raise
    
    async def close(self) -> None:
        """Close the client connections."""
        if self.async_client:
            await self.async_client.close_chain_channel()
            await self.async_client.close_chain_stream_channel()
            logger.info("Injective V2 client connections closed")
    
    def is_initialized(self) -> bool:
        """Check if the client is initialized."""
        return self._initialized
    
    # Market Data Methods (using IndexerClient)
    
    async def get_spot_markets(self) -> Dict[str, Any]:
        """Get all spot markets using IndexerClient."""
        if not self.indexer_client:
            raise RuntimeError("IndexerClient not initialized")
        return await self.indexer_client.fetch_spot_markets()
    
    async def get_derivative_markets(self) -> Dict[str, Any]:
        """Get all derivative markets using IndexerClient."""
        if not self.indexer_client:
            raise RuntimeError("IndexerClient not initialized")
        return await self.indexer_client.fetch_derivative_markets()
    
    async def get_spot_orderbook(self, market_id: str, depth: int = 10) -> Dict[str, Any]:
        """Get spot orderbook using IndexerClient."""
        if not self.indexer_client:
            raise RuntimeError("IndexerClient not initialized")
        return await self.indexer_client.fetch_spot_orderbook_v2(market_id=market_id, depth=depth)
    
    async def get_derivative_orderbook(self, market_id: str, depth: int = 10) -> Dict[str, Any]:
        """Get derivative orderbook using IndexerClient."""
        if not self.indexer_client:
            raise RuntimeError("IndexerClient not initialized")
        return await self.indexer_client.fetch_derivative_orderbook_v2(market_id=market_id, depth=depth)
    
    async def get_spot_trades(self, market_id: str, **kwargs) -> Dict[str, Any]:
        """Get spot trades using IndexerClient."""
        if not self.indexer_client:
            raise RuntimeError("IndexerClient not initialized")
        return await self.indexer_client.fetch_spot_trades(market_ids=[market_id], **kwargs)
    
    async def get_derivative_trades(self, market_id: str, **kwargs) -> Dict[str, Any]:
        """Get derivative trades using IndexerClient."""
        if not self.indexer_client:
            raise RuntimeError("IndexerClient not initialized")
        return await self.indexer_client.fetch_derivative_trades(market_ids=[market_id], **kwargs)
    
    # Account and Balance Methods (using AsyncClient)
    
    async def get_account_balance(self, address: str) -> Dict[str, Any]:
        """Get account balance using AsyncClient."""
        if not self.async_client:
            raise RuntimeError("AsyncClient not initialized")
        return await self.async_client.fetch_bank_balances(address=address)
    
    async def get_subaccount_balances(self, subaccount_id: str) -> Dict[str, Any]:
        """Get subaccount balances using AsyncClient."""
        if not self.async_client:
            raise RuntimeError("AsyncClient not initialized")
        return await self.async_client.fetch_subaccount_balances_list(subaccount_id=subaccount_id)
    
    async def get_spot_orders(self, market_id: str, subaccount_id: str) -> Dict[str, Any]:
        """Get spot orders using AsyncClient."""
        if not self.async_client:
            raise RuntimeError("AsyncClient not initialized")
        return await self.async_client.fetch_spot_orders(
            market_ids=[market_id],
            subaccount_id=subaccount_id
        )
    
    async def get_derivative_orders(self, market_id: str, subaccount_id: str) -> Dict[str, Any]:
        """Get derivative orders using AsyncClient."""
        if not self.async_client:
            raise RuntimeError("AsyncClient not initialized")
        return await self.async_client.fetch_derivative_orders(
            market_ids=[market_id],
            subaccount_id=subaccount_id
        )
    
    # Trading Methods (using AsyncClient + Composer)
    
    async def create_spot_limit_order(
        self, 
        market_id: str, 
        subaccount_id: str, 
        price: Decimal, 
        quantity: Decimal, 
        order_type: str, 
        cid: str
    ) -> Dict[str, Any]:
        """Create a spot limit order."""
        if not self.composer or not self.message_broadcaster or not self.address:
            raise RuntimeError("Trading components not initialized")
        
        fee_recipient = "inj1hkhdaj2a2clmq5jq6mspsggqs32vynpk228q3r"
        
        msg = self.composer.msg_create_spot_limit_order(
            sender=self.address.to_acc_bech32(),
            market_id=market_id,
            subaccount_id=subaccount_id,
            fee_recipient=fee_recipient,
            price=price,
            quantity=quantity,
            order_type=order_type,
            cid=cid
        )
        
        result = await self.message_broadcaster.broadcast([msg])
        return result
    
    async def create_derivative_limit_order(
        self, 
        market_id: str, 
        subaccount_id: str, 
        price: Decimal, 
        quantity: Decimal, 
        margin: Decimal, 
        order_type: str, 
        cid: str
    ) -> Dict[str, Any]:
        """Create a derivative limit order."""
        if not self.composer or not self.message_broadcaster or not self.address:
            raise RuntimeError("Trading components not initialized")
        
        fee_recipient = "inj1hkhdaj2a2clmq5jq6mspsggqs32vynpk228q3r"
        
        msg = self.composer.msg_create_derivative_limit_order(
            sender=self.address.to_acc_bech32(),
            market_id=market_id,
            subaccount_id=subaccount_id,
            fee_recipient=fee_recipient,
            price=price,
            quantity=quantity,
            margin=margin,
            order_type=order_type,
            cid=cid
        )
        
        result = await self.message_broadcaster.broadcast([msg])
        return result
    
    async def cancel_spot_order(
        self, 
        market_id: str, 
        subaccount_id: str, 
        order_hash: str = None, 
        cid: str = None
    ) -> Dict[str, Any]:
        """Cancel a spot order."""
        if not self.composer or not self.message_broadcaster or not self.address:
            raise RuntimeError("Trading components not initialized")
        
        msg = self.composer.msg_cancel_spot_order(
            sender=self.address.to_acc_bech32(),
            market_id=market_id,
            subaccount_id=subaccount_id,
            order_hash=order_hash,
            cid=cid
        )
        
        result = await self.message_broadcaster.broadcast([msg])
        return result
    
    async def cancel_derivative_order(
        self, 
        market_id: str, 
        subaccount_id: str, 
        order_hash: str = None, 
        cid: str = None
    ) -> Dict[str, Any]:
        """Cancel a derivative order."""
        if not self.composer or not self.message_broadcaster or not self.address:
            raise RuntimeError("Trading components not initialized")
        
        msg = self.composer.msg_cancel_derivative_order(
            sender=self.address.to_acc_bech32(),
            market_id=market_id,
            subaccount_id=subaccount_id,
            order_hash=order_hash,
            cid=cid
        )
        
        result = await self.message_broadcaster.broadcast([msg])
        return result
    
    # Utility Methods
    
    def get_subaccount_id(self, index: int = 0) -> str:
        """Get subaccount ID for the wallet."""
        if not self.address:
            raise RuntimeError("Wallet not initialized")
        return self.address.get_subaccount_id(index=index)
    
    def get_wallet_address(self) -> str:
        """Get wallet address."""
        if not self.address:
            raise RuntimeError("Wallet not initialized")
        return self.address.to_acc_bech32()

# Global client instance
injective_client = InjectiveClient()
