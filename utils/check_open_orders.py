#!/usr/bin/env python3
"""
Check Open Orders Utility
Shows how many open orders each wallet has for each market.
Based on the official Injective example.
"""

import asyncio
import json
import os
import sys
import logging
from datetime import datetime
from pyinjective import PrivateKey
from pyinjective.async_client_v2 import AsyncClient
from pyinjective.indexer_client import IndexerClient
from pyinjective.core.network import Network

# Add parent directory to path to import from utils
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import the secure wallet loader
from utils.secure_wallet_loader import load_wallets_from_env

def setup_logging():
    """Setup logging to file"""
    # Create logs directory in the root if it doesn't exist
    os.makedirs('../logs', exist_ok=True)
    
    # Create log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"../logs/open_orders_{timestamp}.log"
    
    # Clear any existing logging configuration
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()  # Also print to console
        ],
        force=True  # Force reconfiguration
    )
    
    return log_filename

def print_header():
    """Print a beautiful header"""
    print("\n" + "=" * 80)
    print("📊 CHECK OPEN ORDERS - WALLET & MARKET STATUS")
    print("=" * 80)
    print("📅 This utility shows how many open orders each wallet has for each market")
    print("🎯 Based on official Injective examples")
    print("=" * 80)

def print_wallet_header(wallet_name, wallet_id, address):
    """Print wallet header"""
    print(f"\n" + "-" * 60)
    print(f"💰 WALLET: {wallet_name}")
    print(f"   ID: {wallet_id}")
    print(f"   Address: {address}")
    print("-" * 60)

def print_market_header(market_id, market_type):
    """Print market header"""
    print(f"\n   📊 MARKET: {market_id} ({market_type.upper()})")
    print(f"   " + "-" * 40)

def print_orders_summary(spot_orders, derivative_orders, market_id):
    """Print orders summary for a market"""
    total_orders = len(spot_orders) + len(derivative_orders)
    
    if total_orders > 0:
        print(f"      ✅ Found {total_orders} open orders:")
        if spot_orders:
            print(f"         📈 Spot orders: {len(spot_orders)}")
        if derivative_orders:
            print(f"         📊 Derivative orders: {len(derivative_orders)}")
    else:
        print(f"      ✅ No open orders found")

def print_order_details(orders, order_type):
    """Print detailed order information"""
    if not orders:
        return
    
    print(f"\n      📋 {order_type.upper()} ORDER DETAILS:")
    for i, order in enumerate(orders, 1):
        order_hash = order.get('orderHash', 'N/A')
        side = order.get('orderType', 'N/A')
        price = order.get('price', 'N/A')
        quantity = order.get('quantity', 'N/A')
        state = order.get('state', 'N/A')
        
        order_info = f"         {i}. Hash: {order_hash} | {side} | Price: {price} | Qty: {quantity} | State: {state}"
        print(order_info)
        logging.info(order_info)

