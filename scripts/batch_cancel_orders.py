#!/usr/bin/env python3
"""
Batch cancel all orders using Injective's batch cancel functionality.
"""

import asyncio
import json
import os
import sys
from pyinjective.async_client_v2 import AsyncClient
from pyinjective.indexer_client import IndexerClient
from pyinjective.core.network import Network
from pyinjective.core.broadcaster import MsgBroadcasterWithPk
from pyinjective import PrivateKey

# Add parent directory to path to import from utils
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import the secure wallet loader
from utils.secure_wallet_loader import load_wallets_from_env

async def batch_cancel_all_orders():
    print("🚨 Batch Cancel All Orders")
    print("=" * 40)
    
    try:
        # Load wallet configs securely from environment variables
        print("🔒 Loading wallet configuration from environment variables...")
        wallets_config = load_wallets_from_env()
        
        # Load market configs
        print("📁 Loading market configuration...")
        with open('config/markets_config.json', 'r') as f:
            markets_config = json.load(f)
        
        # Initialize network
        network = Network.testnet()
        
        # Initialize indexer client for fetching orders
        indexer_client = IndexerClient(network)
        
        total_cancelled = 0
        
        print(f"📋 Found {len(wallets_config['wallets'])} enabled wallets")
        for wallet in wallets_config['wallets']:
            print(f"   - {wallet['name']}: {wallet['id']} ({'enabled' if wallet['enabled'] else 'disabled'})")
        
        print(f"\n📊 Found {len([m for m in markets_config['markets'].values() if m.get('enabled', False)])} enabled markets")
        
        # Process each wallet
        for wallet_config in wallets_config['wallets']:
            if not wallet_config.get('enabled', False):
                continue
                
            wallet_id = wallet_config['id']
            private_key = wallet_config['private_key']
            
            print(f"\n📝 Processing wallet: {wallet_id}")
            
            try:
                # Initialize client for this wallet
                client = AsyncClient(network)
                composer = await client.composer()
                
                # Initialize wallet
                pk = PrivateKey.from_hex(private_key)
                address = pk.to_public_key().to_address()
                
                # Initialize broadcaster with gas heuristics for better gas estimation
                gas_price = await client.current_chain_gas_price()
                gas_price = int(gas_price * 1.1)
                
                broadcaster = MsgBroadcasterWithPk.new_using_gas_heuristics(
                    network=network,
                    private_key=private_key,
                    gas_price=gas_price,
                    client=client,
                    composer=composer,
                )
                
                print(f"   ✅ Wallet initialized: {address.to_acc_bech32()}")
                
                # Collect all orders to cancel
                all_spot_orders_data = []
                all_derivative_orders_data = []
                
                # Process each market
                for market_id, market_config in markets_config['markets'].items():
                    if not market_config.get('enabled', False):
                        continue
                        
                    print(f"   📊 Processing market: {market_id}")
                    
                    try:
                        # Get orders using indexer client
                        subaccount_id = address.get_subaccount_id(0)
                        
                        # Use testnet_market_id for order cancellation (we're on testnet)
                        testnet_market_id = market_config.get('testnet_market_id')
                        if not testnet_market_id:
                            print(f"      ⚠️  No testnet_market_id found for {market_id}")
                            continue
                        
                        if market_config.get('type') == 'spot':
                            orders = await indexer_client.fetch_spot_orders(
                                market_ids=[testnet_market_id],
                                subaccount_id=subaccount_id
                            )
                        else:
                            orders = await indexer_client.fetch_derivative_orders(
                                market_ids=[testnet_market_id],
                                subaccount_id=subaccount_id
                            )
                        
                        if orders and 'orders' in orders and orders['orders']:
                            print(f"      📊 Found {len(orders['orders'])} orders to cancel")
                            print(f"      📋 Raw orders response: {orders}")
                            
                            for order in orders['orders']:
                                print(f"         📝 Processing order: {order}")
                                order_hash = order.get('orderHash')
                                order_state = order.get('state', 'unknown')
                                print(f"            Order hash: {order_hash}")
                                print(f"            Order state: {order_state}")
                                
                                if order_hash and order_state == 'booked':
                                    # Create OrderData for batch cancel
                                    order_data = composer.order_data_without_mask(
                                        market_id=testnet_market_id,
                                        subaccount_id=subaccount_id,
                                        order_hash=order_hash
                                    )
                                    
                                    if market_config.get('type') == 'spot':
                                        all_spot_orders_data.append(order_data)
                                        print(f"            ✅ Added to spot batch cancel")
                                    else:
                                        all_derivative_orders_data.append(order_data)
                                        print(f"            ✅ Added to derivative batch cancel")
                                else:
                                    print(f"            ⚠️  Skipping order (hash: {order_hash}, state: {order_state})")
                        else:
                            print(f"      ✅ No orders found for {market_id}")
                            print(f"      📋 Orders response: {orders}")
                            
                    except Exception as e:
                        print(f"      ❌ Error processing market {market_id}: {e}")
                
                # Batch cancel spot orders
                if all_spot_orders_data:
                    print(f"   🚨 Batch cancelling {len(all_spot_orders_data)} spot orders...")
                    try:
                        batch_cancel_msg = composer.msg_batch_cancel_spot_orders(
                            sender=address.to_acc_bech32(),
                            orders_data=all_spot_orders_data
                        )
                        
                        response = await broadcaster.broadcast([batch_cancel_msg])
                        
                        # Check for transaction hash in different response formats
                        tx_hash = response.get('txhash') or response.get('txResponse', {}).get('txhash')
                        if tx_hash:
                            print(f"   ✅ Successfully batch cancelled {len(all_spot_orders_data)} spot orders")
                            print(f"   📝 Transaction hash: {tx_hash}")
                            total_cancelled += len(all_spot_orders_data)
                        else:
                            print(f"   ⚠️  Failed to batch cancel spot orders")
                            print(f"   📋 Response: {response}")
                            
                    except Exception as e:
                        print(f"   ❌ Error batch cancelling spot orders: {e}")
                        import traceback
                        print(f"   📋 Traceback: {traceback.format_exc()}")
                
                # Batch cancel derivative orders
                if all_derivative_orders_data:
                    print(f"   🚨 Batch cancelling {len(all_derivative_orders_data)} derivative orders...")
                    try:
                        batch_cancel_msg = composer.msg_batch_cancel_derivative_orders(
                            sender=address.to_acc_bech32(),
                            orders_data=all_derivative_orders_data
                        )
                        
                        response = await broadcaster.broadcast([batch_cancel_msg])
                        
                        # Check for transaction hash in different response formats
                        tx_hash = response.get('txhash') or response.get('txResponse', {}).get('txhash')
                        if tx_hash:
                            print(f"   ✅ Successfully batch cancelled {len(all_derivative_orders_data)} derivative orders")
                            print(f"   📝 Transaction hash: {tx_hash}")
                            total_cancelled += len(all_derivative_orders_data)
                        else:
                            print(f"   ⚠️  Failed to batch cancel derivative orders")
                            print(f"   📋 Response: {response}")
                            
                    except Exception as e:
                        print(f"   ❌ Error batch cancelling derivative orders: {e}")
                        import traceback
                        print(f"   📋 Traceback: {traceback.format_exc()}")
                
                # Close client
                await client.close_chain_channel()
                await client.close_chain_stream_channel()
                
            except Exception as e:
                print(f"   ❌ Error processing wallet {wallet_id}: {e}")
        
        print(f"\n✅ Batch cancellation complete! Total orders cancelled: {total_cancelled}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    asyncio.run(batch_cancel_all_orders())
