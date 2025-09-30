#!/usr/bin/env python3
"""
Injective Network Health Checker
Tests all APIs and services to diagnose connectivity issues
"""

import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from pyinjective.async_client_v2 import AsyncClient
from pyinjective.indexer_client import IndexerClient
from pyinjective.core.network import Network

# ANSI color codes for pretty output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
BOLD = '\033[1m'
RESET = '\033[0m'

def print_status(service: str, status: str, details: str = "", duration_ms: int = 0):
    """Print formatted status line"""
    if status == "OK":
        icon = f"{GREEN}✅{RESET}"
        status_text = f"{GREEN}{status}{RESET}"
    elif status == "FAIL":
        icon = f"{RED}❌{RESET}"
        status_text = f"{RED}{status}{RESET}"
    else:
        icon = f"{YELLOW}⚠️{RESET}"
        status_text = f"{YELLOW}{status}{RESET}"
    
    duration_text = f" ({duration_ms}ms)" if duration_ms > 0 else ""
    details_text = f" - {details}" if details else ""
    
    print(f"{icon} {service:40} [{status_text}]{duration_text}{details_text}")

async def check_chain_grpc(network: Network):
    """Check Chain gRPC - Used for broadcasting transactions (CRITICAL)"""
    print(f"\n{BOLD}⚡ Chain gRPC (Transaction Broadcasting){RESET}")
    print(f"   Endpoint: {network.grpc_endpoint}")
    
    try:
        start = time.time()
        client = AsyncClient(network)
        # Test account query (similar to what bot does)
        await client.fetch_account("inj1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqe2hm49")
        duration = int((time.time() - start) * 1000)
        print_status("✅ Transaction Broadcasting", "OK", "Can send orders to chain", duration)
    except Exception as e:
        print_status("❌ Transaction Broadcasting", "FAIL", str(e)[:80])

