#!/usr/bin/env python3
"""
Simple Market Maker Runner
Runs a single market maker instance with basic functionality.
"""

import asyncio
import signal
import sys
from datetime import datetime

# Add the project root to the path
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from strategies.market_maker import MarketMakerStrategy
from core.client import injective_client
from core.markets import market_manager
from core.wallet_manager import wallet_manager
from utils.logger import get_logger

logger = get_logger(__name__)

async def main():
    """Main function to run the simple market maker."""
    logger.info("🚀 Starting Simple Market Making Bot")
    logger.info("=" * 60)
    
    try:
        # Initialize components
        logger.info("📡 1. Initializing components...")
        await injective_client.initialize()
        await market_manager.initialize()
        await wallet_manager.initialize()
        logger.info("✅ All components initialized successfully")
        
        # Create and initialize strategy
        logger.info("🤖 2. Initializing market maker strategy...")
        strategy = MarketMakerStrategy()  # No wallet_id - uses main wallet
        success = await strategy.initialize(["INJ/USDT"])
        
        if not success:
            logger.error("❌ Failed to initialize strategy!")
            return
            
        logger.info("✅ Strategy initialized successfully")
        
        # Start strategy
        logger.info("🎯 3. Starting market maker strategy...")
        await strategy.start()
        logger.info("✅ Strategy started successfully")
        
        # Show status
        status = strategy.get_market_maker_status()
        logger.info("📊 4. Strategy Status:")
        logger.info(f"   Strategy: {status.get('strategy_name', 'Unknown')}")
        logger.info(f"   Running: {status.get('is_running', False)}")
        logger.info(f"   Markets: {status.get('markets', [])}")
        logger.info(f"   Total Orders: {status.get('total_orders', 0)}")
        
        # Run strategy loop
        logger.info("🔄 5. Running market maker strategy...")
        logger.info("   - Press Ctrl+C to stop")
        logger.info("=" * 60)
        
        execution_count = 0
        while True:
            try:
                execution_count += 1
                logger.info(f"🔄 Execution #{execution_count} - Running market maker strategy...")
                
                # Execute the strategy
                success = await strategy.execute()
                
                if success:
                    logger.info(f"✅ Execution #{execution_count} completed successfully")
                else:
                    logger.warning(f"⚠️ Execution #{execution_count} failed")
                    
                # Wait before next execution
                logger.info(f"⏰ Waiting 30 seconds before next execution...")
                for i in range(30):
                    await asyncio.sleep(1)
                    
            except KeyboardInterrupt:
                logger.info("🛑 Received interrupt signal...")
                break
            except Exception as e:
                logger.error(f"❌ Error in execution loop: {e}")
                await asyncio.sleep(5)  # Wait a bit before retrying
                
    except Exception as e:
        logger.error(f"❌ Error in main loop: {e}")
    finally:
        # Cleanup
        logger.info("🛑 6. Shutting down gracefully...")
        
        try:
            # Stop strategy
            await strategy.stop()
            logger.info("✅ Strategy stopped")
            
            # Close connections
            await injective_client.close()
            logger.info("✅ Injective client closed")
            
            logger.info("👋 Simple market making bot stopped successfully")
            
        except Exception as e:
            logger.error(f"❌ Error during shutdown: {e}")
        finally:
            sys.exit(0)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
