#!/usr/bin/env python3
"""
Test script for Enhanced Derivative Trading Strategy
Tests the new two-phase approach: Market Moving → Orderbook Building
"""

import asyncio
import sys
from decimal import Decimal
from derivative_trader import DerivativeTrader, log

async def test_enhanced_derivative_strategy():
    """Test the enhanced derivative trading strategy with different scenarios"""
    print("🚀 TESTING ENHANCED DERIVATIVE TRADING STRATEGY")
    print("=" * 80)
    
    try:
        trader = DerivativeTrader("wallet_1")
        await trader.initialize()
        
        # Get market config
        market_config = trader.config["markets"]["INJ/USDT-PERP"]
        market_id = market_config["testnet_market_id"]
        market_symbol = "INJ/USDT-PERP"
        
        # Test scenarios with different price gaps
        test_scenarios = [
            {
                "name": "🚨 EMERGENCY PRICE CORRECTION",
                "description": "Massive gap requires aggressive market moving",
                "testnet_price": 25.00,
                "mainnet_price": 12.50,
                "expected_phase": "MARKET_MOVING",
                "gap_percent": 100.0
            },
            {
                "name": "⚖️ MODERATE CONVERGENCE",
                "description": "Medium gap requires transition strategy", 
                "testnet_price": 15.00,
                "mainnet_price": 12.50,
                "expected_phase": "TRANSITION",
                "gap_percent": 20.0
            },
            {
                "name": "🎪 LIQUIDITY BUILDING",
                "description": "Small gap allows orderbook building",
                "testnet_price": 12.80,
                "mainnet_price": 12.50,
                "expected_phase": "LIQUIDITY_PROVISION", 
                "gap_percent": 2.4
            }
        ]
        
        for i, scenario in enumerate(test_scenarios, 1):
            print(f"\n{'='*60}")
            print(f"📊 TEST {i}: {scenario['name']}")
            print(f"📝 {scenario['description']}")
            print(f"💰 Testnet: ${scenario['testnet_price']:.2f} | Mainnet: ${scenario['mainnet_price']:.2f}")
            print(f"📈 Gap: {scenario['gap_percent']:.1f}%")
            print(f"🎯 Expected Phase: {scenario['expected_phase']}")
            print("=" * 60)
            
            # Test phase-based strategy execution
            await trader.execute_phase_based_strategy(
                market_id, market_symbol, market_config,
                scenario['testnet_price'], scenario['mainnet_price'], scenario['gap_percent']
            )
            
            # Check if correct phase was set
            current_phase = trader.market_states.get(market_id, {}).get('phase', 'UNKNOWN')
            if current_phase == scenario['expected_phase']:
                print(f"✅ Correct phase selected: {current_phase}")
            else:
                print(f"❌ Wrong phase! Expected: {scenario['expected_phase']}, Got: {current_phase}")
            
            # Show active orders tracking
            if market_id in trader.active_orders:
                orders = trader.active_orders[market_id]
                print(f"📋 Active Order Tracking:")
                print(f"   Market Moving: {len(orders.get('MARKET_MOVING', []))} batches")
                print(f"   Liquidity Provision: {len(orders.get('LIQUIDITY_PROVISION', []))} batches")
                print(f"   Transition: {len(orders.get('TRANSITION', []))} batches")
            
            print(f"⏱️ Waiting 3 seconds before next test...\n")
            await asyncio.sleep(3)
        
        # Test order creation methods directly
        print("\n" + "=" * 80)
        print("🧪 TESTING ORDER CREATION METHODS")
        print("=" * 80)
        
        # Test market moving orders
        print("\n🎯 Testing Market Moving Orders (Testnet $25 → Mainnet $12.50)")
        moving_orders = await trader.create_market_moving_orders(
            market_id, market_symbol, market_config, 25.00, 12.50
        )
        print(f"✅ Created {len(moving_orders)} market-moving orders")
        analyze_orders(moving_orders, "MARKET_MOVING")
        
        # Test orderbook depth orders
        print("\n🎪 Testing Orderbook Depth Orders (Target Price $12.50)")
        depth_orders = await trader.create_orderbook_depth_orders(
            market_id, market_symbol, market_config, 12.50
        )
        print(f"✅ Created {len(depth_orders)} orderbook depth orders")
        analyze_orders(depth_orders, "ORDERBOOK_DEPTH")
        
        # Test smart orders (existing)
        print("\n🧠 Testing Smart Orders (Testnet $12.80 → Mainnet $12.50)")
        smart_orders = await trader.create_smart_derivative_orders(
            market_id, market_symbol, market_config, 12.80, 12.50
        )
        print(f"✅ Created {len(smart_orders)} smart orders")
        analyze_orders(smart_orders, "SMART_ORDERS")
        
        # Show final summary
        print("\n" + "=" * 80)
        print("📊 ENHANCED STRATEGY TEST SUMMARY")
        print("=" * 80)
        summary = trader.get_trading_summary()
        print(summary)
        
        print("\n✅ Enhanced derivative trading strategy test completed successfully!")
        
    except Exception as e:
        print(f"❌ Enhanced strategy test failed: {e}")
        import traceback
        traceback.print_exc()

def analyze_orders(orders, order_type):
    """Analyze order composition"""
    if not orders:
        print(f"⚠️ No {order_type} orders created")
        return
    
    buy_orders = [o for o in orders if hasattr(o, 'order_type') and o.order_type == "BUY"]
    sell_orders = [o for o in orders if hasattr(o, 'order_type') and o.order_type == "SELL"]
    
    # Try to extract prices (this might fail depending on order structure)
    try:
        buy_prices = []
        sell_prices = []
        
        for order in orders:
            # The order structure might be different, so we'll try to access price
            if hasattr(order, 'price'):
                price = float(order.price)
                if hasattr(order, 'order_type'):
                    if order.order_type == "BUY":
                        buy_prices.append(price)
                    elif order.order_type == "SELL":
                        sell_prices.append(price)
        
        print(f"   📊 Order Analysis:")
        print(f"      Buy Orders: {len(buy_orders)} | Sell Orders: {len(sell_orders)}")
        
        if buy_prices:
            print(f"      Buy Price Range: ${min(buy_prices):.4f} - ${max(buy_prices):.4f}")
        if sell_prices:
            print(f"      Sell Price Range: ${min(sell_prices):.4f} - ${max(sell_prices):.4f}")
            
    except Exception as e:
        print(f"   📊 Order Analysis: {len(buy_orders)} buys, {len(sell_orders)} sells (detailed analysis failed)")

async def main():
    """Main test entry point"""
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("Enhanced Derivative Trading Strategy Test")
        print("Usage: python test_enhanced_derivative_strategy.py")
        print("\nThis script tests the new two-phase approach:")
        print("1. 🚀 Market Moving Phase - Aggressive price correction for large gaps")
        print("2. 🎪 Orderbook Building Phase - Realistic liquidity around target price")
        print("3. ⚖️ Transition Phase - Moderate convergence strategy")
        return
    
    await test_enhanced_derivative_strategy()

if __name__ == "__main__":
    asyncio.run(main())
