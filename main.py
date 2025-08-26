"""
Main entry point for the Injective Market Making Bot.
"""

import asyncio
import signal
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings
from core.client import injective_client
from core.markets import market_manager
from core.wallet_manager import wallet_manager
from strategies.market_maker import MarketMakerStrategy
from api.routes import router
from utils.logger import logger

# Global strategy instance
market_maker_strategy = MarketMakerStrategy()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Injective Market Making Bot")
    
    try:
        # Initialize Injective client
        logger.info("Initializing Injective client")
        await injective_client.initialize()
        if not injective_client.is_initialized():
            logger.error("Failed to initialize Injective client")
            sys.exit(1)
        
        # Initialize market manager
        logger.info("Initializing market manager")
        await market_manager.initialize()
        if not market_manager._initialized:
            logger.error("Failed to initialize market manager")
            sys.exit(1)
        
        # Initialize wallet manager
        logger.info("Initializing wallet manager")
        await wallet_manager.initialize()
        if not wallet_manager._initialized:
            logger.error("Failed to initialize wallet manager")
            sys.exit(1)
        
        logger.info("Injective Market Making Bot started successfully")
        
    except Exception as e:
        logger.error("Failed to start application", error=str(e))
        sys.exit(1)
    
    yield
    
    # Shutdown
    logger.info("Shutting down Injective Market Making Bot")
    
    try:
        # Stop strategy
        if market_maker_strategy.is_running:
            await market_maker_strategy.stop()
        
        # Disconnect wallet clients
        await wallet_manager.disconnect_all()
        
        # Close Injective client
        await injective_client.close()
        
        logger.info("Injective Market Making Bot shutdown complete")
        
    except Exception as e:
        logger.error("Error during shutdown", error=str(e))


# Create FastAPI application
app = FastAPI(
    title="Injective Market Making Bot",
    description="A scalable market making bot for Injective testnet",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1")


# Signal handlers for graceful shutdown
def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, shutting down gracefully")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


async def run_strategy_loop():
    """Run the strategy execution loop."""
    logger.info("Starting strategy execution loop")
    
    while True:
        try:
            if market_maker_strategy.is_running:
                await market_maker_strategy.execute()
            
            # Wait for next execution
            await asyncio.sleep(settings.price_monitoring_interval)
            
        except asyncio.CancelledError:
            logger.info("Strategy loop cancelled")
            break
        except Exception as e:
            logger.error("Error in strategy loop", error=str(e))
            await asyncio.sleep(5)  # Wait before retrying


async def run_balance_update_loop():
    """Run the balance update loop."""
    logger.info("Starting balance update loop")
    
    while True:
        try:
            await wallet_manager.update_all_balances()
            
            # Wait for next update
            await asyncio.sleep(60)  # Update balances every minute
            
        except asyncio.CancelledError:
            logger.info("Balance update loop cancelled")
            break
        except Exception as e:
            logger.error("Error in balance update loop", error=str(e))
            await asyncio.sleep(30)  # Wait before retrying


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    # Start background tasks
    asyncio.create_task(run_strategy_loop())
    asyncio.create_task(run_balance_update_loop())


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting Injective Market Making Bot server")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.api_port,
        reload=False,
        log_level=settings.log_level.lower()
    )