async def check_open_orders():
    """Check open orders for all wallets and markets"""
    print_header()
    
    try:
        # Load configurations
        config_msg = "\n🔒 Loading configurations..."
        print(config_msg)
        logging.info(config_msg)
        wallets_config = load_wallets_from_env()
        
        with open('config/markets_config.json', 'r') as f:
            markets_config = json.load(f)
        
        # Log configuration summary
        enabled_wallets = [w for w in wallets_config['wallets'] if w.get('enabled', False)]
        enabled_markets = [m for m in markets_config['markets'].values() if m.get('enabled', False)]
        
        print(f"✅ Loaded {len(enabled_wallets)} enabled wallets")
        print(f"✅ Loaded {len(enabled_markets)} enabled markets")
        
        # Initialize network
        network = Network.testnet()
        
        total_orders_all_wallets = 0
        total_wallets_processed = 0
        
        # Process each wallet
        for wallet_config in wallets_config['wallets']:
            if not wallet_config.get('enabled', False):
                continue
                
            wallet_id = wallet_config['id']
            wallet_name = wallet_config['name']
            private_key = wallet_config['private_key']
            
            try:
                # Initialize clients for this wallet
                client = AsyncClient(network)
                indexer_client = IndexerClient(network)
                
                # Initialize wallet
                priv_key = PrivateKey.from_hex(private_key)
                pub_key = priv_key.to_public_key()
                address = pub_key.to_address()
                
                # Fetch account info
                await client.fetch_account(address.to_acc_bech32())
                
                # Try different subaccount indices
                subaccount_indices = [0, 1, 2]  # Try multiple subaccount indices
                
                # Print wallet header
                print_wallet_header(wallet_name, wallet_id, address.to_acc_bech32())
                logging.info(f"Processing wallet: {wallet_name} ({wallet_id})")
                
                wallet_total_orders = 0
                
                # Process each market
                for market_id, market_config in markets_config['markets'].items():
                    if not market_config.get('enabled', False):
                        continue
                        
                    market_type = market_config.get('type', 'unknown')
                    testnet_market_id = market_config.get('testnet_market_id')
                    
                    if not testnet_market_id:
                        print(f"      ⚠️  No testnet_market_id found for {market_id}")
                        continue
                    
                    print_market_header(market_id, market_type)
                    logging.info(f"Processing market: {market_id} ({market_type})")
                    
                    try:
                        # Use official SubaccountOrderSummary method (much faster!)
                        subaccount_id = address.get_subaccount_id(index=0)
                        
                        # Get order summary using official method
                        order_summary = await indexer_client.fetch_subaccount_order_summary(
                            subaccount_id=subaccount_id,
                            market_id=testnet_market_id
                        )
                        
                        # Extract counts from summary
                        spot_count = int(order_summary.get('spotOrdersTotal', 0))
                        derivative_count = int(order_summary.get('derivativeOrdersTotal', 0))
                        
                        print(f"      📊 Order Summary: {spot_count} spot, {derivative_count} derivative")
                        
                        # If we have orders, fetch detailed order data
                        all_orders = []
                        if spot_count > 0 or derivative_count > 0:
                            try:
                                if market_type == 'spot' and spot_count > 0:
                                    detailed_orders = await indexer_client.fetch_spot_orders(
                                        market_ids=[testnet_market_id],
                                        subaccount_id=subaccount_id
                                    )
                                    if detailed_orders and 'orders' in detailed_orders:
                                        all_orders.extend(detailed_orders['orders'])
                                        
                                elif market_type == 'derivative' and derivative_count > 0:
                                    detailed_orders = await indexer_client.fetch_derivative_orders(
                                        market_ids=[testnet_market_id],
                                        subaccount_id=subaccount_id
                                    )
                                    if detailed_orders and 'orders' in detailed_orders:
                                        all_orders.extend(detailed_orders['orders'])
                            except Exception as e:
                                print(f"      ⚠️  Error fetching detailed orders: {e}")
                        
                        # Separate spot and derivative orders
                        spot_orders = []
                        derivative_orders = []
                        
                        for order in all_orders:
                            order_state = order.get('state')
                            
                            # Check for different possible states
                            if order_state in ['booked', 'partial_filled', 'active', 'unfilled']:
                                if market_type == 'spot':
                                    spot_orders.append(order)
                                else:
                                    derivative_orders.append(order)
                        
                        # Print summary
                        print_orders_summary(spot_orders, derivative_orders, market_id)
                        
                        # Print detailed order information
                        if spot_orders:
                            print_order_details(spot_orders, 'spot')
                        if derivative_orders:
                            print_order_details(derivative_orders, 'derivative')
                        
                        # Count total orders for this market
                        market_orders = len(spot_orders) + len(derivative_orders)
                        wallet_total_orders += market_orders
                        
                    except Exception as e:
                        print(f"      ❌ Error checking orders for {market_id}: {e}")
                
                # Print wallet summary
                print(f"\n   📊 WALLET SUMMARY:")
                print(f"      Total open orders: {wallet_total_orders}")
                total_orders_all_wallets += wallet_total_orders
                
                # Close client
                await client.close_chain_channel()
                await client.close_chain_stream_channel()
                
                total_wallets_processed += 1
                
            except Exception as e:
                print(f"   ❌ Error processing wallet {wallet_id}: {e}")
        
        # Print final summary
        print(f"\n" + "=" * 80)
        print(f"🎉 OPEN ORDERS CHECK COMPLETE!")
        print("=" * 80)
        print(f"📊 SUMMARY:")
        print(f"   💰 Wallets Processed: {total_wallets_processed}")
        print(f"   📈 Total Open Orders: {total_orders_all_wallets}")
        
        if total_orders_all_wallets > 0:
            print(f"\n✅ Found {total_orders_all_wallets} open orders across all wallets")
            print(f"🎯 Use the batch cancel script to cancel orders if needed")
        else:
            print(f"\n✅ No open orders found across all wallets")
            print(f"🎯 All wallets are clean!")
        
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")

