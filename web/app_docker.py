#!/usr/bin/env python3
"""
Docker-Enabled Trading Bot Manager - Web Interface
Manages trading bots as Docker containers instead of processes
"""

import asyncio
import json
import os
import time
import secrets
import docker
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

# Add parent directory to path to import from utils
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.secure_wallet_loader import load_wallets_from_env

app = FastAPI(title="Trading Bot Manager")
security = HTTPBasic()

# Initialize Docker client
try:
    docker_client = docker.from_env()
    DOCKER_AVAILABLE = True
except Exception as e:
    print(f"WARNING: Docker not available: {e}")
    DOCKER_AVAILABLE = False

# Load authentication credentials from environment variables
AUTH_USERNAME = os.getenv("WEB_AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("WEB_AUTH_PASSWORD", "admin")

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify HTTP Basic Authentication credentials."""
    correct_username = secrets.compare_digest(credentials.username, AUTH_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, AUTH_PASSWORD)
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# Request models
class StartBotRequest(BaseModel):
    bot_type: str  # "spot" or "derivative"
    wallet_id: str
    market: str

class StopBotRequest(BaseModel):
    wallet_id: str
    container_id: str  # Changed from pid to container_id

# Global state for tracking running bots
running_bots = {}  # wallet_id -> bot_info

@app.get("/")
async def get_dashboard(username: str = Depends(verify_credentials)):
    """Serve the main dashboard page"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    static_file_path = os.path.join(script_dir, "static", "index.html")
    
    with open(static_file_path, "r") as f:
        return HTMLResponse(f.read())

@app.get("/static/{file_path:path}")
async def static_files(file_path: str):
    """Serve static files"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    static_file_path = os.path.join(script_dir, "static", file_path)
    
    if not os.path.exists(static_file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(static_file_path)

@app.get("/api/wallets")
async def get_wallets():
    """Get available wallets"""
    try:
        wallets_config = load_wallets_from_env()
        return {
            "wallets": [
                {
                    "id": wallet["id"],
                    "name": wallet["name"],
                    "enabled": wallet.get("enabled", False)
                }
                for wallet in wallets_config["wallets"]
                if wallet.get("enabled", False)
            ]
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/markets")
async def get_markets():
    """Get available markets organized by type"""
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(project_root, "config", "trader_config.json")
        
        with open(config_path, "r") as f:
            config = json.load(f)
        
        spot_markets = []
        derivative_markets = []
        
        for market_symbol, market_config in config["markets"].items():
            market_info = {
                "symbol": market_symbol,
                "type": market_config.get("type", "spot")
            }
            
            if market_config.get("type") == "derivative":
                derivative_markets.append(market_info)
            else:
                spot_markets.append(market_info)
        
        return {
            "markets": {
                "spot": spot_markets,
                "derivative": derivative_markets
            }
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/running-bots")
async def get_running_bots(username: str = Depends(verify_credentials)):
    """Get currently running bots with enhanced information"""
    try:
        # Update running bots status by checking containers
        await update_running_bots_status()
        
        bots = []
        for wallet_id, bot_info in running_bots.items():
            # Calculate uptime
            current_time = time.time()
            uptime_seconds = current_time - bot_info["started_at"]
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            seconds = int(uptime_seconds % 60)
            uptime = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            
            # Get wallet balance
            wallet_balance = None
            try:
                wallet_balance = await get_wallet_balance(wallet_id)
            except Exception as e:
                wallet_balance = {'error': f'Balance check failed: {str(e)}'}
            
            # Get market prices  
            market_prices = None
            try:
                market_prices = await get_market_prices(bot_info["market"])
            except Exception as e:
                market_prices = {'error': f'Price check failed: {str(e)}'}
            
            bots.append({
                "wallet_id": wallet_id,
                "bot_type": bot_info["bot_type"],
                "market": bot_info["market"],
                "container_id": bot_info["container_id"],
                "container_name": bot_info.get("container_name", ""),
                "started_at": datetime.fromtimestamp(bot_info["started_at"]).isoformat(),
                "uptime": uptime,
                "wallet_balance": wallet_balance,
                "market_prices": market_prices,
                "status": bot_info.get("status", "unknown")
            })
        
        return {"bots": bots}
    except Exception as e:
        print(f"DEBUG: Error in get_running_bots: {e}")
        return {"error": str(e)}

@app.post("/api/start-bot")
async def start_bot(request: StartBotRequest, username: str = Depends(verify_credentials)):
    """Start a trading bot as a Docker container"""
    try:
        if not DOCKER_AVAILABLE:
            return {"success": False, "error": "Docker is not available"}
            
        # Check if wallet is already in use
        if request.wallet_id in running_bots:
            return {"success": False, "error": f"Wallet {request.wallet_id} is already in use"}
        
        # Get wallet private key from environment
        wallet_key_env = f"{request.wallet_id.upper()}_PRIVATE_KEY"
        wallet_private_key = os.getenv(wallet_key_env)
        
        if not wallet_private_key:
            return {"success": False, "error": f"Wallet private key not found for {request.wallet_id}"}
        
        # Determine which image to use
        if request.bot_type == "spot":
            image_name = "spot-trader:latest"
        elif request.bot_type == "derivative":
            image_name = "derivative-trader:latest"
        else:
            return {"success": False, "error": f"Invalid bot type: {request.bot_type}"}
        
        # Generate unique container name
        container_name = f"{request.bot_type}-{request.wallet_id}-{request.market.replace('/', '-')}"
        
        # Get absolute paths for volumes
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logs_path = os.path.join(project_root, "logs")
        config_path = os.path.join(project_root, "config")
        data_path = os.path.join(project_root, "data")
        
        # Prepare environment variables
        environment = {
            "WALLET_ID": request.wallet_id,
            "MARKET": request.market if request.bot_type == "spot" else "",
            "MARKETS": request.market if request.bot_type == "derivative" else "",
            f"{request.wallet_id.upper()}_PRIVATE_KEY": wallet_private_key,
        }
        
        # Copy other necessary env vars
        for key in os.environ:
            if key.startswith("WALLET_") or key in ["COSMOS_GRPC", "TENDERMINT_RPC", "EXCHANGE_GRPC"]:
                environment[key] = os.getenv(key)
        
        try:
            # Create and start container
            container = docker_client.containers.run(
                image=image_name,
                name=container_name,
                detach=True,
                environment=environment,
                volumes={
                    logs_path: {"bind": "/app/logs", "mode": "rw"},
                    config_path: {"bind": "/app/config", "mode": "ro"},
                    data_path: {"bind": "/app/data", "mode": "ro"}
                },
                labels={
                    "app": "trading-bot",
                    "wallet_id": request.wallet_id,
                    "market": request.market,
                    "bot_type": request.bot_type
                },
                network="trading-network",
                restart_policy={"Name": "unless-stopped"}
            )
            
            # Wait a moment to ensure container starts
            await asyncio.sleep(2)
            
            # Refresh container status
            container.reload()
            
            # Check if container is still running
            if container.status != "running":
                logs = container.logs(tail=50).decode('utf-8')
                container.remove(force=True)
                return {"success": False, "error": f"Container failed to start. Logs:\n{logs}"}
            
            # Store bot info
            running_bots[request.wallet_id] = {
                "bot_type": request.bot_type,
                "market": request.market,
                "container_id": container.id,
                "container_name": container.name,
                "container": container,
                "started_at": time.time(),
                "status": "running"
            }
            
            return {
                "success": True,
                "message": f"{request.bot_type.title()} trader started for {request.wallet_id} on {request.market}",
                "container_id": container.short_id
            }
            
        except docker.errors.ImageNotFound:
            return {"success": False, "error": f"Docker image '{image_name}' not found. Please build images first."}
        except docker.errors.APIError as e:
            return {"success": False, "error": f"Docker API error: {str(e)}"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/stop-bot")
async def stop_bot(request: StopBotRequest, username: str = Depends(verify_credentials)):
    """Stop a specific trading bot container"""
    try:
        if not DOCKER_AVAILABLE:
            return {"success": False, "error": "Docker is not available"}
            
        if request.wallet_id not in running_bots:
            return {"success": False, "error": f"No bot running for wallet {request.wallet_id}"}
        
        bot_info = running_bots[request.wallet_id]
        
        # Verify container ID matches
        if not bot_info["container_id"].startswith(request.container_id):
            return {"success": False, "error": "Container ID mismatch, bot may have restarted"}
        
        try:
            # Get container
            container = docker_client.containers.get(bot_info["container_id"])
            
            # Stop container gracefully
            container.stop(timeout=10)
            
            # Remove container
            container.remove()
            
        except docker.errors.NotFound:
            # Container already gone
            pass
        except Exception as e:
            print(f"Error stopping container: {e}")
        
        # Remove from running bots
        del running_bots[request.wallet_id]
        
        return {
            "success": True,
            "message": f"Bot stopped for wallet {request.wallet_id}"
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

async def update_running_bots_status():
    """Update the status of running bots by checking container status"""
    if not DOCKER_AVAILABLE:
        return
        
    dead_bots = []
    
    for wallet_id, bot_info in running_bots.items():
        try:
            # Get container status
            container = docker_client.containers.get(bot_info["container_id"])
            
            # Update status
            bot_info["status"] = container.status
            
            # If container is not running, mark for removal
            if container.status not in ["running", "restarting"]:
                print(f"DEBUG: Bot {wallet_id} (Container {container.short_id}) status: {container.status}")
                dead_bots.append(wallet_id)
                
        except docker.errors.NotFound:
            print(f"DEBUG: Bot {wallet_id} container not found")
            dead_bots.append(wallet_id)
        except Exception as e:
            print(f"DEBUG: Error checking container for {wallet_id}: {e}")
            dead_bots.append(wallet_id)
    
    # Remove dead bots from tracking
    for wallet_id in dead_bots:
        print(f"DEBUG: Removing dead bot {wallet_id}")
        del running_bots[wallet_id]

# Import the rest of the utility functions from original app.py
# (get_wallet_balance, get_market_prices, get_bot_logs, etc.)
# These remain unchanged as they don't depend on subprocess

async def get_wallet_balance(wallet_id: str):
    """Get balance information for a specific wallet"""
    try:
        from utils.balance_checker import BalanceChecker
        
        checker = BalanceChecker()
        all_balances = await checker.check_all_wallets_all_tokens()
        
        for wallet_balance in all_balances:
            if wallet_balance.get('wallet_id') == wallet_id:
                balances = wallet_balance.get('balances', [])
                
                key_balances = {}
                for balance in balances:
                    symbol = get_token_symbol(balance['denom'])
                    if symbol in ['INJ', 'USDT', 'HDRO', 'TIA', 'stINJ']:
                        key_balances[symbol] = {
                            'balance': float(balance['balance']),
                            'denom': balance['denom']
                        }
                
                return {
                    'wallet_id': wallet_id,
                    'balances': key_balances,
                    'total_tokens': len(balances)
                }
        
        return {'error': f'No balance data found for {wallet_id}'}
        
    except Exception as e:
        return {'error': f'Failed to get balance: {str(e)}'}

async def get_market_prices(market_symbol: str):
    """Get testnet and mainnet prices for a market"""
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(project_root, "config", "trader_config.json")
        
        with open(config_path, "r") as f:
            config = json.load(f)
        
        if market_symbol not in config["markets"]:
            return {'error': f'Market {market_symbol} not found in config'}
        
        market_config = config["markets"][market_symbol]
        testnet_market_id = market_config.get("testnet_market_id")
        mainnet_market_id = market_config.get("mainnet_market_id")
        
        if not testnet_market_id or not mainnet_market_id:
            return {'error': f'Market IDs not configured for {market_symbol}'}
        
        from pyinjective.async_client_v2 import AsyncClient
        from pyinjective.indexer_client import IndexerClient
        from pyinjective.core.network import Network
        
        prices = {
            'testnet_price': None,
            'mainnet_price': None,
            'price_difference': None,
            'market_symbol': market_symbol
        }
        
        try:
            testnet_network = Network.testnet()
            testnet_indexer = IndexerClient(testnet_network)
            
            if market_config.get("type") == "spot":
                testnet_orderbook = await testnet_indexer.fetch_spot_orderbook_v2(market_id=testnet_market_id, depth=10)
            else:
                testnet_orderbook = await testnet_indexer.fetch_derivative_orderbook_v2(market_id=testnet_market_id, depth=10)
            
            if testnet_orderbook and 'orderbook' in testnet_orderbook:
                buys = testnet_orderbook['orderbook'].get('buys', [])
                sells = testnet_orderbook['orderbook'].get('sells', [])
                
                if buys and sells:
                    best_buy = float(buys[0]['price'])
                    best_sell = float(sells[0]['price'])
                    prices['testnet_price'] = (best_buy + best_sell) / 2
            
        except Exception as e:
            prices['testnet_error'] = str(e)
        
        try:
            mainnet_network = Network.mainnet()
            mainnet_indexer = IndexerClient(mainnet_network)
            
            if market_config.get("type") == "spot":
                mainnet_orderbook = await mainnet_indexer.fetch_spot_orderbook_v2(market_id=mainnet_market_id, depth=10)
            else:
                mainnet_orderbook = await mainnet_indexer.fetch_derivative_orderbook_v2(market_id=mainnet_market_id, depth=10)
            
            if mainnet_orderbook and 'orderbook' in mainnet_orderbook:
                buys = mainnet_orderbook['orderbook'].get('buys', [])
                sells = mainnet_orderbook['orderbook'].get('sells', [])
                
                if buys and sells:
                    best_buy = float(buys[0]['price'])
                    best_sell = float(sells[0]['price'])
                    prices['mainnet_price'] = (best_buy + best_sell) / 2
            
        except Exception as e:
            prices['mainnet_error'] = str(e)
        
        if prices['testnet_price'] and prices['mainnet_price']:
            difference = ((prices['testnet_price'] - prices['mainnet_price']) / prices['mainnet_price']) * 100
            prices['price_difference'] = difference
        
        return prices
        
    except Exception as e:
        return {'error': f'Failed to get prices: {str(e)}'}

def get_token_symbol(denom: str) -> str:
    """Get token symbol from denomination"""
    if denom == 'inj':
        return 'INJ'
    elif 'stinj' in denom.lower():
        return 'stINJ'
    elif 'atom' in denom.lower():
        return 'ATOM'
    elif 'tia' in denom.lower():
        return 'TIA'
    elif 'usdc' in denom.lower():
        return 'USDC'
    elif 'weth' in denom.lower():
        return 'WETH'
    elif 'hdro' in denom.lower():
        return 'HDRO'
    elif 'usdt' in denom.lower() or 'peggy0x87aB3B4C8661e07D6372361211B96ed4Dc36B1B5' in denom:
        return 'USDT'
    else:
        return denom.split('/')[-1] if '/' in denom else denom

if __name__ == "__main__":
    import uvicorn
    print("Starting Trading Bot Manager (Docker-enabled)...")
    print("Access the dashboard at: http://localhost:8000")
    if DOCKER_AVAILABLE:
        print("✅ Docker connection established")
    else:
        print("⚠️ Docker not available - bot management disabled")
    uvicorn.run(app, host="0.0.0.0", port=8000)

