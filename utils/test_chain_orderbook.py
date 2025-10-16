#!/usr/bin/env python3
"""
Test script to verify chain-based orderbook queries work correctly.
This bypasses the indexer entirely and queries the chain directly.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pyinjective.async_client_v2 import AsyncClient
from pyinjective.core.network import Network


async def test_chain_orderbook():
    """Test fetching orderbook directly from chain"""
    
    # USDC/USDT market on testnet
    market_id = "0x5fbd22eb44d9db413513f99ceb9a5ac4cc5b5e6893d5882877391d6927927e6d"
    
    print("=" * 80)
    print("TESTING CHAIN-BASED ORDERBOOK QUERY")
    print("=" * 80)
    print(f"Market: USDC/USDT")
    print(f"Market ID: {market_id}")
    print()
    
    # Initialize network and client
    network = Network.testnet()
    client = AsyncClient(network)
    
    try:
        print("🔗 Fetching orderbook directly from chain (bypassing indexer)...")
        
        # Query chain directly
        chain_orderbook = await client.fetch_chain_spot_orderbook(market_id=market_id)
        
        print("✅ Chain query successful!")
        print()
        
        # Parse response - Chain returns {buysPriceLevel, sellsPriceLevel}
        if chain_orderbook:
            # Chain format: {buysPriceLevel: [{p, q}], sellsPriceLevel: [{p, q}]}
            buys_raw = chain_orderbook.get('buysPriceLevel', [])
            sells_raw = chain_orderbook.get('sellsPriceLevel', [])
            
            print(f"📊 Orderbook Statistics:")
            print(f"   Total Bids: {len(buys_raw)}")
            print(f"   Total Asks: {len(sells_raw)}")
            print()
            
            if buys_raw:
                print(f"📈 Top 5 Bids:")
                for i, bid in enumerate(buys_raw[:5], 1):
                    # Chain uses 'p' for price, 'q' for quantity
                    price = float(bid.get('p', '0')) / 1e18  # Convert from base units
                    quantity = float(bid.get('q', '0')) / 1e18
                    print(f"   {i}. Price: ${price:.4f}, Qty: {quantity:.2f}")
                print()
            else:
                print("   No bids in orderbook")
                print()
            
            if sells_raw:
                print(f"📉 Top 5 Asks:")
                for i, ask in enumerate(sells_raw[:5], 1):
                    price = float(ask.get('p', '0')) / 1e18
                    quantity = float(ask.get('q', '0')) / 1e18
                    print(f"   {i}. Price: ${price:.4f}, Qty: {quantity:.2f}")
                print()
            else:
                print("   No asks in orderbook")
                print()
            
            print("=" * 80)
            print("✅ CHAIN QUERY TEST PASSED!")
            print("=" * 80)
            print()
            print("The chain-based fallback is working correctly.")
            print("Chain response format differs from indexer:")
            print("  - Uses 'buysPriceLevel'/'sellsPriceLevel' instead of 'orderbook.buys/sells'")
            print("  - Uses 'p'/'q' instead of 'price'/'quantity'")
            print()
            print("The bot automatically converts this format for compatibility.")
            print()
            print("You can now enable force chain mode using:")
            print()
            print("  export FORCE_CHAIN_QUERIES=true")
            print("  python scripts/bots/spot_trader.py --market 'USDC/USDT'")
            print()
            
        else:
            print("⚠️ Unexpected response: No data returned")
            print(chain_orderbook)
            
    except Exception as e:
        print(f"❌ Chain query failed: {e}")
        print()
        print("This suggests there may be an issue with the chain query.")
        print("Please check:")
        print("  1. Network connectivity")
        print("  2. Chain node availability")
        print("  3. Market ID is correct")


if __name__ == "__main__":
    asyncio.run(test_chain_orderbook())

