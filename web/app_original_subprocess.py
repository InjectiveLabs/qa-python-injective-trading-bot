#!/usr/bin/env python3
"""
Simple Trading Bot Manager - Web Interface
Clean, Web 1.0 style interface for managing spot and derivative trading bots
"""

import asyncio
import json
import os
import subprocess
import time
import signal
import secrets
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

# Load authentication credentials from environment variables
# Default: admin/admin (change via .env: WEB_AUTH_USERNAME and WEB_AUTH_PASSWORD)
AUTH_USERNAME = os.getenv("WEB_AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("WEB_AUTH_PASSWORD", "admin")

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Verify HTTP Basic Authentication credentials.
    
    Browser will cache credentials after first login, so user only sees
    the popup ONCE when they first access the dashboard.
    """
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
    pid: int

# Global state for tracking running bots
running_bots = {}  # wallet_id -> bot_info

@app.get("/")
async def get_dashboard(username: str = Depends(verify_credentials)):
    """Serve the main dashboard page - protected by HTTP Basic Auth"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    static_file_path = os.path.join(script_dir, "static", "index.html")
    
    with open(static_file_path, "r") as f:
        return HTMLResponse(f.read())

@app.get("/static/{file_path:path}")
async def static_files(file_path: str, username: str = Depends(verify_credentials)):
    """Serve static files"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    static_file_path = os.path.join(script_dir, "static", file_path)
    
    if not os.path.exists(static_file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(static_file_path)

@app.get("/api/wallets")
async def get_wallets(username: str = Depends(verify_credentials)):
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
async def get_markets(username: str = Depends(verify_credentials)):
    """Get available markets organized by type"""
    try:
        # Load trader config to get market information
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

@app.get("/api/debug/running-bots")
async def debug_running_bots(username: str = Depends(verify_credentials)):
    """Debug endpoint to check running bots data"""
    return {
        "running_bots_dict": running_bots,
        "running_bots_count": len(running_bots),
        "current_time": time.time()
    }

@app.get("/api/running-bots")
async def get_running_bots(username: str = Depends(verify_credentials)):
    """Get currently running bots with enhanced information"""
    try:
        # Update running bots status by checking processes
        await update_running_bots_status()
        
        bots = []
        for wallet_id, bot_info in running_bots.items():
            # Calculate uptime (fix the refresh issue)
            current_time = time.time()
            uptime_seconds = current_time - bot_info["started_at"]
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            seconds = int(uptime_seconds % 60)
            uptime = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            
            print(f"DEBUG: Bot {wallet_id} - Started: {bot_info['started_at']}, Current: {current_time}, Uptime: {uptime}")
            
            # Get wallet balance (with error handling)
            wallet_balance = None
            try:
                wallet_balance = await get_wallet_balance(wallet_id)
                print(f"DEBUG: Wallet balance for {wallet_id}: {wallet_balance}")
            except Exception as e:
                print(f"DEBUG: Error getting wallet balance for {wallet_id}: {e}")
                wallet_balance = {'error': f'Balance check failed: {str(e)}'}
            
            # Get market prices (with error handling)  
            market_prices = None
            try:
                market_prices = await get_market_prices(bot_info["market"])
                print(f"DEBUG: Market prices for {bot_info['market']}: {market_prices}")
            except Exception as e:
                print(f"DEBUG: Error getting market prices for {bot_info['market']}: {e}")
                market_prices = {'error': f'Price check failed: {str(e)}'}
            
            bots.append({
                "wallet_id": wallet_id,
                "bot_type": bot_info["bot_type"],
                "market": bot_info["market"],
                "pid": bot_info["pid"],
                "started_at": datetime.fromtimestamp(bot_info["started_at"]).isoformat(),
                "uptime": uptime,
                "wallet_balance": wallet_balance,
                "market_prices": market_prices
            })
        
        return {"bots": bots}
    except Exception as e:
        print(f"DEBUG: Error in get_running_bots: {e}")
        return {"error": str(e)}

@app.post("/api/start-bot")
async def start_bot(request: StartBotRequest, username: str = Depends(verify_credentials)):
    """Start a trading bot"""
    try:
        # Check if wallet is already in use
        if request.wallet_id in running_bots:
            return {"success": False, "error": f"Wallet {request.wallet_id} is already in use"}
        
        # Determine script to run
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        if request.bot_type == "spot":
            script_path = os.path.join(project_root, "spot_trader.py")
            cmd = ["python", script_path, request.wallet_id, request.market]
        elif request.bot_type == "derivative":
            script_path = os.path.join(project_root, "derivative_trader.py")
            cmd = ["python", script_path, request.wallet_id, "--markets", request.market]
        else:
            return {"success": False, "error": f"Invalid bot type: {request.bot_type}"}
        
        # Check if script exists
        if not os.path.exists(script_path):
            return {"success": False, "error": f"Script not found: {script_path}"}
        
        # Start the process
        process = subprocess.Popen(
            cmd,
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait a moment to ensure process starts
        await asyncio.sleep(2)
        
        # Check if process is still running
        if process.poll() is not None:
            # Process died, get error output
            stdout, stderr = process.communicate()
            error_msg = stderr.decode() if stderr else stdout.decode()
            return {"success": False, "error": f"Bot failed to start: {error_msg}"}
        
        # Store bot info
        running_bots[request.wallet_id] = {
            "bot_type": request.bot_type,
            "market": request.market,
            "pid": process.pid,
            "process": process,
            "started_at": time.time()
        }
        
        return {
            "success": True, 
            "message": f"{request.bot_type.title()} trader started for {request.wallet_id} on {request.market}"
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/stop-bot")
async def stop_bot(request: StopBotRequest, username: str = Depends(verify_credentials)):
    """Stop a specific trading bot"""
    try:
        if request.wallet_id not in running_bots:
            return {"success": False, "error": f"No bot running for wallet {request.wallet_id}"}
        
        bot_info = running_bots[request.wallet_id]
        
        # Verify PID matches
        if bot_info["pid"] != request.pid:
            return {"success": False, "error": "PID mismatch, bot may have restarted"}
        
        # Try to terminate the process gracefully
        try:
            process = bot_info["process"]
            process.terminate()
            
            # Wait up to 5 seconds for graceful shutdown
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't stop gracefully
                process.kill()
                process.wait()
                
        except ProcessLookupError:
            # Process already dead
            pass
        
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
                                    # If parsing fails, just add the raw line
                                    all_logs.append({
                                        "timestamp": "Unknown",
                                        "message": line,
                                        "source": log_file
                                    })
                except Exception as e:
                    print(f"Error reading {log_file}: {e}")
        
        # Sort by timestamp (most recent first) and limit to 50 entries
        all_logs.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return {"logs": all_logs[:50]}
        
    except Exception as e:
        return {"error": str(e)}

async def get_wallet_balance(wallet_id: str):
    """Get balance information for a specific wallet"""
    try:
        # Import with correct path
        import sys
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.append(project_root)
        
        from utils.balance_checker import BalanceChecker
        
        checker = BalanceChecker()
        all_balances = await checker.check_all_wallets_all_tokens()
        
        # Find balance for this wallet
        for wallet_balance in all_balances:
            if wallet_balance.get('wallet_id') == wallet_id:
                balances = wallet_balance.get('balances', [])
                
                # Get key balances (INJ, USDT, HDRO, TIA, stINJ)
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

async def get_market_metadata(market_id: str, network_type: str = "testnet"):
    """Get market metadata including base and quote decimals"""
    try:
        from pyinjective.indexer_client import IndexerClient
        from pyinjective.core.network import Network
        
        network = Network.testnet() if network_type == "testnet" else Network.mainnet()
        indexer = IndexerClient(network)
        
        market = await indexer.fetch_spot_market(market_id=market_id)
        
        if market and 'market' in market:
            market_data = market['market']
            
            # Get decimals from tokenMeta objects
            base_decimals = 18  # default
            quote_decimals = 6  # default
            
            if 'baseTokenMeta' in market_data:
                base_decimals = int(market_data['baseTokenMeta'].get('decimals', 18))
            if 'quoteTokenMeta' in market_data:
                quote_decimals = int(market_data['quoteTokenMeta'].get('decimals', 6))
            
            return {
                'base_decimals': base_decimals,
                'quote_decimals': quote_decimals,
                'decimal_diff': base_decimals - quote_decimals
            }
    except Exception as e:
        print(f"Failed to get market metadata: {e}")
        
    # Fallback for known markets
    if "HDRO/INJ" in market_id or market_id in ["0xd8e9ea042ac67990134d8e024a251809b1b76c5f7df49f511858e040a285efca", "0xc8fafa1fcab27e16da20e98b4dc9dda45320418c27db80663b21edac72f3b597"]:
        return {'base_decimals': 6, 'quote_decimals': 18, 'decimal_diff': -12}
    elif "INJ/USDT" in market_id or market_id in ["0x0611780ba69656949525013d947713300f56c37b6175e02f26bffa495c3208fe", "0xa508cb32923323679f29a032c70342c147c17d0145625922b0ef22e955c844c0"]:
        return {'base_decimals': 18, 'quote_decimals': 6, 'decimal_diff': 12}
    elif "TIA/USDT" in market_id or market_id in ["0xa283fc94a9055a01a58bb6229b1e56a8bb54069a0debfce7fbd1e6c25a95330c", "0x35fd4fa9291ea68ce5eef6e0ea8567c7744c1891c2059ef08580ba2e7a31f101"]:
        return {'base_decimals': 6, 'quote_decimals': 6, 'decimal_diff': 0}
    elif "stINJ/INJ" in market_id or market_id in ["0xf02752c2c87728af7fd10a298a8a645261859eafd0295dcda7e2c5b45c8412cf", "0xce1829d4942ed939580e72e66fd8be3502396fc840b6d12b2d676bdb86542363"]:
        return {'base_decimals': 18, 'quote_decimals': 18, 'decimal_diff': 0}
    
    # Default fallback
    return {'base_decimals': 18, 'quote_decimals': 6, 'decimal_diff': 12}

async def get_market_prices(market_symbol: str):
    """Get testnet and mainnet prices for a market"""
    try:
        # Load market configuration to get market IDs
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
        
        # Import price checking utilities
        from pyinjective.async_client_v2 import AsyncClient
        from pyinjective.indexer_client import IndexerClient
        from pyinjective.core.network import Network
        
        prices = {
            'testnet_price': None,
            'mainnet_price': None,
            'price_difference': None,
            'market_symbol': market_symbol
        }
        
        # Get market metadata for proper scaling
        testnet_metadata = await get_market_metadata(testnet_market_id, "testnet")
        mainnet_metadata = await get_market_metadata(mainnet_market_id, "mainnet")
        
        try:
            # Get testnet price using IndexerClient
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
                    
                    # Scale prices properly based on token decimals
                    if market_config.get("type") == "spot":
                        # Apply proper scaling: 10^(base_decimals - quote_decimals)
                        scale_factor = 10 ** testnet_metadata['decimal_diff']
                        best_buy *= scale_factor
                        best_sell *= scale_factor
                    else:
                        # Derivative prices need different scaling
                        best_buy /= 1e6
                        best_sell /= 1e6
                    
                    prices['testnet_price'] = (best_buy + best_sell) / 2
            
        except Exception as e:
            prices['testnet_error'] = str(e)
        
        try:
            # Get mainnet price using IndexerClient
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
                    
                    # Scale prices properly based on token decimals
                    if market_config.get("type") == "spot":
                        # Apply proper scaling: 10^(base_decimals - quote_decimals)
                        scale_factor = 10 ** mainnet_metadata['decimal_diff']
                        best_buy *= scale_factor
                        best_sell *= scale_factor
                    else:
                        # Mainnet derivative prices need to be divided by 10^6
                        best_buy /= 1e6
                        best_sell /= 1e6
                    
                    prices['mainnet_price'] = (best_buy + best_sell) / 2
            
        except Exception as e:
            prices['mainnet_error'] = str(e)
        
        # Calculate price difference
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

async def update_running_bots_status():
    """Update the status of running bots by checking if processes are still alive"""
    dead_bots = []
    
    for wallet_id, bot_info in running_bots.items():
        try:
            # Check if process is still running using ps command
            result = subprocess.run(
                ["ps", "-p", str(bot_info["pid"])], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            
            if result.returncode != 0:
                # Process is dead
                print(f"DEBUG: Bot {wallet_id} (PID {bot_info['pid']}) is no longer running")
                dead_bots.append(wallet_id)
            else:
                print(f"DEBUG: Bot {wallet_id} (PID {bot_info['pid']}) is still running")
                
        except Exception as e:
            print(f"DEBUG: Error checking process for {wallet_id}: {e}")
            # Assume it's dead if we can't check
            dead_bots.append(wallet_id)
    
    # Remove dead bots from tracking
    for wallet_id in dead_bots:
        print(f"DEBUG: Removing dead bot {wallet_id}")
        del running_bots[wallet_id]

if __name__ == "__main__":
    import uvicorn
    print("=" * 70)
    print("🚀 Trading Bot Manager - Starting...")
    print("=" * 70)
    print()
    print(f"📊 Dashboard URL: http://localhost:8000")
    print()
    print("🔐 Authentication: HTTP Basic Auth")
    print(f"   👤 Username: {AUTH_USERNAME}")
    print(f"   🔑 Password: {'*' * len(AUTH_PASSWORD)}")
    print()
    if AUTH_USERNAME == "admin" and AUTH_PASSWORD == "admin":
        print("⚠️  WARNING: Using default credentials!")
        print("   Set WEB_AUTH_USERNAME and WEB_AUTH_PASSWORD in .env file")
        print()
    print("ℹ️  Browser will show login popup ONCE when you first open the page.")
    print("   After login, credentials are cached - you won't see popup again!")
    print()
    print("=" * 70)
    uvicorn.run(app, host="0.0.0.0", port=8000)