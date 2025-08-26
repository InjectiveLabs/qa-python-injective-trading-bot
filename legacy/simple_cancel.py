#!/usr/bin/env python3
"""
Very simple script to cancel all orders.
"""

import asyncio
import json
from pyinjective.async_client_v2 import AsyncClient
from pyinjective.indexer_client import IndexerClient
from pyinjective.core.network import Network
from pyinjective.core.broadcaster import MsgBroadcasterWithPk
from pyinjective import PrivateKey

async def cancel_all_orders():
    print("🚨 Simple Cancel All Orders")
    print("=" * 40)
    
    try:
        # Load wallet configs
        with open('wallets_config.json', 'r') as f:
            wallets_config = json.load(f)
        
        # Load market configs
        with open('markets_config.json', 'r') as f:
            markets_config = json.load(f)
        
        # Initialize network
        network = Network.testnet()
        
        # Initialize indexer client for fetching orders
        indexer_client = IndexerClient(network)
        
        total_cancelled = 0
        
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
                
                # Initialize broadcaster
                gas_price = await client.current_chain_gas_price()
                gas_price = int(gas_price * 1.1)
                
                broadcaster = MsgBroadcasterWithPk.new_using_simulation(
                    network=network,
                    private_key=private_key,
                    gas_price=gas_price,
                    client=client,
                    composer=composer,
                )
                
                print(f"   ✅ Wallet initialized: {address.to_acc_bech32()}")
                
                # Process each market
                for market_id, market_config in markets_config['markets'].items():
                    if not market_config.get('enabled', False):
                        continue
                        
                    print(f"   📊 Processing market: {market_id}")
                    
                    try:
                        # Get orders using indexer client
                        subaccount_id = address.get_subaccount_id(0)
                        
                        if market_config.get('type') == 'spot':
                            orders = await indexer_client.fetch_spot_orders(
                                market_ids=[market_config['market_id']],
                                subaccount_id=subaccount_id
                            )
                        else:
                            orders = await indexer_client.fetch_derivative_orders(
                                market_ids=[market_config['market_id']],
                                subaccount_id=subaccount_id
                            )
                        
                        if orders and 'orders' in orders and orders['orders']:
                            print(f"      📊 Found {len(orders['orders'])} orders to cancel")
                            print(f"      📋 Orders: {orders['orders']}")
                            
                            for order in orders['orders']:
                                order_id = order.get('orderHash')  # Use orderHash instead of orderId
                                if order_id:
                                    print(f"         📝 Cancelling order {order_id}...")
                                    print(f"            Order details: {order}")
                                    
                                    try:
                                        if market_config.get('type') == 'spot':
                                            cancel_msg = composer.msg_cancel_spot_order(
                                                sender=address.to_acc_bech32(),
                                                market_id=market_config['market_id'],
                                                subaccount_id=subaccount_id,
                                                order_hash=order_id
                                            )
                                        else:
                                            cancel_msg = composer.msg_cancel_derivative_order(
                                                sender=address.to_acc_bech32(),
                                                market_id=market_config['market_id'],
                                                subaccount_id=subaccount_id,
                                                order_hash=order_id
                                            )
                                        
                                        response = await broadcaster.broadcast([cancel_msg])
                                        
                                        if response.get('txhash'):
                                            print(f"         ✅ Order {order_id} cancelled successfully")
                                            total_cancelled += 1
                                        else:
                                            print(f"         ⚠️  Failed to cancel order {order_id}")
                                            
                                    except Exception as e:
                                        print(f"         ❌ Error cancelling order {order_id}: {e}")
                                        
                                    # Add delay between cancellations to avoid sequence issues
                                    await asyncio.sleep(1)
                        else:
                            print(f"      ✅ No orders found for {market_id}")
                            
                    except Exception as e:
                        print(f"      ❌ Error processing market {market_id}: {e}")
                
                # Close client
                await client.close_chain_channel()
                await client.close_chain_stream_channel()
                
            except Exception as e:
                print(f"   ❌ Error processing wallet {wallet_id}: {e}")
        
        print(f"\n✅ Cancellation complete! Total orders cancelled: {total_cancelled}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    asyncio.run(cancel_all_orders())
