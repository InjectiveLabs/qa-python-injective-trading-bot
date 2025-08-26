#!/usr/bin/env python3
"""
Simple script to run the market maker strategy without the web server.
This allows us to test the core functionality directly.
"""

import asyncio
import signal
import sys
import warnings
from strategies.market_maker import MarketMakerStrategy
from core.client import injective_client
from core.markets import market_manager
from core.wallet_manager import wallet_manager
from core.price_monitor import price_monitor
from utils.logger import get_logger

logger = get_logger(__name__)

# Global strategy instance
market_maker_strategy = MarketMakerStrategy()

# Flag for graceful shutdown
is_running = True


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    global is_running
    logger.info(f"Received signal {signum}, shutting down gracefully")
    is_running = False


async def main():
    """Main function to run the market maker."""
    global is_running
    
    print("🚀 Starting Injective Market Making Bot (Strategy Only)")
    print("=" * 60)
    
    try:
        # Suppress expected warnings
        warnings.filterwarnings("ignore", message="coroutine 'wait_for' was never awaited")
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Initialize components
        print("📡 1. Initializing components...")
        await injective_client.initialize()
        await market_manager.initialize()
        await wallet_manager.initialize()
        await price_monitor.initialize()
        
        print("✅ All components initialized successfully")
        
        # Initialize strategy
        print("\n🤖 2. Initializing market maker strategy...")
        success = await market_maker_strategy.initialize(["INJ/USDT"])
        if not success:
            print("❌ Failed to initialize market maker strategy")
            return
        
        print("✅ Strategy initialized successfully")
        
        # Start strategy
        print("\n🎯 3. Starting market maker strategy...")
        success = await market_maker_strategy.start()
        if not success:
            print("❌ Failed to start market maker strategy")
            return
        
        print("✅ Strategy started successfully")
        
        # Display initial status
        print("\n📊 4. Strategy Status:")
        status = market_maker_strategy.get_market_maker_status()
        print(f"   Strategy: {status['strategy_name']}")
        print(f"   Running: {status['is_running']}")
        print(f"   Markets: {status['markets']}")
        print(f"   Price Correction: {'Enabled' if status['price_correction']['enabled'] else 'Disabled'}")
        print(f"   Emergency Orders: {'Enabled' if status['emergency_orders']['threshold'] > 0 else 'Disabled'}")
        
        print("\n🔄 5. Running strategy loop...")
        print("   - Normal market making: LIMIT orders")
        print("   - Price correction: 5% threshold (LIMIT orders)")
        print("   - Emergency correction: 20% threshold (MARKET orders)")
        print("   - Press Ctrl+C to stop")
        print("\n" + "=" * 60)
        
        # Main strategy loop
        execution_count = 0
        while is_running:
            try:
                if market_maker_strategy.is_running:
                    execution_count += 1
                    print(f"\n🔄 Execution #{execution_count} - Running market maker strategy...")
                    await market_maker_strategy.execute()
                    
                    # Show execution summary
                    status = market_maker_strategy.get_market_maker_status()
                    market_orders = status.get('market_orders', {})
                    
                    # Count actual orders
                    total_orders = 0
                    for market_id, orders in market_orders.items():
                        buy_orders = len(orders.get('buy', []))
                        sell_orders = len(orders.get('sell', []))
                        total_orders += buy_orders + sell_orders
                    
                    print(f"📊 Execution #{execution_count} Summary:")
                    print(f"   - Markets: {status['markets']}")
                    print(f"   - Total Orders: {total_orders}")
                    print(f"   - Buy Orders: {sum(len(orders.get('buy', [])) for orders in market_orders.values())}")
                    print(f"   - Sell Orders: {sum(len(orders.get('sell', [])) for orders in market_orders.values())}")
                    print(f"   - Last Update: {status.get('last_update', 'N/A')}")
                    print(f"✅ Execution #{execution_count} completed")
                
                # Wait for next execution (with responsive interrupt)
                print(f"⏰ Waiting 30 seconds before next execution...")
                try:
                    # Use a shorter sleep that can be interrupted
                    for _ in range(30):
                        if not is_running:
                            break
                        await asyncio.sleep(1)
                except asyncio.CancelledError:
                    break
                
            except asyncio.CancelledError:
                logger.info("Strategy loop cancelled")
                break
            except Exception as e:
                logger.error("Error in strategy loop", error=str(e))
                print(f"❌ Error in execution #{execution_count}: {e}")
                await asyncio.sleep(5)  # Wait before retrying
        
        print("\n🛑 6. Shutting down gracefully...")
        
        # Stop strategy
        if market_maker_strategy.is_running:
            print("🛑 Stopping strategy...")
            await market_maker_strategy.stop()
            print("✅ Strategy stopped")
        
        # Cleanup with proper error handling
        print("🧹 Cleaning up connections...")
        try:
            await wallet_manager.disconnect_all()
            print("✅ Wallet connections closed")
        except Exception as e:
            print(f"⚠️  Warning: Error closing wallet connections: {e}")
        
        try:
            await injective_client.close()
            print("✅ Injective client closed")
        except Exception as e:
            print(f"⚠️  Warning: Error closing Injective client: {e}")
        
        print("✅ Shutdown complete")
        print("👋 Market making bot stopped successfully")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        
        # Cleanup on error
        print("🧹 Emergency cleanup...")
        try:
            if market_maker_strategy.is_running:
                await market_maker_strategy.stop()
            await wallet_manager.disconnect_all()
            await injective_client.close()
        except Exception as cleanup_error:
            print(f"⚠️  Warning: Error during emergency cleanup: {cleanup_error}")


if __name__ == "__main__":
    asyncio.run(main())
