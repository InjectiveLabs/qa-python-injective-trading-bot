#!/usr/bin/env python3
"""
Multi-Wallet Market Maker Runner
Runs separate market maker instances for each wallet in parallel.
"""

import asyncio
import signal
import sys
from typing import List, Dict
import json
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

class MultiWalletMarketMaker:
    """Runs multiple market maker instances, one for each wallet."""
    
    def __init__(self):
        self.strategies: Dict[str, MarketMakerStrategy] = {}
        self.running = False
        self.tasks: List[asyncio.Task] = []
        
    async def initialize(self):
        """Initialize all components and strategies."""
        logger.info("🚀 Starting Multi-Wallet Market Making Bot")
        logger.info("=" * 60)
        
        # Initialize components
        logger.info("📡 1. Initializing components...")
        await injective_client.initialize()  # Initialize Injective client first
        await market_manager.initialize()
        await wallet_manager.initialize()
        logger.info("✅ All components initialized successfully")
        
        # Get enabled wallets
        enabled_wallets = [wallet_id for wallet_id, config in wallet_manager.wallets.items() 
                          if config.enabled]
        
        if not enabled_wallets:
            logger.error("❌ No enabled wallets found!")
            return False
            
        logger.info(f"👛 Found {len(enabled_wallets)} enabled wallets: {enabled_wallets}")
        
        # Initialize strategy for each wallet
        logger.info("🤖 2. Initializing market maker strategies...")
        for wallet_id in enabled_wallets:
            try:
                # Create strategy instance for this wallet
                strategy = MarketMakerStrategy(wallet_id=wallet_id)
                
                # Initialize the strategy with markets
                markets = ["INJ/USDT"]  # Default markets
                success = await strategy.initialize(markets)
                if success:
                    self.strategies[wallet_id] = strategy
                    logger.info(f"✅ Strategy initialized for {wallet_id}")
                else:
                    logger.error(f"❌ Failed to initialize strategy for {wallet_id}")
                    
            except Exception as e:
                logger.error(f"❌ Error initializing strategy for {wallet_id}: {e}")
                
        if not self.strategies:
            logger.error("❌ No strategies initialized successfully!")
            return False
            
        logger.info(f"✅ {len(self.strategies)} strategies initialized successfully")
        return True
        
    async def start_all_strategies(self):
        """Start all market maker strategies."""
        logger.info("🎯 3. Starting all market maker strategies...")
        
        for wallet_id, strategy in self.strategies.items():
            try:
                await strategy.start()
                logger.info(f"✅ Strategy started for {wallet_id}")
            except Exception as e:
                logger.error(f"❌ Failed to start strategy for {wallet_id}: {e}")
                
        logger.info("✅ All strategies started successfully")
        
    async def run_strategy_loop(self, wallet_id: str, strategy: MarketMakerStrategy):
        """Run the strategy loop for a specific wallet."""
        logger.info(f"🔄 Starting strategy loop for {wallet_id}")
        
        execution_count = 0
        while self.running:
            try:
                execution_count += 1
                logger.info(f"🔄 Execution #{execution_count} - Running market maker strategy for {wallet_id}...")
                
                # Execute the strategy
                success = await strategy.execute()
                
                if success:
                    logger.info(f"✅ Execution #{execution_count} completed for {wallet_id}")
                else:
                    logger.warning(f"⚠️ Execution #{execution_count} failed for {wallet_id}")
                    
                # Wait before next execution
                logger.info(f"⏰ Waiting 30 seconds before next execution for {wallet_id}...")
                for i in range(30):
                    if not self.running:
                        break
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"❌ Error in strategy loop for {wallet_id}: {e}")
                await asyncio.sleep(5)  # Wait a bit before retrying
                
        logger.info(f"🛑 Strategy loop stopped for {wallet_id}")
        
    async def run_all_strategies(self):
        """Run all strategies in parallel."""
        logger.info("🔄 4. Running all strategies in parallel...")
        logger.info("   - Each wallet runs independently")
        logger.info("   - Press Ctrl+C to stop all strategies")
        logger.info("=" * 60)
        
        self.running = True
        
        # Create tasks for each strategy
        for wallet_id, strategy in self.strategies.items():
            task = asyncio.create_task(self.run_strategy_loop(wallet_id, strategy))
            self.tasks.append(task)
            
        # Wait for all tasks to complete
        try:
            await asyncio.gather(*self.tasks)
        except asyncio.CancelledError:
            logger.info("🛑 All strategy tasks cancelled")
            
    async def stop_all_strategies(self):
        """Stop all market maker strategies."""
        logger.info("🛑 5. Stopping all strategies...")
        
        self.running = False
        
        # Cancel all running tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
                
        # Wait for tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
            
        # Stop all strategies
        for wallet_id, strategy in self.strategies.items():
            try:
                await strategy.stop()
                logger.info(f"✅ Strategy stopped for {wallet_id}")
            except Exception as e:
                logger.error(f"❌ Error stopping strategy for {wallet_id}: {e}")
                
        logger.info("✅ All strategies stopped")
        
    async def cleanup(self):
        """Clean up all connections."""
        logger.info("🧹 6. Cleaning up connections...")
        
        try:
            # Close wallet connections
            await wallet_manager.disconnect_all()
        except Exception as e:
            logger.warning(f"⚠️ Warning: Error closing wallet connections: {e}")
            
        try:
            # Close Injective client
            await injective_client.close()
            logger.info("✅ Injective client closed")
        except Exception as e:
            logger.error(f"❌ Error closing Injective client: {e}")
            
        logger.info("✅ Shutdown complete")
        
    def get_status(self) -> Dict:
        """Get status of all strategies."""
        status = {
            "total_strategies": len(self.strategies),
            "running": self.running,
            "strategies": {}
        }
        
        for wallet_id, strategy in self.strategies.items():
            try:
                status["strategies"][wallet_id] = strategy.get_market_maker_status()
            except Exception as e:
                status["strategies"][wallet_id] = {"error": str(e)}
                
        return status

async def main():
    """Main function to run the multi-wallet market maker."""
    market_maker = MultiWalletMarketMaker()
    
    # Set up signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info("🛑 Received shutdown signal...")
        asyncio.create_task(shutdown(market_maker))
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize
        success = await market_maker.initialize()
        if not success:
            logger.error("❌ Initialization failed!")
            return
            
        # Start strategies
        await market_maker.start_all_strategies()
        
        # Show status
        status = market_maker.get_status()
        logger.info("📊 4. Strategy Status:")
        for wallet_id, wallet_status in status["strategies"].items():
            logger.info(f"   {wallet_id}:")
            logger.info(f"     Strategy: {wallet_status.get('strategy_name', 'Unknown')}")
            logger.info(f"     Running: {wallet_status.get('is_running', False)}")
            logger.info(f"     Markets: {wallet_status.get('markets', [])}")
            logger.info(f"     Total Orders: {wallet_status.get('total_orders', 0)}")
            
        # Run all strategies
        await market_maker.run_all_strategies()
        
    except Exception as e:
        logger.error(f"❌ Error in main loop: {e}")
    finally:
        await shutdown(market_maker)

async def shutdown(market_maker: MultiWalletMarketMaker):
    """Graceful shutdown function."""
    logger.info("🛑 6. Shutting down gracefully...")
    
    try:
        # Stop all strategies
        await market_maker.stop_all_strategies()
        
        # Clean up connections
        await market_maker.cleanup()
        
        logger.info("👋 Multi-wallet market making bot stopped successfully")
        
    except Exception as e:
        logger.error(f"❌ Error during shutdown: {e}")
    finally:
        # Exit the program
        sys.exit(0)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
