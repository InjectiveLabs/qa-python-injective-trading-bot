#!/usr/bin/env python3
"""
Derivative Position Closer
Closes open derivative positions by placing opposite market orders.

Usage:
    python scripts/position_closer.py --wallet wallet_1 --market INJ/USDT-PERP
    python scripts/position_closer.py --wallet all --market all
"""

import asyncio
import argparse
import json
import sys
import os
from decimal import Decimal
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.secure_wallet_loader import load_wallets_from_env
from pyinjective.async_client_v2 import AsyncClient
from pyinjective.indexer_client import IndexerClient
from pyinjective.core.network import Network
from pyinjective.core.broadcaster import MsgBroadcasterWithPk
from pyinjective import PrivateKey, Address
from pyinjective.composer import Composer


def log(message: str, wallet_id: str = "", market_id: str = ""):
    """Simple logging function"""
    timestamp = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0
    prefix = f"[{wallet_id}]" if wallet_id else ""
    market_suffix = f"[{market_id}]" if market_id else ""
    print(f"{prefix}{market_suffix} {message}")


class PositionCloser:
    """Close open derivative positions by placing opposite market orders"""
    
    def __init__(self, wallet_id: str, private_key: str):
        self.wallet_id = wallet_id
        self.private_key = private_key
        
        # Network setup
        self.network = Network.testnet()
        
        # Client connections
        self.async_client = AsyncClient(self.network)
        self.indexer_client = IndexerClient(self.network)
        self.composer = None  # Will be initialized in initialize()
        
        # Wallet setup
        private_key_obj = PrivateKey.from_hex(private_key)
        self.address = private_key_obj.to_public_key().to_address()
        
        # Broadcaster
        self.broadcaster = None
        
    async def initialize(self):
        """Initialize the position closer"""
        try:
            # Get account information
            await self.async_client.fetch_account(self.address.to_acc_bech32())
            self.sequence = self.async_client.sequence
            self.account_number = self.async_client.number
            
            # Initialize composer with market data
            self.composer = await self.async_client.composer()
            
            # Set up broadcaster with derivative-optimized settings
            gas_price = await self.async_client.current_chain_gas_price()
            gas_price = int(gas_price * 1.3)  # Higher gas price for market orders
            
            self.broadcaster = MsgBroadcasterWithPk.new_using_gas_heuristics(
                network=self.network,
                private_key=self.private_key,
                gas_price=gas_price
            )
            self.broadcaster.timeout_height_offset = 120
            
            log(f"✅ Position closer initialized for {self.wallet_id}: {self.address.to_acc_bech32()}", self.wallet_id)
            return True
            
        except Exception as e:
            log(f"❌ Failed to initialize position closer: {e}", self.wallet_id)
            return False
    
    async def get_open_positions(self, market_id: str) -> List[Dict]:
        """Get open derivative positions for a specific market"""
        try:
            subaccount_id = self.address.get_subaccount_id(0)
            
            positions_response = await self.indexer_client.fetch_derivative_positions_v2(
                subaccount_id=subaccount_id,
                market_ids=[market_id]
            )
            
            open_positions = []
            if positions_response and 'positions' in positions_response:
                for position in positions_response['positions']:
                    quantity = float(position.get('quantity', '0'))
                    if quantity != 0:  # Only include positions with non-zero quantity
                        open_positions.append(position)
            
            log(f"📊 Found {len(open_positions)} open positions", self.wallet_id)
            return open_positions
            
        except Exception as e:
            log(f"❌ Error getting open positions: {e}", self.wallet_id)
            return []
    
    async def close_position(self, position: Dict, market_id: str, market_symbol: str) -> bool:
        """Close a single position by placing opposite market order"""
        try:
            direction = position.get('direction', '')
            quantity = abs(float(position.get('quantity', '0')))
            
            if quantity == 0:
                log(f"⚠️ Position has zero quantity, skipping", self.wallet_id)
                return True
            
            # Determine opposite order type
            if direction.lower() == 'long':
                order_type = "SELL"  # Close long by selling
                log(f"🔄 Closing LONG position of {quantity} by SELLING", self.wallet_id)
            elif direction.lower() == 'short':
                order_type = "BUY"   # Close short by buying
                log(f"🔄 Closing SHORT position of {quantity} by BUYING", self.wallet_id)
            else:
                log(f"❌ Unknown position direction: {direction}", self.wallet_id)
                return False
            
            # Get current market price for margin calculation
            try:
                # Try to get market price from orderbook
                try:
                    orderbook = await self.indexer_client.fetch_derivative_orderbook_v2(market_id=market_id, depth=10)
                    if orderbook and 'orderbook' in orderbook:
                        buys = orderbook['orderbook'].get('buys', [])
                        sells = orderbook['orderbook'].get('sells', [])
                        
                        if buys and sells:
                            bid_price = float(buys[0]['price'])
                            ask_price = float(sells[0]['price'])
                            market_price = (bid_price + ask_price) / 2
                        elif buys:
                            market_price = float(buys[0]['price'])
                        elif sells:
                            market_price = float(sells[0]['price'])
                        else:
                            raise Exception("No orderbook data available")
                    else:
                        raise Exception("Failed to get orderbook data")
                except Exception as ob_error:
                    log(f"⚠️ Orderbook error: {ob_error}, trying mark price fallback", self.wallet_id)
                    # Fallback: use a reasonable price (e.g., $12.50 for INJ)
                    market_price = 12.50
                    log(f"📊 Using fallback price: ${market_price}", self.wallet_id)
                
            except Exception as e:
                log(f"❌ Error getting market price: {e}", self.wallet_id)
                return False
            
            # Calculate margin (use 10% of notional as safety margin)
            notional_value = market_price * quantity
            margin = Decimal(str(notional_value * 0.1))
            
            # Handle one-sided orderbook with aggressive limit order
            log(f"🎯 Using aggressive limit order for one-sided orderbook", self.wallet_id)
            
            # For one-sided orderbook, use very aggressive pricing
            if order_type == "BUY":
                # To close short, buy at a very high price to ensure execution
                # Use the highest existing bid or a reasonable maximum
                aggressive_price = Decimal(str(max(market_price * 2, 50.0)))  # At least $50 or 2x market
            else:
                # To close long, sell at a very low price to ensure execution  
                aggressive_price = Decimal(str(market_price * 0.5))  # 50% of market price
            
            log(f"💰 Using aggressive price: ${aggressive_price} (market: ${market_price})", self.wallet_id)
            
            # Create market order to close position using the dedicated market order message
            msg = self.composer.msg_create_derivative_market_order(
                sender=self.address.to_acc_bech32(),
                market_id=market_id,
                subaccount_id=self.address.get_subaccount_id(0),
                fee_recipient=self.address.to_acc_bech32(),
                quantity=Decimal(str(quantity)),
                price=aggressive_price,
                margin=margin,
                order_type=order_type,
                trigger_price=None
            )
            
            # Broadcast the closing order
            log(f"📡 Broadcasting {order_type} order to close position...", self.wallet_id)
            response = await self.broadcaster.broadcast([msg])
            
            # Check response - handle different response formats
            success = False
            tx_hash = None
            
            if response:
                # Handle dict response format
                if isinstance(response, dict) and 'txResponse' in response:
                    tx_resp = response['txResponse']
                    if tx_resp.get('code', -1) == 0:
                        success = True
                        tx_hash = tx_resp.get('txhash', 'unknown')
                # Handle object response format
                elif hasattr(response, 'tx_response') and response.tx_response:
                    if response.tx_response.code == 0:
                        success = True
                        tx_hash = response.tx_response.txhash
                # Handle direct txhash response
                elif hasattr(response, 'txhash'):
                    success = True
                    tx_hash = response.txhash
            
            if success:
                log(f"✅ Position closing order placed successfully", self.wallet_id)
                log(f"📝 Transaction: {tx_hash}", self.wallet_id)
                log(f"🔗 Explorer: https://testnet.explorer.injective.network/transaction/{tx_hash}", self.wallet_id)
                return True
            else:
                log(f"❌ Failed to place position closing order: {response}", self.wallet_id)
                return False
                
        except Exception as e:
            log(f"❌ Error closing position: {e}", self.wallet_id)
            # Add more detailed error information
            import traceback
            log(f"❌ Full error details: {traceback.format_exc()}", self.wallet_id)
            return False
    
    async def close_positions_for_market(self, market_id: str, market_symbol: str) -> bool:
        """Close all positions for a specific market"""
        try:
            log(f"🔍 Checking positions for {market_symbol}", self.wallet_id)
            
            positions = await self.get_open_positions(market_id)
            
            if not positions:
                log(f"ℹ️ No open positions found for {market_symbol}", self.wallet_id)
                return True
            
            closed_count = 0
            for i, position in enumerate(positions, 1):
                log(f"🎯 Closing position {i}/{len(positions)}", self.wallet_id)
                
                # Log position details
                direction = position.get('direction', 'unknown')
                quantity = position.get('quantity', '0')
                entry_price = position.get('entry_price', '0')
                unrealized_pnl = position.get('unrealized_pnl', '0')
                
                log(f"   Direction: {direction}", self.wallet_id)
                log(f"   Quantity: {quantity}", self.wallet_id)
                log(f"   Entry Price: ${float(entry_price):.4f}", self.wallet_id)
                log(f"   Unrealized PnL: ${float(unrealized_pnl):.4f}", self.wallet_id)
                
                success = await self.close_position(position, market_id, market_symbol)
                if success:
                    closed_count += 1
                    # Wait a moment for the order to process
                    await asyncio.sleep(3)
                else:
                    log(f"⚠️ Failed to close position {i}", self.wallet_id)
            
            log(f"📊 Successfully closed {closed_count}/{len(positions)} positions for {market_symbol}", self.wallet_id)
            return closed_count > 0
            
        except Exception as e:
            log(f"❌ Error closing positions for {market_symbol}: {e}", self.wallet_id)
            return False
    
    async def close_all_positions(self, markets_config: Dict) -> bool:
        """Close all positions for all derivative markets"""
        try:
            total_closed = 0
            total_markets = 0
            
            for market_symbol, market_config in markets_config['markets'].items():
                if market_config.get('type') == 'derivative' and market_config.get('enabled', False):
                    market_id = market_config.get('testnet_market_id', market_config.get('market_id'))
                    if market_id:
                        total_markets += 1
                        success = await self.close_positions_for_market(market_id, market_symbol)
                        if success:
                            total_closed += 1
                        
                        # Small delay between markets
                        await asyncio.sleep(2)
            
            log(f"📊 Position Closing Summary: {total_closed}/{total_markets} derivative markets processed", self.wallet_id)
            return total_closed > 0
            
        except Exception as e:
            log(f"❌ Error closing all positions: {e}", self.wallet_id)
            return False
    
    async def close(self):
        """Close connections"""
        try:
            pass  # AsyncClient doesn't have explicit close in this version
        except Exception as e:
            log(f"⚠️ Error closing connections: {e}", self.wallet_id)


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Derivative Position Closer')
    parser.add_argument('--wallet', required=True, help='Wallet ID to close positions for (wallet_1, wallet_2, wallet_3, or all)')
    parser.add_argument('--market', required=True, help='Market symbol to close positions for (INJ/USDT-PERP or all)')
    parser.add_argument('--config', default='config/markets_config.json', help='Path to markets config file')
    
    args = parser.parse_args()
    
    # Load markets configuration
    try:
        with open(args.config, 'r') as f:
            markets_config = json.load(f)
    except Exception as e:
        log(f"❌ Error loading markets config: {e}")
        return
    
    # Load wallets
    try:
        wallets = load_wallets_from_env()
    except Exception as e:
        log(f"❌ Error loading wallets: {e}")
        return
    
    # Extract wallet list from the loaded configuration
    wallet_list = wallets.get('wallets', [])
    wallet_map = {wallet['id']: wallet for wallet in wallet_list}
    
    if args.wallet == 'all':
        wallet_ids = [wallet['id'] for wallet in wallet_list if wallet['enabled']]
    else:
        if args.wallet not in wallet_map:
            available_wallets = [wallet['id'] for wallet in wallet_list]
            log(f"❌ Wallet {args.wallet} not found. Available wallets: {available_wallets}")
            return
        wallet_ids = [args.wallet]
    
    # Process each wallet
    for wallet_id in wallet_ids:
        if wallet_id not in wallet_map:
            log(f"⚠️ Wallet {wallet_id} not found, skipping")
            continue
        
        log(f"🚀 Starting position closing for {wallet_id}")
        
        # Initialize position closer
        closer = PositionCloser(
            wallet_id, 
            wallet_map[wallet_id]['private_key']
        )
        
        if not await closer.initialize():
            log(f"❌ Failed to initialize position closer for {wallet_id}")
            continue
        
        try:
            if args.market == 'all':
                # Close positions for all derivative markets
                success = await closer.close_all_positions(markets_config)
                if success:
                    log(f"✅ Successfully processed all derivative markets for {wallet_id}")
                else:
                    log(f"⚠️ No positions found or failed to close for {wallet_id}")
            else:
                # Close positions for specific market
                market_config = None
                for symbol, config in markets_config['markets'].items():
                    if symbol == args.market:
                        market_config = config
                        break
                
                if not market_config:
                    log(f"❌ Market {args.market} not found in config")
                    continue
                
                if market_config.get('type') != 'derivative':
                    log(f"❌ Market {args.market} is not a derivative market")
                    continue
                
                market_id = market_config.get('testnet_market_id', market_config.get('market_id'))
                if not market_id:
                    log(f"❌ No market ID found for {args.market}")
                    continue
                
                success = await closer.close_positions_for_market(market_id, args.market)
                if success:
                    log(f"✅ Successfully processed {args.market} for {wallet_id}")
                else:
                    log(f"⚠️ No positions found or failed to close for {wallet_id}")
        
        finally:
            await closer.close()
    
    log("🏁 Position closing process completed")


if __name__ == "__main__":
    asyncio.run(main())
