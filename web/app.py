#!/usr/bin/env python3
"""
Docker-Enabled Trading Bot Manager - Web Interface
Manages trading bots as Docker containers instead of processes
"""

import asyncio
import json
import os
import time
import re
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
        
        # Get host paths for volumes (from environment variables set in docker-compose.yml)
        # These are the actual host filesystem paths, not container paths
        logs_path = os.getenv("HOST_LOGS_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"))
        config_path = os.getenv("HOST_CONFIG_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config"))
        data_path = os.getenv("HOST_DATA_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
        
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
            # If a container with the same name already exists, reuse it
            try:
                existing = docker_client.containers.get(container_name)
                existing.reload()
                if existing.status != "running":
                    existing.start()
                    await asyncio.sleep(2)
                    existing.reload()
                # Register in running_bots and return success
                running_bots[request.wallet_id] = {
                    "wallet_id": request.wallet_id,
                    "bot_type": request.bot_type,
                    "market": request.market,
                    "container_id": existing.id,
                    "container_name": existing.name,
                    "container": existing,
                    "started_at": time.time(),
                    "status": existing.status,
                }
                return {
                    "success": True,
                    "message": f"Reused existing container for {request.wallet_id} on {request.market}",
                    "container_id": existing.short_id,
                }
            except docker.errors.NotFound:
                pass

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
                    "component": "bot",
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
                "wallet_id": request.wallet_id,
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

@app.get("/api/bot-logs/{wallet_id}/{bot_type}")
async def get_bot_logs(wallet_id: str, bot_type: str, username: str = Depends(verify_credentials)):
    """Get logs for a specific bot"""
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dir = os.path.join(project_root, "logs")
        
        # Determine which log file to read based on bot type
        if bot_type == "spot":
            log_file = "spot_trader.log"
        elif bot_type == "derivative":
            log_file = "derivative_trader.log"
        else:
            return {"error": f"Unknown bot type: {bot_type}"}
        
        log_path = os.path.join(log_dir, log_file)
        
        if not os.path.exists(log_path):
            return {"error": f"Log file not found: {log_file}"}
        
        logs = []
        
        try:
            with open(log_path, "r") as f:
                lines = f.readlines()
                
                # Filter logs for this specific wallet and get last 100 entries
                wallet_logs = []
                for line in lines:
                    line = line.strip()
                    if line and f'[{wallet_id}]' in line:
                        # Parse timestamp and message
                        try:
                            if '[' in line and ']' in line:
                                timestamp_end = line.find(']')
                                timestamp = line[1:timestamp_end]
                                message = line[timestamp_end + 1:].strip()
                                
                                wallet_logs.append({
                                    "timestamp": timestamp,
                                    "message": message
                                })
                        except:
                            # If parsing fails, just add the raw line
                            wallet_logs.append({
                                "timestamp": "Unknown",
                                "message": line
                            })
                
                # Get last 100 entries for this wallet
                logs = wallet_logs[-100:] if len(wallet_logs) > 100 else wallet_logs
                
        except Exception as e:
            return {"error": f"Error reading log file: {str(e)}"}
        
        return {"logs": logs}
        
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/recent-logs")
async def get_recent_logs(username: str = Depends(verify_credentials)):
    """Get recent log entries from all log files"""
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dir = os.path.join(project_root, "logs")
        
        all_logs = []
        
        # Check common log files
        log_files = [
            "derivative_trader.log",
            "spot_trader.log", 
            "trader.log",
            "enhanced_trading.log"
        ]
        
        for log_file in log_files:
            log_path = os.path.join(log_dir, log_file)
            if os.path.exists(log_path):
                try:
                    with open(log_path, "r") as f:
                        lines = f.readlines()
                        # Get last 20 lines
                        recent_lines = lines[-20:] if len(lines) > 20 else lines
                        
                        for line in recent_lines:
                            line = line.strip()
                            if line and '[' in line and ']' in line:
                                # Parse timestamp
                                try:
                                    timestamp_end = line.find(']')
                                    timestamp = line[1:timestamp_end]
                                    message = line[timestamp_end + 1:].strip()
                                    
                                    all_logs.append({
                                        "timestamp": timestamp,
                                        "message": message,
                                        "source": log_file
                                    })
                                except:
                                    pass
                except Exception as e:
                    print(f"Error reading {log_file}: {e}")
        
        # Sort by timestamp (newest first) and limit to last 50
        all_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return {"logs": all_logs[:50]}
        
    except Exception as e:
        return {"error": str(e)}

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
    """Get testnet and mainnet prices for a market.
    First try to parse from bot logs (fast, same as bots). If not found, fallback to Indexer gRPC.
    """
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

        # 1) Try to read latest prices from logs
        try:
            log_file = "spot_trader.log" if market_config.get("type") == "spot" else "derivative_trader.log"
            log_path = os.path.join(project_root, "logs", log_file)
            if os.path.exists(log_path):
                with open(log_path, "r") as f:
                    lines = f.readlines()[-500:]
                # Scan from end for the most recent matching line
                for line in reversed(lines):
                    if market_symbol in line and "Mainnet:" in line and "Testnet:" in line:
                        # Pattern: Mainnet: $9.5675 | Testnet: $9.5840
                        m = re.search(r"Mainnet:\s*\$(\d+(?:\.\d+)?)\s*\|\s*Testnet:\s*\$(\d+(?:\.\d+)?)", line)
                        if not m:
                            # Pattern swapped
                            m = re.search(r"Testnet:\s*\$(\d+(?:\.\d+)?)\s*\|\s*Mainnet:\s*\$(\d+(?:\.\d+)?)", line)
                            if m:
                                prices['testnet_price'] = float(m.group(1))
                                prices['mainnet_price'] = float(m.group(2))
                        else:
                            prices['mainnet_price'] = float(m.group(1))
                            prices['testnet_price'] = float(m.group(2))
                        if prices['testnet_price'] and prices['mainnet_price']:
                            break
        except Exception as e:
            prices['log_parse_error'] = str(e)
        
        # 2) Fallback: gRPC (only if missing from logs)
        try:
            import httpx
            from pyinjective.client.model.pagination import PaginationOption
            testnet_network = Network.testnet()
            # Use recommended gRPC endpoints
            testnet_network.grpc_exchange_endpoint = "k8s.testnet.exchange.grpc.injective.network:443"
            testnet_network.grpc_indexer_endpoint = "k8s.testnet.indexer.grpc.injective.network:443"
            testnet_indexer = IndexerClient(testnet_network)

            # Prefer last trade price (matches bots). Fallback to orderbook mid.
            if market_config.get("type") == "spot" and prices['testnet_price'] is None:
                # 1) gRPC trades (same as bots)
                try:
                    trades = await testnet_indexer.fetch_spot_trades(
                        market_ids=[testnet_market_id],
                        pagination=PaginationOption(limit=1)
                    )
                    trade_list = trades.get('trades') or trades.get('spot_trades') or []
                    if trade_list:
                        prices['testnet_price'] = float(trade_list[0].get('price') or trade_list[0].get('execution_price'))
                except Exception:
                    pass
                # 2) REST trades (backup)
                if prices['testnet_price'] is None:
                    rest_url = "https://k8s.testnet.indexer.injective.network/api/v2/spot/trades"
                    async with httpx.AsyncClient(timeout=5) as client:
                        r = await client.get(rest_url, params={"marketId": testnet_market_id, "limit": 1})
                        if r.status_code == 200:
                            j = r.json()
                            trade_list = j.get('trades') or j.get('spot_trades') or []
                            if trade_list:
                                prices['testnet_price'] = float(trade_list[0].get('price') or trade_list[0].get('execution_price'))
                # 3) gRPC orderbook mid (last resort)
                if prices['testnet_price'] is None:
                    try:
                        ob = await testnet_indexer.fetch_spot_orderbook_v2(market_id=testnet_market_id, depth=10)
                        if ob:
                            buys = ob.get('buys', [])
                            sells = ob.get('sells', [])
                            if buys and sells:
                                prices['testnet_price'] = (float(buys[0]['price']) + float(sells[0]['price'])) / 2
                    except Exception:
                        pass
            elif market_config.get("type") != "spot" and prices['testnet_price'] is None:
                # 1) gRPC trades
                try:
                    trades = await testnet_indexer.fetch_derivative_trades(
                        market_ids=[testnet_market_id],
                        pagination=PaginationOption(limit=1)
                    )
                    trade_list = trades.get('trades') or trades.get('derivative_trades') or []
                    if trade_list:
                        prices['testnet_price'] = float(trade_list[0].get('price') or trade_list[0].get('execution_price'))
                except Exception:
                    pass
                # 2) REST trades (backup)
                if prices['testnet_price'] is None:
                    try:
                        rest_url = "https://k8s.testnet.indexer.injective.network/api/v2/derivative/trades"
                        async with httpx.AsyncClient(timeout=5) as client:
                            r = await client.get(rest_url, params={"marketId": testnet_market_id, "limit": 1})
                            if r.status_code == 200:
                                j = r.json()
                                trade_list = j.get('trades') or j.get('derivative_trades') or []
                                if trade_list:
                                    prices['testnet_price'] = float(trade_list[0].get('price') or trade_list[0].get('execution_price'))
                    except Exception:
                        pass
                if prices['testnet_price'] is None:
                    try:
                        ob = await testnet_indexer.fetch_derivative_orderbook_v2(market_id=testnet_market_id, depth=10)
                        if ob:
                            buys = ob.get('buys', [])
                            sells = ob.get('sells', [])
                            if buys and sells:
                                prices['testnet_price'] = (float(buys[0]['price']) + float(sells[0]['price'])) / 2
                    except Exception:
                        pass
            
        except Exception as e:
            prices['testnet_error'] = str(e)
        
        try:
            import httpx
            from pyinjective.client.model.pagination import PaginationOption
            mainnet_network = Network.mainnet()
            mainnet_indexer = IndexerClient(mainnet_network)

            if market_config.get("type") == "spot":
                # 1) gRPC trades first (like bots)
                try:
                    trades = await mainnet_indexer.fetch_spot_trades(
                        market_ids=[mainnet_market_id],
                        pagination=PaginationOption(limit=1)
                    )
                    trade_list = trades.get('trades') or trades.get('spot_trades') or []
                    if trade_list:
                        prices['mainnet_price'] = float(trade_list[0].get('price') or trade_list[0].get('execution_price'))
                except Exception:
                    pass
                # 2) REST trades (backup)
                if prices['mainnet_price'] is None:
                    try:
                        rest_url = "https://k8s.indexer.injective.network/api/v2/spot/trades"
                        async with httpx.AsyncClient(timeout=5) as client:
                            r = await client.get(rest_url, params={"marketId": mainnet_market_id, "limit": 1})
                            if r.status_code == 200:
                                j = r.json()
                                trade_list = j.get('trades') or j.get('spot_trades') or []
                                if trade_list:
                                    prices['mainnet_price'] = float(trade_list[0].get('price') or trade_list[0].get('execution_price'))
                    except Exception:
                        pass
                if prices['mainnet_price'] is None:
                    try:
                        ob = await mainnet_indexer.fetch_spot_orderbook_v2(market_id=mainnet_market_id, depth=10)
                        if ob:
                            buys = ob.get('buys', [])
                            sells = ob.get('sells', [])
                            if buys and sells:
                                prices['mainnet_price'] = (float(buys[0]['price']) + float(sells[0]['price'])) / 2
                    except Exception:
                        pass
            else:
                # 1) gRPC trades
                try:
                    trades = await mainnet_indexer.fetch_derivative_trades(
                        market_ids=[mainnet_market_id],
                        pagination=PaginationOption(limit=1)
                    )
                    trade_list = trades.get('trades') or trades.get('derivative_trades') or []
                    if trade_list:
                        prices['mainnet_price'] = float(trade_list[0].get('price') or trade_list[0].get('execution_price'))
                except Exception:
                    pass
                # 2) REST trades
                if prices['mainnet_price'] is None:
                    try:
                        rest_url = "https://k8s.indexer.injective.network/api/v2/derivative/trades"
                        async with httpx.AsyncClient(timeout=5) as client:
                            r = await client.get(rest_url, params={"marketId": mainnet_market_id, "limit": 1})
                            if r.status_code == 200:
                                j = r.json()
                                trade_list = j.get('trades') or j.get('derivative_trades') or []
                                if trade_list:
                                    prices['mainnet_price'] = float(trade_list[0].get('price') or trade_list[0].get('execution_price'))
                    except Exception:
                        pass
                if prices['mainnet_price'] is None:
                    try:
                        ob = await mainnet_indexer.fetch_derivative_orderbook_v2(market_id=mainnet_market_id, depth=10)
                        if ob:
                            buys = ob.get('buys', [])
                            sells = ob.get('sells', [])
                            if buys and sells:
                                prices['mainnet_price'] = (float(buys[0]['price']) + float(sells[0]['price'])) / 2
                    except Exception:
                        pass
            
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

def rediscover_running_bots():
    """Rediscover bot containers that are already running on startup"""
    if not DOCKER_AVAILABLE:
        return
    
    try:
        # Find all containers with app=trading-bot label
        containers = docker_client.containers.list(
            filters={"label": "app=trading-bot"}
        )
        
        for container in containers:
            try:
                # Skip the web dashboard itself
                if "web" in container.name or "dashboard" in container.name:
                    continue
                
                labels = container.labels
                wallet_id = labels.get("wallet_id")
                market = labels.get("market")
                bot_type = labels.get("bot_type")
                
                if wallet_id and market and bot_type:
                    # Parse started_at timestamp
                    started_at_str = container.attrs.get("State", {}).get("StartedAt", "")
                    try:
                        # Parse ISO format timestamp from Docker
                        from dateutil import parser as date_parser
                        started_at_dt = date_parser.parse(started_at_str)
                        started_at_timestamp = started_at_dt.timestamp()
                    except:
                        # Fallback to current time if parsing fails
                        started_at_timestamp = time.time()
                    
                    # Add to running_bots
                    running_bots[wallet_id] = {
                        "wallet_id": wallet_id,
                        "market": market,
                        "bot_type": bot_type,
                        "container_id": container.id,
                        "container": container,
                        "container_name": container.name,
                        "started_at": started_at_timestamp,
                        "status": container.status
                    }
                    print(f"✅ Rediscovered {bot_type} bot: {wallet_id} → {market} (container: {container.name})")
            except Exception as e:
                print(f"⚠️ Error processing container {container.id}: {e}")
        
        if running_bots:
            print(f"🔄 Rediscovered {len(running_bots)} running bot(s)")
        else:
            print("ℹ️ No existing bots found")
            
    except Exception as e:
        print(f"⚠️ Error rediscovering bots: {e}")

if __name__ == "__main__":
    import uvicorn
    print("Starting Trading Bot Manager (Docker-enabled)...")
    print("Access the dashboard at: http://localhost:8000")
    if DOCKER_AVAILABLE:
        print("✅ Docker connection established")
        # Rediscover any already-running bots
        rediscover_running_bots()
    else:
        print("⚠️ Docker not available - bot management disabled")
    uvicorn.run(app, host="0.0.0.0", port=8000)

