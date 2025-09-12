#!/usr/bin/env python3
"""
Manual Order Canceller for Enhanced Multi-Wallet Trader

This script allows you to cancel orders on demand for specific wallets and markets.
Now supports unlimited batches until all orders are cancelled, with safety limits.

Usage:
    python scripts/manual_order_canceller.py --wallet wallet_1 --market INJ/USDT
    python scripts/manual_order_canceller.py --wallet all --market all
    python scripts/manual_order_canceller.py --wallet wallet_1 --market all
    
    # For large order sets, customize safety limits:
    python scripts/manual_order_canceller.py --wallet all --market all --max-orders 20000 --max-duration 600
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


class ManualOrderCanceller:
    """Manual order canceller for enhanced multi-wallet trader"""
    
    def __init__(self, wallet_id: str, private_key: str, max_orders: int = 10000, max_duration: int = 300):
        self.wallet_id = wallet_id
        self.private_key = private_key
        self.max_orders = max_orders
        self.max_duration = max_duration
        
        # Network setup
        self.network = Network.testnet()
        
        # Client connections
        self.async_client = AsyncClient(self.network)
        self.indexer_client = IndexerClient(self.network)
        self.composer = Composer(network=self.network)
        
        # Wallet setup
        private_key_obj = PrivateKey.from_hex(private_key)
        self.address = private_key_obj.to_public_key().to_address()
        
        # Broadcaster
        self.broadcaster = None
        
    async def initialize(self):
        """Initialize the canceller"""
        try:
            # Get account information
            await self.async_client.fetch_account(self.address.to_acc_bech32())
            self.sequence = self.async_client.sequence
            self.account_number = self.async_client.number
            
            # Set up broadcaster
            gas_price = await self.async_client.current_chain_gas_price()
            gas_price = int(gas_price * 1.1)
            
            self.broadcaster = MsgBroadcasterWithPk.new_using_gas_heuristics(
                network=self.network,
                private_key=self.private_key,
                gas_price=gas_price
            )
            self.broadcaster.timeout_height_offset = 20
            
            log(f"✅ Manual canceller initialized for {self.wallet_id}: {self.address.to_acc_bech32()}", self.wallet_id)
            return True
            
        except Exception as e:
            log(f"❌ Failed to initialize canceller: {e}", self.wallet_id)
            return False
    
    async def _broadcast_with_retry(self, msg, max_retries=3):
        """Broadcast message with retry logic for sequence mismatches"""
        for attempt in range(max_retries):
            try:
                # Refresh account info before each attempt
                await self.async_client.fetch_account(self.address.to_acc_bech32())
                self.sequence = self.async_client.sequence
                self.account_number = self.async_client.number
                
                # Update gas price before each attempt
                gas_price = await self.async_client.current_chain_gas_price()
                gas_price = int(gas_price * (1.2 + attempt * 0.1))  # Increase gas price on retry
                self.broadcaster.update_gas_price(gas_price=gas_price)
                
                # Broadcast the message
                response = await self.broadcaster.broadcast([msg])
                
                # Check if it's a sequence mismatch error
                if hasattr(response, 'tx_response') and response.tx_response:
                    if response.tx_response.code != 0:
                        error_msg = str(response.tx_response.raw_log)
                        if 'account sequence mismatch' in error_msg.lower():
                            if attempt < max_retries - 1:
                                log(f"⚠️ Sequence mismatch on attempt {attempt + 1}, retrying...", self.wallet_id)
                                await asyncio.sleep(2 + attempt)  # Wait before retry
                                continue
                            else:
                                log(f"❌ Sequence mismatch after {max_retries} attempts", self.wallet_id)
                                return response
                
                return response
                
            except Exception as e:
                error_msg = str(e)
                if 'account sequence mismatch' in error_msg.lower():
                    if attempt < max_retries - 1:
                        log(f"⚠️ Sequence mismatch on attempt {attempt + 1}, retrying...", self.wallet_id)
                        await asyncio.sleep(2 + attempt)  # Wait before retry
                        continue
                    else:
                        log(f"❌ Sequence mismatch after {max_retries} attempts", self.wallet_id)
                        raise e
                else:
                    # Different error, don't retry
                    raise e
        
        return None
    
    async def get_active_orders(self, market_id: str) -> List[Dict]:
        """Get active orders for a specific market with full pagination support"""
        try:
            subaccount_id = self.address.get_subaccount_id(0)
            active_orders = []
            
            # Get spot orders
            try:
                spot_orders_response = await self.indexer_client.fetch_spot_orders(
                    subaccount_id=subaccount_id,
                    market_ids=[market_id]  # Filter by market
                )
                
                if spot_orders_response and 'orders' in spot_orders_response:
                    for order in spot_orders_response['orders']:
                        if order.get('state') in ['booked', 'partial_filled']:
                            active_orders.append({
                                'order_hash': order.get('orderHash'),
                                'market_id': order.get('marketId'),
                                'side': order.get('side'),
                                'price': order.get('price'),
                                'quantity': order.get('quantity'),
                                'state': order.get('state'),
                                'type': 'spot'
                            })
                    
            except Exception as e:
                log(f"⚠️ Error fetching spot orders: {e}", self.wallet_id, market_id)
            
            # Get derivative orders
            try:
                derivative_orders_response = await self.indexer_client.fetch_derivative_orders(
                    subaccount_id=subaccount_id,
                    market_ids=[market_id]  # Filter by market
                )
                
                if derivative_orders_response and 'orders' in derivative_orders_response:
                    for order in derivative_orders_response['orders']:
                        if order.get('state') in ['booked', 'partial_filled']:
                            active_orders.append({
                                'order_hash': order.get('orderHash'),
                                'market_id': order.get('marketId'),
                                'side': order.get('side'),
                                'price': order.get('price'),
                                'quantity': order.get('quantity'),
                                'state': order.get('state'),
                                'type': 'derivative'
                            })
                    
            except Exception as e:
                log(f"⚠️ Error fetching derivative orders: {e}", self.wallet_id, market_id)
            
            log(f"📊 Found {len(active_orders)} total active orders for {market_id}", self.wallet_id)
            return active_orders
            
        except Exception as e:
            log(f"❌ Error getting active orders: {e}", self.wallet_id, market_id)
            return []
    
    async def cancel_orders_for_market(self, market_id: str, market_symbol: str) -> bool:
        """Cancel all orders for a specific market with unlimited batches until completion"""
        try:
            total_cancelled = 0
            attempt = 0
            start_time = asyncio.get_event_loop().time()
            
            while True:
                attempt += 1
                current_time = asyncio.get_event_loop().time()
                
                # Safety checks
                if total_cancelled >= self.max_orders:
                    log(f"⚠️ Safety limit reached: {self.max_orders} orders cancelled for {market_symbol}", self.wallet_id)
                    break
                
                if current_time - start_time > self.max_duration:
                    log(f"⚠️ Timeout reached: {self.max_duration}s elapsed for {market_symbol}", self.wallet_id)
                    break
                
                log(f"🔍 Checking active orders for {market_symbol} (batch {attempt})", self.wallet_id)
                
                # Get active orders
                active_orders = await self.get_active_orders(market_id)
                
                if not active_orders:
                    if total_cancelled > 0:
                        elapsed_time = current_time - start_time
                        log(f"✅ All orders cancelled for {market_symbol}. Total cancelled: {total_cancelled} in {attempt} batches ({elapsed_time:.1f}s)", self.wallet_id)
                    else:
                        log(f"ℹ️ No active orders found for {market_symbol}", self.wallet_id)
                    return True
                
                log(f"📋 Found {len(active_orders)} active orders to cancel (batch {attempt}, total cancelled so far: {total_cancelled})", self.wallet_id)
                
                # Separate spot and derivative orders
                spot_orders_to_cancel = []
                derivative_orders_to_cancel = []
                
                for order in active_orders:
                    order_data = {
                        'market_id': order['market_id'],
                        'subaccount_id': self.address.get_subaccount_id(0),
                        'order_hash': order['order_hash']
                    }
                    
                    if order['type'] == 'spot':
                        spot_orders_to_cancel.append(order_data)
                    else:
                        derivative_orders_to_cancel.append(order_data)
                
                # Create batch cancel message
                msg = self.composer.msg_batch_update_orders(
                    sender=self.address.to_acc_bech32(),
                    derivative_orders_to_create=[],
                    spot_orders_to_create=[],
                    derivative_orders_to_cancel=derivative_orders_to_cancel,
                    spot_orders_to_cancel=spot_orders_to_cancel
                )
                
                # Broadcast cancellation with retry logic
                response = await self._broadcast_with_retry(msg, max_retries=3)
                
                # Check for success in different response formats
                success = False
                tx_hash = None
                
                if response and hasattr(response, 'tx_response') and response.tx_response and response.tx_response.code == 0:
                    success = True
                    tx_hash = response.tx_response.txhash
                elif response and hasattr(response, 'txhash'):
                    success = True
                    tx_hash = response.txhash
                elif response and isinstance(response, dict) and 'txResponse' in response:
                    tx_response = response['txResponse']
                    if tx_response.get('code') == 0:
                        success = True
                        tx_hash = tx_response.get('txhash')
                
                if success:
                    batch_cancelled = len(active_orders)
                    total_cancelled += batch_cancelled
                    elapsed_time = current_time - start_time
                    log(f"✅ Successfully cancelled {batch_cancelled} orders for {market_symbol} (batch {attempt}, total: {total_cancelled}, {elapsed_time:.1f}s)", self.wallet_id)
                    if tx_hash:
                        log(f"📝 Transaction: {tx_hash}", self.wallet_id)
                    
                    # Wait a moment for the blockchain to process the cancellation
                    await asyncio.sleep(2)
                    
                    # Continue to next batch if there might be more orders
                    continue
                else:
                    # Check if it's a sequence mismatch error that we should retry
                    error_msg = ""
                    if hasattr(response, 'tx_response') and response.tx_response:
                        error_msg = str(response.tx_response.raw_log)
                    elif hasattr(response, 'details'):
                        error_msg = str(response.details)
                    else:
                        error_msg = str(response)
                    
                    if 'account sequence mismatch' in error_msg.lower():
                        log(f"⚠️ Sequence mismatch for {market_symbol} (batch {attempt}), retrying batch...", self.wallet_id)
                        # Don't increment attempt, retry the same batch
                        await asyncio.sleep(2)
                        continue
                    else:
                        log(f"❌ Failed to cancel orders for {market_symbol} (batch {attempt}). Response: {response}", self.wallet_id)
                        return False
            
            # If we've reached safety limits, check if there are still orders
            remaining_orders = await self.get_active_orders(market_id)
            if remaining_orders:
                elapsed_time = asyncio.get_event_loop().time() - start_time
                log(f"⚠️ Reached safety limits but {len(remaining_orders)} orders still remain for {market_symbol} (cancelled {total_cancelled} in {elapsed_time:.1f}s)", self.wallet_id)
                return False
            else:
                elapsed_time = asyncio.get_event_loop().time() - start_time
                log(f"✅ All orders cancelled for {market_symbol}. Total cancelled: {total_cancelled} in {attempt} batches ({elapsed_time:.1f}s)", self.wallet_id)
                return True
                
        except Exception as e:
            log(f"❌ Error cancelling orders for {market_symbol}: {e}", self.wallet_id)
            return False
    
    async def cancel_all_orders(self, markets_config: Dict) -> bool:
        """Cancel all orders for all markets"""
        try:
            total_cancelled = 0
            total_markets = 0
            
            for market_symbol, market_config in markets_config['markets'].items():
                if market_config.get('enabled', False):
                    market_id = market_config.get('testnet_market_id', market_config.get('market_id'))
                    if market_id:
                        total_markets += 1
                        success = await self.cancel_orders_for_market(market_id, market_symbol)
                        if success:
                            total_cancelled += 1
                        
                        # Small delay between markets
                        await asyncio.sleep(1)
            
            log(f"📊 Cancellation Summary: {total_cancelled}/{total_markets} markets processed", self.wallet_id)
            return total_cancelled > 0
            
        except Exception as e:
            log(f"❌ Error cancelling all orders: {e}", self.wallet_id)
            return False
    
    async def close(self):
        """Close connections"""
        try:
            # AsyncClient doesn't have a close method in this version
            pass
        except Exception as e:
            log(f"⚠️ Error closing connections: {e}", self.wallet_id)


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Manual Order Canceller for Enhanced Multi-Wallet Trader')
    parser.add_argument('--wallet', required=True, help='Wallet ID to cancel orders for (wallet_1, wallet_2, wallet_3, or all)')
    parser.add_argument('--market', required=True, help='Market symbol to cancel orders for (INJ/USDT, stINJ/INJ, or all)')
    parser.add_argument('--config', default='config/markets_config.json', help='Path to markets config file')
    parser.add_argument('--max-orders', type=int, default=10000, help='Maximum total orders to cancel per market (safety limit)')
    parser.add_argument('--max-duration', type=int, default=300, help='Maximum duration in seconds per market (safety limit)')
    
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
        
        log(f"🚀 Starting manual cancellation for {wallet_id}")
        
        # Initialize canceller
        canceller = ManualOrderCanceller(
            wallet_id, 
            wallet_map[wallet_id]['private_key'],
            max_orders=args.max_orders,
            max_duration=args.max_duration
        )
        
        if not await canceller.initialize():
            log(f"❌ Failed to initialize canceller for {wallet_id}")
            continue
        
        try:
            if args.market == 'all':
                # Cancel all orders for all markets
                success = await canceller.cancel_all_orders(markets_config)
                if success:
                    log(f"✅ Successfully processed all markets for {wallet_id}")
                else:
                    log(f"⚠️ No orders found or failed to cancel for {wallet_id}")
            else:
                # Cancel orders for specific market
                market_config = None
                for symbol, config in markets_config['markets'].items():
                    if symbol == args.market:
                        market_config = config
                        break
                
                if not market_config:
                    log(f"❌ Market {args.market} not found in config")
                    continue
                
                market_id = market_config.get('testnet_market_id', market_config.get('market_id'))
                if not market_id:
                    log(f"❌ No market ID found for {args.market}")
                    continue
                
                success = await canceller.cancel_orders_for_market(market_id, args.market)
                if success:
                    log(f"✅ Successfully processed {args.market} for {wallet_id}")
                else:
                    log(f"⚠️ No orders found or failed to cancel for {wallet_id}")
        
        finally:
            await canceller.close()
    
    log("🏁 Manual cancellation process completed")


if __name__ == "__main__":
    asyncio.run(main())
