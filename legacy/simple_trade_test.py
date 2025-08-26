#!/usr/bin/env python3
"""
Simple script to fetch INJ/USDT price and place a basic order.
"""

import asyncio
from decimal import Decimal
from core.client import injective_client
from core.markets import market_manager
from core.price_feed import price_feed
from utils.logger import get_logger
from pyinjective.async_client import Composer
from pyinjective.core.network import Network

logger = get_logger(__name__)

async def simple_trade_test():
    """Simple test to fetch price and place order."""
    print("🚀 Simple Trade Test - INJ/USDT")
    print("=" * 40)
    
    try:
        # Step 1: Initialize everything
        print("📡 1. Initializing client...")
        await injective_client.initialize()
        
        print("📊 2. Initializing market manager...")
        await market_manager.initialize()
        
        print("📈 3. Initializing price feed...")
        await price_feed.initialize()
        
        # Step 2: Get current prices
        print("\n💰 Getting Current Prices:")
        
        # Get oracle price (external API)
        oracle_price = await price_feed.get_reference_price("INJ", "USDT")
        print(f"  🔮 Oracle Price (CryptoCompare): ${oracle_price}")
        
        # Get testnet orderbook price
        market_config = await market_manager.get_market_config("INJ/USDT")
        if market_config:
            print(f"  📊 Market ID: {market_config.market_id}")
            
            # Get raw orderbook
            orderbook = await injective_client.get_spot_orderbook(market_config.market_id)
            if orderbook and 'orderbook' in orderbook:
                ob = orderbook['orderbook']
                buys = ob.get('buys', [])
                sells = ob.get('sells', [])
                
                if buys and sells:
                    best_bid_raw = float(buys[0]['price'])
                    best_ask_raw = float(sells[0]['price'])
                    
                    print(f"  📖 Testnet Best Bid (raw): {best_bid_raw}")
                    print(f"  📖 Testnet Best Ask (raw): {best_ask_raw}")
                    
                    # If prices are very small, maybe we use oracle price
                    if best_bid_raw < 0.001 and best_ask_raw < 0.001:
                        print(f"  ⚠️  Testnet prices very small, using oracle price")
                        base_price = oracle_price
                    else:
                        mid_price = (best_bid_raw + best_ask_raw) / 2
                        print(f"  📊 Testnet Mid Price: ${mid_price:.6f}")
                        base_price = mid_price
                else:
                    print(f"  ❌ No testnet liquidity, using oracle price")
                    base_price = oracle_price
            else:
                print(f"  ❌ No orderbook data, using oracle price")
                base_price = oracle_price
        else:
            print(f"  ❌ No market config found")
            return
        
        print(f"  ✅ Using base price: ${base_price:.4f}")
        
        # Step 3: Calculate order prices
        print(f"\n📋 Calculating Order Prices:")
        spread_percent = 0.5  # 0.5% spread
        tick_size = Decimal("0.001")  # Minimum price tick size
        
        # Convert to Decimal for precise calculations
        base_price_decimal = Decimal(str(base_price))
        bid_price_raw = base_price_decimal * (Decimal("1") - Decimal(str(spread_percent)) / Decimal("200"))  # Buy 0.25% below
        ask_price_raw = base_price_decimal * (Decimal("1") + Decimal(str(spread_percent)) / Decimal("200"))  # Sell 0.25% above
        
        # Round to tick size using integer arithmetic to avoid floating point issues
        bid_price_int = round(bid_price_raw / tick_size)
        ask_price_int = round(ask_price_raw / tick_size)
        
        # Convert back to Decimal with exact precision
        bid_price = bid_price_int * tick_size
        ask_price = ask_price_int * tick_size
        
        print(f"  💚 BUY order price:  ${bid_price:.4f}")
        print(f"  ❤️  SELL order price: ${ask_price:.4f}")
        
        # Step 4: Create order messages (but don't send yet)
        print(f"\n📝 Creating Order Messages:")
        
        if not injective_client.composer:
            print(f"  ❌ No composer available")
            return
        
        # Create BUY order message
        buy_msg = injective_client.composer.msg_create_spot_limit_order(
            sender=injective_client.address.to_acc_bech32(),
            market_id=market_config.market_id,
            subaccount_id=injective_client.address.get_subaccount_id(0),
            fee_recipient=injective_client.address.to_acc_bech32(),
            price=bid_price,
            quantity=Decimal("10.0"),  # 10 INJ
            order_type="BUY",
            cid=None
        )
        print(f"  ✅ BUY order message created")
        
        # Create SELL order message
        sell_msg = injective_client.composer.msg_create_spot_limit_order(
            sender=injective_client.address.to_acc_bech32(),
            market_id=market_config.market_id,
            subaccount_id=injective_client.address.get_subaccount_id(0),
            fee_recipient=injective_client.address.to_acc_bech32(),
            price=ask_price,
            quantity=Decimal("10.0"),  # 10 INJ
            order_type="SELL",
            cid=None
        )
        print(f"  ✅ SELL order message created")
        
        # Step 5: Check wallet balance (optional)
        print(f"\n💳 Wallet Info:")
        print(f"  🔑 Address: {injective_client.address.to_acc_bech32()}")
        
        # Step 6: Ask user if they want to place orders
        print(f"\n🚨 READY TO PLACE ORDERS:")
        print(f"  📊 Market: INJ/USDT")
        print(f"  💚 BUY:  {bid_price:.4f} USDT (10 INJ)")
        print(f"  ❤️  SELL: {ask_price:.4f} USDT (10 INJ)")
        print(f"")
        print(f"  ⚠️  This is testnet - no real money!")
        
        # For now, just simulate the orders
        print(f"\n🎭 SIMULATING ORDERS (not actually placing):")
        print(f"  ✅ BUY order would be placed")
        print(f"  ✅ SELL order would be placed")
        
        print(f"\n🎉 Test completed successfully!")
        print(f"💡 To actually place orders, uncomment the broadcast code below")
        
        # Actually placing orders on testnet:
        print(f"\n📡 Broadcasting BUY order...")
        buy_response = await injective_client.message_broadcaster.broadcast([buy_msg])
        print(f"BUY response: {buy_response}")
        
        print(f"📡 Broadcasting SELL order...")
        sell_response = await injective_client.message_broadcaster.broadcast([sell_msg])
        print(f"SELL response: {sell_response}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    asyncio.run(simple_trade_test())
