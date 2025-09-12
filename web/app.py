#!/usr/bin/env python3
"""
Injective Trading Bot - Operational Dashboard
A simple, clean web interface for monitoring and controlling the trading bot
"""

import asyncio
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add parent directory to path to import from utils
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.secure_wallet_loader import load_wallets_from_env

# Token name mapping for better readability
TOKEN_NAMES = {
    'inj': 'INJ',
    'factory/inj17gkuet8f6pssxd8nycm3qr9d9y699rupv6397z/stinj': 'stINJ (Staked INJ)',
    'factory/inj17vytdwqczqz72j65saukplrktd4gyfme5agf6c/atom': 'ATOM',
    'factory/inj17vytdwqczqz72j65saukplrktd4gyfme5agf6c/tia': 'TIA',
    'factory/inj17vytdwqczqz72j65saukplrktd4gyfme5agf6c/usdc': 'USDC',
    'factory/inj17vytdwqczqz72j65saukplrktd4gyfme5agf6c/weth': 'WETH',
    'factory/inj1pk7jhvjj2lufcghmvr7gl49dzwkk3xj0uqkwfk/hdro': 'HDRO',
    'peggy0x87aB3B4C8661e07D6372361211B96ed4Dc36B1B5': 'USDT (Peggy)'
}

def get_token_display_name(denom: str) -> str:
    """Get a human-readable token name"""
    return TOKEN_NAMES.get(denom, denom)

def get_token_symbol(denom: str) -> str:
    """Get token symbol from denomination"""
    if denom == 'inj':
        return 'INJ'
    elif 'stinj' in denom:
        return 'stINJ'
    elif 'atom' in denom:
        return 'ATOM'
    elif 'tia' in denom:
        return 'TIA'
    elif 'usdc' in denom:
        return 'USDC'
    elif 'weth' in denom:
        return 'WETH'
    elif 'hdro' in denom:
        return 'HDRO'
    elif 'usdt' in denom.lower() or 'peggy0x87aB3B4C8661e07D6372361211B96ed4Dc36B1B5' in denom:
        return 'USDT'
    else:
        return denom.split('/')[-1] if '/' in denom else denom

app = FastAPI(title="Injective Trading Bot Dashboard")

# Mount static files with no-cache headers
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

@app.get("/static/{file_path:path}")
async def static_files(file_path: str):
    """Serve static files with no-cache headers"""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    static_file_path = os.path.join(script_dir, "static", file_path)
    
    response = FileResponse(static_file_path)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Global state
bot_status = {
    "running": False,
    "started_at": None,
    "process": None
}

# Cached configuration data
cached_config = {
    "wallets": None,
    "markets": None,
    "last_updated": None
}

# WebSocket connections
active_connections = []

class BotControl(BaseModel):
    action: str  # "start" or "stop"

def load_cached_config():
    """Load and cache wallet and market configuration"""
    global cached_config
    
    # Check if we need to reload (every 30 seconds or if not cached)
    current_time = time.time()
    if (cached_config["last_updated"] is None or 
        current_time - cached_config["last_updated"] > 30):
        
        try:
            # Load wallet configuration (this will print the wallet loading messages)
            wallets_config = load_wallets_from_env()
            enabled_wallets = [w for w in wallets_config['wallets'] if w.get('enabled', False)]
            
            # Load market configuration
            # Get the project root directory (parent of web directory)
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            markets_config_path = os.path.join(project_root, 'config', 'markets_config.json')
            with open(markets_config_path, 'r') as f:
                markets_config = json.load(f)
            enabled_markets = [m for m in markets_config['markets'].values() if m.get('enabled', False)]
            
            # Cache the data
            cached_config["wallets"] = {
                "enabled": len(enabled_wallets),
                "total": len(wallets_config['wallets']),
                "list": [{"id": w['id'], "name": w['name']} for w in enabled_wallets]
            }
            
            cached_config["markets"] = {
                "enabled": len(enabled_markets),
                "list": [{"symbol": k, "type": v.get('type', 'unknown')} for k, v in markets_config['markets'].items() if v.get('enabled', False)]
            }
            
            cached_config["last_updated"] = current_time
            print(f"Configuration cached at {datetime.now().strftime('%H:%M:%S')}")
            
        except Exception as e:
            print(f"Error loading configuration: {e}")
            # Keep existing cached data if loading fails
    
    return cached_config["wallets"], cached_config["markets"]

