#!/usr/bin/env python3
"""
Check Derivative Positions Utility
Shows all open derivative positions for each wallet.
"""

import asyncio
import json
import os
import sys
from decimal import Decimal
from pyinjective import PrivateKey
from pyinjective.async_client_v2 import AsyncClient
from pyinjective.indexer_client import IndexerClient
from pyinjective.core.network import Network

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.secure_wallet_loader import load_wallets_from_env

async def check_derivative_positions():
    """Check derivative positions for all wallets"""
    print("\n" + "=" * 80)
    print("🎯 DERIVATIVE POSITIONS CHECKER")
    print("=" * 80)
    
    try:
        # Load wallets
        wallets_config = load_wallets_from_env()
        
        # Load markets config
        with open('config/markets_config.json', 'r') as f:
            markets_config = json.load(f)
        
        # Network setup
        network = Network.testnet()
        
        total_positions = 0
        
        for wallet in wallets_config['wallets']:
            if not wallet.get('enabled', False):
                continue
                
            wallet_id = wallet['id']
            print(f"\n📊 Checking positions for {wallet_id}...")
            
            try:
                # Create client
                client = AsyncClient(network)
                
                # Set up wallet
                private_key_obj = PrivateKey.from_hex(wallet['private_key'])
                address = private_key_obj.to_public_key().to_address()
                subaccount_id = address.get_subaccount_id(0)
                
                # Check positions for each derivative market
                wallet_positions = 0
                
                for market_symbol, market_config in markets_config['markets'].items():
                    if market_config.get('type') != 'derivative' or not market_config.get('enabled'):
                        continue
                    
                    market_id = market_config.get('testnet_market_id', market_config.get('market_id'))
                    if not market_id:
                        continue
                    
                    print(f"   🔍 Checking {market_symbol} ({market_id[:8]}...)")
                    
                    try:
                        # Fetch derivative positions using indexer  
                        indexer_client = IndexerClient(network)
                        positions_response = await indexer_client.fetch_derivative_positions_v2(
                            subaccount_id=subaccount_id,
                            market_ids=[market_id]
                        )
                        
                        if positions_response and 'positions' in positions_response:
                            positions = positions_response['positions']
                            
                            for position in positions:
                                direction = position.get('direction', 'unknown')
                                quantity = position.get('quantity', '0')
                                entry_price = position.get('entry_price', '0')
                                mark_price = position.get('mark_price', '0')
                                unrealized_pnl = position.get('unrealized_pnl', '0')
                                margin = position.get('margin', '0')
                                
                                # Skip positions with zero quantity
                                if float(quantity) == 0:
                                    continue
                                
                                print(f"      📍 OPEN POSITION:")
                                print(f"         Direction: {direction}")
                                print(f"         Quantity: {quantity}")
                                print(f"         Entry Price: ${float(entry_price):.4f}")
                                print(f"         Mark Price: ${float(mark_price):.4f}")
                                print(f"         Unrealized PnL: ${float(unrealized_pnl):.4f}")
                                print(f"         Margin: ${float(margin):.4f}")
                                
                                wallet_positions += 1
                                total_positions += 1
                    
                    except Exception as e:
                        print(f"      ❌ Error checking positions for {market_symbol}: {e}")
                
                print(f"   📊 Total positions for {wallet_id}: {wallet_positions}")
                
                # Close client
                await client.close_chain_channel()
                await client.close_chain_stream_channel()
                
            except Exception as e:
                print(f"   ❌ Error processing wallet {wallet_id}: {e}")
        
        print(f"\n" + "=" * 80)
        print(f"🎯 TOTAL DERIVATIVE POSITIONS: {total_positions}")
        print("=" * 80)
        
        if total_positions > 0:
            print("\n💡 To close derivative positions, you need to:")
            print("   1. Create opposite orders (if long, place sell orders)")
            print("   2. Or use a position closing script")
            print("   3. Order cancellation only cancels pending orders, not positions!")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_derivative_positions())
