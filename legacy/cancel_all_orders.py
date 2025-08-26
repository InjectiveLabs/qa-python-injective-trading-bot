#!/usr/bin/env python3
"""
Simple script to cancel all orders from all wallets.
"""

import asyncio
import json
from core.wallet_manager import wallet_manager
from core.markets import market_manager
from core.client import injective_client

async def cancel_all_orders():
    print("🚨 Cancelling All Orders")
    print("=" * 40)
    
    try:
        # Initialize components
        await injective_client.initialize()
        await market_manager.initialize()
        await wallet_manager.initialize()
        
        print("✅ Components initialized")
        
        # Load market configs
        with open('markets_config.json', 'r') as f:
            markets_config = json.load(f)
        
        # Load wallet configs
        with open('wallets_config.json', 'r') as f:
            wallets_config = json.load(f)
        
        total_cancelled = 0
        
        # Cancel orders for each market
        for market_id, market_config in markets_config['markets'].items():
            if not market_config.get('enabled', False):
                continue
                
            print(f"\n📝 Processing market: {market_id}")
            
            # Cancel orders from each wallet
            for wallet_config in wallets_config['wallets']:
                if not wallet_config.get('enabled', False):
                    continue
                
                wallet_id = wallet_config['id']
                
                print(f"   🔄 Cancelling orders from {wallet_id}...")
                
                try:
                    # Get wallet data
                    wallet_data = await wallet_manager.get_wallet_data(wallet_id)
                    if not wallet_data:
                        print(f"   ❌ No wallet data for {wallet_id}")
                        continue
                    
                    subaccount_id = wallet_data.address + "0"
                    
                    # Get orders based on market type
                    if market_config.get('type') == 'spot':
                        orders = await injective_client.get_spot_orders(market_id, subaccount_id)
                    else:
                        orders = await injective_client.get_derivative_orders(market_id, subaccount_id)
                    
                    if orders and 'orders' in orders and orders['orders']:
                        print(f"   📊 Found {len(orders['orders'])} orders to cancel")
                        
                        for order in orders['orders']:
                            order_id = order.get('orderId')
                            if order_id:
                                print(f"      📝 Cancelling order {order_id}...")
                                
                                try:
                                    if market_config.get('type') == 'spot':
                                        response = await injective_client.cancel_spot_order(
                                            market_id=market_id,
                                            subaccount_id=subaccount_id,
                                            order_hash=order_id
                                        )
                                    else:
                                        response = await injective_client.cancel_derivative_order(
                                            market_id=market_id,
                                            subaccount_id=subaccount_id,
                                            order_hash=order_id
                                        )
                                    
                                    if response.get('txhash'):
                                        print(f"      ✅ Order {order_id} cancelled successfully")
                                        total_cancelled += 1
                                    else:
                                        print(f"      ⚠️  Failed to cancel order {order_id}")
                                        
                                except Exception as e:
                                    print(f"      ❌ Error cancelling order {order_id}: {e}")
                    else:
                        print(f"   ✅ No orders found for {wallet_id}")
                        
                except Exception as e:
                    print(f"   ❌ Error processing wallet {wallet_id}: {e}")
        
        print(f"\n✅ Cancellation complete! Total orders cancelled: {total_cancelled}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    asyncio.run(cancel_all_orders())
