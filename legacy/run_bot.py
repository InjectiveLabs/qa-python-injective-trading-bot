#!/usr/bin/env python3
"""
Simple market-making bot runner for Phase 1 (MVP).
Runs the bot directly without web interface.
"""

import asyncio
import signal
import sys
from typing import Optional

from core.client import injective_client
from core.markets import market_manager
from core.wallet_manager import wallet_manager
from core.price_monitor import price_monitor
from strategies.market_maker import MarketMakerStrategy
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# Global strategy instance
market_maker_strategy: Optional[MarketMakerStrategy] = None

async def initialize_bot():
    """Initialize all bot components."""
    logger.info("🚀 Starting Injective Market Making Bot (Phase 1)")
    
    try:
        # Initialize Injective client
        logger.info("📡 Initializing Injective client")
        await injective_client.initialize()
        if not injective_client.is_initialized():
            logger.error("❌ Failed to initialize Injective client")
            return False
        
        # Initialize market manager
        logger.info("📊 Initializing market manager")
        await market_manager.initialize()
        if not market_manager._initialized:
            logger.error("❌ Failed to initialize market manager")
            return False
        
        # Initialize wallet manager
        logger.info("💰 Initializing wallet manager")
        await wallet_manager.initialize()
        if not wallet_manager._initialized:
            logger.error("❌ Failed to initialize wallet manager")
            return False
        
        # Initialize price monitor
        logger.info("📈 Initializing price monitor")
        await price_monitor.initialize()
        
        # Initialize market maker strategy
        logger.info("🤖 Initializing market maker strategy")
        global market_maker_strategy
        market_maker_strategy = MarketMakerStrategy()
        
        # Get enabled markets from market manager
        enabled_markets = list(market_manager.market_configs.keys())
        if not enabled_markets:
            logger.error("❌ No enabled markets found")
            return False
            
        await market_maker_strategy.initialize(enabled_markets)
        
        # Start the strategy
        logger.info("🚀 Starting market maker strategy")
        await market_maker_strategy.start()
        
        logger.info("✅ Bot initialization completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Bot initialization failed: {e}")
        return False

async def run_bot():
    """Run the market-making bot."""
    logger.info("🎯 Starting market making operations")
    
    try:
        while True:
            logger.info("🔄 Bot execution cycle starting...")
            
            if market_maker_strategy and market_maker_strategy.is_running:
                logger.info("🤖 Executing market maker strategy...")
                await market_maker_strategy.execute()
                logger.info("✅ Strategy execution completed")
            else:
                logger.warning("⚠️ Strategy not running")
            
            logger.info(f"⏳ Waiting {settings.price_monitoring_interval} seconds...")
            # Wait for next execution
            await asyncio.sleep(settings.price_monitoring_interval)
            
    except asyncio.CancelledError:
        logger.info("🛑 Bot execution cancelled")
    except Exception as e:
        logger.error(f"❌ Error in bot execution: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")

async def shutdown_bot():
    """Shutdown the bot gracefully."""
    logger.info("🛑 Shutting down bot")
    
    try:
        # Stop strategy
        if market_maker_strategy and market_maker_strategy.is_running:
            await market_maker_strategy.stop()
        
        # Close client connections
        await injective_client.close()
        
        logger.info("✅ Bot shutdown completed")
        
    except Exception as e:
        logger.error(f"❌ Error during shutdown: {e}")

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"📡 Received signal {signum}, shutting down gracefully")
    sys.exit(0)

async def main():
    """Main bot execution."""
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Initialize bot
    if not await initialize_bot():
        logger.error("❌ Bot initialization failed, exiting")
        sys.exit(1)
    
    try:
        # Run the bot
        await run_bot()
    except KeyboardInterrupt:
        logger.info("🛑 Received keyboard interrupt")
    finally:
        # Shutdown gracefully
        await shutdown_bot()

if __name__ == "__main__":
    asyncio.run(main())