def force_refresh_config():
    """Force refresh the cached configuration"""
    global cached_config
    cached_config["last_updated"] = None
    return load_cached_config()

@app.get("/")
async def get_dashboard():
    """Serve the main dashboard page"""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    static_file_path = os.path.join(script_dir, "static", "index.html")
    
    with open(static_file_path, "r") as f:
        response = HTMLResponse(f.read())
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

@app.get("/api/config")
async def get_config():
    """Get configuration information (loads fresh data)"""
    try:
        # Force load configuration
        wallets_data, markets_data = force_refresh_config()
        
        return {
            "wallets": wallets_data or {"enabled": 0, "total": 0, "list": []},
            "markets": markets_data or {"enabled": 0, "list": []},
            "loaded_at": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/balances")
async def get_balances():
    """Get real-time wallet balances and token information"""
    try:
        # Import the balance checker
        from utils.balance_checker import BalanceChecker
        
        # Load wallet configuration
        wallets_data = load_wallets_from_env()
        if not wallets_data or 'wallets' not in wallets_data:
            return {"error": "No wallets configured"}
        
        # Get balances for each enabled wallet
        balances = {}
        total_value_usd = 0
        
        # Create a single BalanceChecker instance
        checker = BalanceChecker()
        
        try:
            # Get all wallet balances at once
            all_wallet_balances = await checker.check_all_wallets_all_tokens()
            
            # Convert list to dictionary for easier lookup
            wallet_balance_dict = {}
            for wallet_balance in all_wallet_balances:
                wallet_id = wallet_balance.get('wallet_id')
                if wallet_id:
                    wallet_balance_dict[wallet_id] = wallet_balance
            
            for wallet in wallets_data['wallets']:
                if not wallet.get('enabled', False):
                    continue
                
                wallet_id = wallet['id']
                if wallet_id in wallet_balance_dict:
                    wallet_data = wallet_balance_dict[wallet_id]
                    tokens = wallet_data.get('balances', [])
                    
                    # Convert balance format for frontend
                    formatted_tokens = []
                    for token in tokens:
                        formatted_token = {
                            'symbol': get_token_symbol(token['denom']),
                            'name': get_token_display_name(token['denom']),
                            'balance': token['balance'],
                            'denom': token['denom']
                        }
                        formatted_tokens.append(formatted_token)
                    
                    balances[wallet_id] = {
                        "name": wallet['name'],
                        "tokens": formatted_tokens,
                        "total_tokens": len(formatted_tokens),
                        "last_updated": datetime.now().isoformat()
                    }
                    
                    # Calculate total USD value (if we have price data)
                    for token in formatted_tokens:
                        if 'usd_value' in token and token['usd_value']:
                            total_value_usd += float(token['usd_value'])
                else:
                    balances[wallet_id] = {
                        "name": wallet['name'],
                        "error": "No balance data available",
                        "last_updated": datetime.now().isoformat()
                    }
            
            # BalanceChecker doesn't need cleanup
            
        except Exception as e:
            # If there's an error, create error entries for all wallets
            for wallet in wallets_data['wallets']:
                if wallet.get('enabled', False):
                    balances[wallet['id']] = {
                        "name": wallet['name'],
                        "error": str(e),
                        "last_updated": datetime.now().isoformat()
                    }
        
        return {
            "wallets": balances,
            "total_value_usd": total_value_usd,
            "last_updated": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/open-orders")
async def get_open_orders():
    """Get open orders count for each wallet"""
    try:
        # Import the check open orders utility
        from utils.check_open_orders import get_open_orders_data
        
        # Get open orders data
        orders_data = await get_open_orders_data()
        
        if "error" in orders_data:
            return orders_data
        
        # Format for frontend
        wallet_orders = {}
        total_orders = 0
        
        for wallet_info in orders_data.get('wallets', []):
            wallet_id = wallet_info.get('wallet_id')
            wallet_name = wallet_info.get('wallet_name')
            markets = wallet_info.get('markets', [])
            
            wallet_total = 0
            market_orders = {}
            
            for market_info in markets:
                market_id = market_info.get('market_id')
                spot_orders = market_info.get('spot_orders', [])
                derivative_orders = market_info.get('derivative_orders', [])
                
                market_total = len(spot_orders) + len(derivative_orders)
                wallet_total += market_total
                
                # Always include market data with actual order details
                market_orders[market_id] = {
                    'spot': len(spot_orders),
                    'derivative': len(derivative_orders),
                    'total': market_total,
                    'spot_orders': spot_orders,  # Include actual order data
                    'derivative_orders': derivative_orders  # Include actual order data
                }
            
            wallet_orders[wallet_id] = {
                'name': wallet_name,
                'total_orders': wallet_total,
                'markets': market_orders,
                'last_updated': datetime.now().isoformat()
            }
            
            total_orders += wallet_total
        
        return {
            "wallets": wallet_orders,
            "total_orders": total_orders,
            "last_updated": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/logs/full")
async def get_full_logs():
    """Get the full trading log file"""
    try:
        # Get the project root directory (parent of web directory)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_file = Path(os.path.join(project_root, "logs", "trading.log"))
        if not log_file.exists():
            return {"error": "Log file not found"}
        
        # Read the entire log file
        with open(log_file, 'r') as f:
            content = f.read()
        
        # Return as plain text
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content, media_type="text/plain")
        
    except Exception as e:
        return {"error": f"Failed to read log file: {str(e)}"}

@app.get("/api/status")
async def get_status():
    """Get current bot status and system information"""
    try:
        # Check if bot is actually running by looking for the process
        actual_running = is_bot_process_running()
        
        # Update bot_status if there's a mismatch
        if bot_status["running"] != actual_running:
            print(f"Bot status mismatch detected: tracked={bot_status['running']}, actual={actual_running}")
            bot_status["running"] = actual_running
            if not actual_running:
                bot_status["started_at"] = None
                bot_status["process"] = None
        
        # Only load configuration if bot is running or if we don't have cached data
        if bot_status["running"] or cached_config["wallets"] is None:
            wallets_data, markets_data = load_cached_config()
        else:
            # Use cached data when bot is not running
            wallets_data = cached_config["wallets"]
            markets_data = cached_config["markets"]
        
        # Get recent logs (increased from 10 to 50 for more detail)
        recent_logs = get_recent_logs(50)
        
        return {
            "bot": {
                "running": bot_status["running"],
                "started_at": bot_status["started_at"],
                "uptime": get_uptime() if bot_status["running"] else None,
                "network": "Testnet"
            },
            "wallets": wallets_data or {"enabled": 0, "total": 0, "list": []},
            "markets": markets_data or {"enabled": 0, "list": []},
            "logs": recent_logs
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/control")
async def control_bot(control: BotControl):
    """Start or stop the trading bot"""
    global bot_status
    
    if control.action == "start" and not bot_status["running"]:
        try:
            # Start the bot
            process = subprocess.Popen([
                "python", "scripts/multi_wallet_trader.py"
            ], cwd=os.path.dirname(os.path.dirname(__file__)))
            
            # Wait a moment to ensure the process starts
            import time
            time.sleep(2)
            
            # Verify the process is actually running
            if is_bot_process_running():
                bot_status["running"] = True
                bot_status["started_at"] = datetime.now().isoformat()
                bot_status["process"] = process
                print(f"Bot started successfully with PID: {process.pid}")
            else:
                print("Bot process failed to start properly")
                return {"success": False, "error": "Bot process failed to start"}
            
            # Force refresh configuration when bot starts
            force_refresh_config()
            
            # Notify all connected clients immediately
            await broadcast_status_update()
            
            return {"success": True, "message": "Bot started successfully"}
            
        except Exception as e:
            print(f"Error starting bot: {e}")
            return {"success": False, "error": str(e)}
    
    elif control.action == "stop":
        try:
            # Stop all bot processes - use multiple methods to ensure they stop
            stopped = False
            
            # Method 1: Try to stop the tracked process gracefully
            if bot_status["process"]:
                process = bot_status["process"]
                try:
                    process.terminate()
                    process.wait(timeout=3)
                    stopped = True
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                        process.wait(timeout=3)
                        stopped = True
                    except:
                        pass
            
            # Method 2: Kill all bot processes using pkill
            if kill_all_bot_processes():
                stopped = True
            
            # Method 3: Wait a moment and check if any processes are still running
            import time
            time.sleep(1)
            if is_bot_process_running():
                # Force kill with SIGKILL
                subprocess.run(["pkill", "-9", "-f", "multi_wallet_trader.py"], 
                             capture_output=True, timeout=5)
            
            bot_status["running"] = False
            bot_status["started_at"] = None
            bot_status["process"] = None
            
            # Force refresh configuration when bot stops
            force_refresh_config()
            
            # Notify all connected clients immediately
            await broadcast_status_update()
            
            return {"success": True, "message": "Bot stopped successfully"}
            
        except Exception as e:
            # Even if there's an error, mark as stopped
            bot_status["running"] = False
            bot_status["started_at"] = None
            bot_status["process"] = None
            await broadcast_status_update()
            return {"success": False, "error": f"Error stopping bot: {str(e)}"}
    
    else:
        return {"success": False, "error": "Invalid action or bot already in requested state"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await websocket.accept()
    active_connections.append(websocket)
    
    try:
        while True:
            try:
                # Send periodic status updates
                status = await get_status()
                status["websocket_timestamp"] = asyncio.get_event_loop().time()
                
                # Send updates more frequently when bot is running, less when stopped
                if status["bot"]["running"]:
                    await websocket.send_json(status)
                    await asyncio.sleep(1)  # Update every 1 second when bot is running
                else:
                    await websocket.send_json(status)
                    await asyncio.sleep(5)  # Update every 5 seconds when bot is stopped
                    
            except Exception as e:
                # Handle any errors during sending
                print(f"WebSocket send error: {e}")
                break
                
    except WebSocketDisconnect:
        pass  # Client disconnected normally
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        # Always remove from active connections
        if websocket in active_connections:
            active_connections.remove(websocket)

async def broadcast_status_update():
    """Broadcast status update to all connected clients"""
    if active_connections:
        status = await get_status()
        # Create a copy of the list to avoid modification during iteration
        connections_to_remove = []
        
        for connection in active_connections:
            try:
                await connection.send_json(status)
            except Exception as e:
                # Mark for removal
                connections_to_remove.append(connection)
        
        # Remove disconnected clients
        for connection in connections_to_remove:
            if connection in active_connections:
                active_connections.remove(connection)

def get_recent_logs(count: int = 20):
    """Get recent log entries from trading.log"""
    try:
        # Get the project root directory (parent of web directory)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_file = Path(os.path.join(project_root, "logs", "trading.log"))
        if not log_file.exists():
            return []
        
        # Read last N lines
        with open(log_file, 'r') as f:
            lines = f.readlines()
            recent_lines = lines[-count:] if len(lines) > count else lines
            
        # Parse log entries
        logs = []
        for line in recent_lines:
            line = line.strip()
            if line and ']' in line:
                # Extract timestamp and message
                if line.startswith('[') and ']' in line:
                    timestamp_end = line.find(']')
                    timestamp = line[1:timestamp_end]
                    message = line[timestamp_end + 1:].strip()
                    
                    logs.append({
                        "timestamp": timestamp,
                        "message": message
                    })
        
        return logs[-count:]  # Return most recent entries
        
    except Exception as e:
        return [{"timestamp": "Error", "message": f"Could not read logs: {e}"}]

def is_bot_process_running():
    """Check if the trading bot process is actually running"""
    try:
        # Use ps to check for the process
        result = subprocess.run(
            ["ps", "aux"], 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        
        if result.returncode == 0:
            # Look for multi_wallet_trader.py in the process list
            for line in result.stdout.split('\n'):
                if 'multi_wallet_trader.py' in line:
                    # More flexible matching - just check if the script name is in the command
                    return True
        
        return False
    except Exception as e:
        print(f"Error checking bot process: {e}")
        return False

def kill_all_bot_processes():
    """Kill all running trading bot processes"""
    try:
        # Use pkill to kill all multi_wallet_trader.py processes
        result = subprocess.run(
            ["pkill", "-f", "multi_wallet_trader.py"], 
            capture_output=True, 
            timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False

def get_uptime():
    """Calculate bot uptime"""
    if bot_status["started_at"]:
        start_time = datetime.fromisoformat(bot_status["started_at"])
        uptime_seconds = (datetime.now() - start_time).total_seconds()
        
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