async def check_indexer_api(network: Network):
    """Check Indexer API - Market data and orderbooks (CRITICAL)"""
    print(f"\n{BOLD}📊 Indexer API (Market Data & Orderbooks){RESET}")
    print(f"   Endpoint: {network.grpc_exchange_endpoint}")
    
    indexer = IndexerClient(network)
    
    # Test 1: Fetch spot markets
    try:
        start = time.time()
        markets = await asyncio.wait_for(
            indexer.fetch_spot_markets(),
            timeout=15.0
        )
        duration = int((time.time() - start) * 1000)
        market_count = len(markets.get('markets', [])) if markets else 0
        print_status("✅ Spot Markets List", "OK", f"{market_count} markets", duration)
    except asyncio.TimeoutError:
        print_status("Spot Markets", "FAIL", "Timeout after 15s")
    except Exception as e:
        error_str = str(e)
        if '503' in error_str or 'UNAVAILABLE' in error_str:
            print_status("❌ Spot Markets List", "FAIL", "503 Service Unavailable")
        else:
            print_status("❌ Spot Markets List", "FAIL", error_str[:80])
    
    # Test 2: Fetch derivative markets
    try:
        start = time.time()
        markets = await asyncio.wait_for(
            indexer.fetch_derivative_markets(),
            timeout=15.0
        )
        duration = int((time.time() - start) * 1000)
        market_count = len(markets.get('markets', [])) if markets else 0
        print_status("✅ Derivative Markets List", "OK", f"{market_count} markets", duration)
    except asyncio.TimeoutError:
        print_status("Derivative Markets", "FAIL", "Timeout after 15s")
    except Exception as e:
        error_str = str(e)
        if '503' in error_str or 'UNAVAILABLE' in error_str:
            print_status("❌ Derivative Markets List", "FAIL", "503 Service Unavailable")
        else:
            print_status("❌ Derivative Markets List", "FAIL", error_str[:80])
    
    # Test 3: Fetch specific orderbook (INJ/USDT testnet)
    try:
        start = time.time()
        market_id = "0x0611780ba69656949525013d947713300f56c37b6175e02f26bffa495c3208fe"  # INJ/USDT testnet
        orderbook = await asyncio.wait_for(
            indexer.fetch_spot_orderbook_v2(market_id=market_id, depth=10),
            timeout=15.0
        )
        duration = int((time.time() - start) * 1000)
        if orderbook and 'orderbook' in orderbook:
            buys = len(orderbook['orderbook'].get('buys', []))
            sells = len(orderbook['orderbook'].get('sells', []))
            print_status("✅ Orderbook Data", "OK", f"{buys} bids, {sells} asks (INJ/USDT)", duration)
        else:
            print_status("⚠️ Orderbook Data", "WARN", "Empty response")
    except asyncio.TimeoutError:
        print_status("Orderbook (INJ/USDT)", "FAIL", "Timeout after 15s")
    except Exception as e:
        error_str = str(e)
        if '503' in error_str or 'UNAVAILABLE' in error_str:
            print_status("❌ Orderbook Data", "FAIL", "503 Service Unavailable")
        else:
            print_status("❌ Orderbook Data", "FAIL", error_str[:80])
    
    # Test 4: Fetch recent trades
    try:
        start = time.time()
        market_id = "0x0611780ba69656949525013d947713300f56c37b6175e02f26bffa495c3208fe"  # INJ/USDT testnet
        from pyinjective.client.model.pagination import PaginationOption
        trades = await asyncio.wait_for(
            indexer.fetch_spot_trades(
                market_ids=[market_id],
                pagination=PaginationOption(limit=5)
            ),
            timeout=15.0
        )
        duration = int((time.time() - start) * 1000)
        trade_count = len(trades.get('trades', [])) if trades else 0
        print_status("✅ Trade History", "OK", f"{trade_count} recent trades", duration)
    except asyncio.TimeoutError:
        print_status("Recent Trades", "FAIL", "Timeout after 15s")
    except Exception as e:
        error_str = str(e)
        if '503' in error_str or 'UNAVAILABLE' in error_str:
            print_status("❌ Trade History", "FAIL", "503 Service Unavailable")
        else:
            print_status("❌ Trade History", "FAIL", error_str[:80])

async def check_wallet_balance(network: Network, wallet_address: str = None):
    """Check wallet balance using chain gRPC"""
    if not wallet_address:
        return
    
    print(f"\n{BOLD}👛 Wallet Balance Check{RESET}")
    print(f"   Address: {wallet_address}")
    
    try:
        start = time.time()
        client = AsyncClient(network)
        account = await client.fetch_account(wallet_address)
        duration = int((time.time() - start) * 1000)
        print_status("✅ Account Query", "OK", "Wallet accessible", duration)
    except Exception as e:
        print_status("❌ Account Query", "FAIL", str(e)[:80])

async def main():
    """Run all health checks"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Injective Network Health Checker')
    parser.add_argument('--network', choices=['testnet', 'mainnet'], default='testnet', help='Network to check (default: testnet)')
    parser.add_argument('--wallet', type=str, help='Optional: Check specific wallet address')
    args = parser.parse_args()
    
    # Select network
    if args.network == 'mainnet':
        network = Network.mainnet()
        network_name = "MAINNET"
    else:
        network = Network.testnet()
        network_name = "TESTNET"
    
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}🏥 INJECTIVE {network_name} HEALTH CHECK{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}")
    
    # Run checks for ONLY what the trading bot uses
    print(f"\n{BOLD}Testing CRITICAL endpoints used by trading bot...{RESET}\n")
    
    await check_chain_grpc(network)          # ✅ CRITICAL: Transaction broadcasting
    await check_indexer_api(network)         # ✅ CRITICAL: Market data & orderbooks
    
    if args.wallet:
        await check_wallet_balance(network, args.wallet)
    
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}✅ Health check complete!{RESET}\n")

if __name__ == "__main__":
    asyncio.run(main())
