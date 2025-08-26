#!/usr/bin/env python3
"""
Check order states to understand why some orders appear "missing".
"""
import asyncio
import json
from pyinjective.async_client_v2 import AsyncClient
from pyinjective.indexer_client import IndexerClient
from pyinjective.core.network import Network

async def check_order_states():
    print("🔍 Checking Order States")
    print("=" * 40)
    
    try:
        with open('wallets_config.json', 'r') as f:
            wallets_config = json.load(f)
        with open('markets_config.json', 'r') as f:
            markets_config = json.load(f)
        
        network = Network.testnet()
        indexer_client = IndexerClient(network)
        
        for wallet_config in wallets_config['wallets']:
            if not wallet_config.get('enabled', False):
                continue
            
            wallet_id = wallet_config['id']
            print(f"\n📝 Checking wallet: {wallet_id}")
            
            for market_id, market_config in markets_config['markets'].items():
                if not market_config.get('enabled', False):
                    continue
                
                print(f"   📊 Checking market: {market_id}")
                
                try:
                    # Get all orders (not just booked ones)
                    if market_config.get('type') == 'spot':
                        orders = await indexer_client.fetch_spot_orders(
                            market_ids=[market_config['market_id']],
                            subaccount_id=None  # Get all orders for this market
                        )
                    else:
                        orders = await indexer_client.fetch_derivative_orders(
                            market_ids=[market_config['market_id']],
                            subaccount_id=None  # Get all orders for this market
                        )
                    
                    if orders and 'orders' in orders and orders['orders']:
                        print(f"      📊 Found {len(orders['orders'])} total orders")
                        
                        # Group by state
                        states = {}
                        for order in orders['orders']:
                            state = order.get('state', 'unknown')
                            if state not in states:
                                states[state] = []
                            states[state].append(order)
                        
                        for state, state_orders in states.items():
                            print(f"         📋 State '{state}': {len(state_orders)} orders")
                            for order in state_orders:
                                order_hash = order.get('orderHash', 'N/A')
                                side = order.get('orderSide', 'N/A')
                                price = order.get('price', 'N/A')
                                quantity = order.get('quantity', 'N/A')
                                print(f"            - {side} {quantity} @ {price} (hash: {order_hash[:20]}...)")
                    else:
                        print(f"      ✅ No orders found for {market_id}")
                        
                except Exception as e:
                    print(f"      ❌ Error checking {market_id}: {e}")
                    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    asyncio.run(check_order_states())