async def get_open_orders_data():
    """Get open orders data for all wallets and markets (returns data instead of printing)"""
    try:
        # Load configurations
        wallets_config = load_wallets_from_env()
        if not wallets_config or 'wallets' not in wallets_config:
            return {"error": "No wallets configuration found"}
        
        enabled_wallets = [w for w in wallets_config['wallets'] if w.get('enabled', False)]
        
        # Load market configuration
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        markets_config_path = os.path.join(project_root, 'config', 'markets_config.json')
        with open(markets_config_path, 'r') as f:
            markets_config = json.load(f)
        
        enabled_markets = [m for m in markets_config['markets'].values() if m.get('enabled', False)]
        
        # Initialize network
        network = Network.testnet()
        
        total_orders_all_wallets = 0
        wallets_data = []
        
        # Process each wallet
        for wallet_config in wallets_config['wallets']:
            if not wallet_config.get('enabled', False):
                continue
                
            wallet_id = wallet_config['id']
            wallet_name = wallet_config['name']
            private_key = wallet_config['private_key']
            
            try:
                # Initialize clients for this wallet
                client = AsyncClient(network)
                indexer_client = IndexerClient(network)
                
                # Initialize wallet
                priv_key = PrivateKey.from_hex(private_key)
                pub_key = priv_key.to_public_key()
                address = pub_key.to_address()
                
                # Fetch account info
                await client.fetch_account(address.to_acc_bech32())
                
                wallet_total_orders = 0
                markets_data = []
                
                # Process each market
                for market_id, market_config in markets_config['markets'].items():
                    if not market_config.get('enabled', False):
                        continue
                    
                    market_type = market_config.get('type', 'spot')
                    testnet_market_id = market_config.get('testnet_market_id')
                    
                    if not testnet_market_id:
                        continue
                    
                    try:
                        # Use official SubaccountOrderSummary method (much faster!)
                        subaccount_id = address.get_subaccount_id(index=0)
                        
                        # Get order summary using official method
                        order_summary = await indexer_client.fetch_subaccount_order_summary(
                            subaccount_id=subaccount_id,
                            market_id=testnet_market_id
                        )
                        
                        # Extract counts from summary
                        spot_count = int(order_summary.get('spotOrdersTotal', 0))
                        derivative_count = int(order_summary.get('derivativeOrdersTotal', 0))
                        
                        # If we have orders, fetch detailed order data
                        all_orders = []
                        if spot_count > 0 or derivative_count > 0:
                            try:
                                if market_type == 'spot' and spot_count > 0:
                                    detailed_orders = await indexer_client.fetch_spot_orders(
                                        market_ids=[testnet_market_id],
                                        subaccount_id=subaccount_id
                                    )
                                    if detailed_orders and 'orders' in detailed_orders:
                                        all_orders.extend(detailed_orders['orders'])
                                        
                                elif market_type == 'derivative' and derivative_count > 0:
                                    detailed_orders = await indexer_client.fetch_derivative_orders(
                                        market_ids=[testnet_market_id],
                                        subaccount_id=subaccount_id
                                    )
                                    if detailed_orders and 'orders' in detailed_orders:
                                        all_orders.extend(detailed_orders['orders'])
                            except Exception as e:
                                pass  # Skip detailed orders if there's an error
                        
                        # Separate spot and derivative orders
                        spot_orders = []
                        derivative_orders = []
                        
                        for order in all_orders:
                            order_state = order.get('state')
                            
                            # Check for different possible states
                            if order_state in ['booked', 'partial_filled', 'active', 'unfilled']:
                                if market_type == 'spot':
                                    spot_orders.append(order)
                                else:
                                    derivative_orders.append(order)
                        
                        # Add market data (always include, even if no orders)
                        market_total = len(spot_orders) + len(derivative_orders)
                        markets_data.append({
                            'market_id': market_id,
                            'market_type': market_type,
                            'spot_orders': spot_orders,
                            'derivative_orders': derivative_orders,
                            'total_orders': market_total
                        })
                        wallet_total_orders += market_total
                        
                    except Exception as e:
                        continue
                
                # Add wallet data
                wallets_data.append({
                    'wallet_id': wallet_id,
                    'wallet_name': wallet_name,
                    'address': address.to_acc_bech32(),
                    'total_orders': wallet_total_orders,
                    'markets': markets_data
                })
                
                total_orders_all_wallets += wallet_total_orders
                
                # Close client connections
                await client.close()
                
            except Exception as e:
                continue
        
        return {
            'wallets': wallets_data,
            'total_orders': total_orders_all_wallets,
            'wallets_processed': len(enabled_wallets),
            'markets_processed': len(enabled_markets)
        }
        
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    # Setup logging first
    log_filename = setup_logging()
    print(f"📝 Logging to: {log_filename}")
    logging.info("Starting open orders check...")
    
    # Run the main function
    asyncio.run(check_open_orders())
    
    print(f"📝 Full log saved to: {log_filename}")
    logging.info("Open orders check completed.")
