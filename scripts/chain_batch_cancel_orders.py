#!/usr/bin/env python3
"""
Chain-based batch cancel all orders using Injective's AsyncClient directly.
This script queries the chain directly for order discovery and cancellation,
avoiding indexer pagination issues and ensuring real-time data accuracy.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional, Any
from pyinjective.async_client_v2 import AsyncClient
from pyinjective.core.network import Network
from pyinjective.core.broadcaster import MsgBroadcasterWithPk
from pyinjective import PrivateKey

# Add parent directory to path to import from utils
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import the secure wallet loader
from utils.secure_wallet_loader import load_wallets_from_env

# Global log file path
CHAIN_BATCH_CANCEL_LOG_FILE = "logs/chain_batch_cancel.log"

def ensure_logs_directory():
    """Ensure the logs directory exists"""
    os.makedirs("logs", exist_ok=True)

def log_chain_batch_cancel(message, wallet_id=None, market_id=None, order_count=None, tx_hash=None, page_info=None):
    """Log chain batch cancel operations to file with timestamp"""
    ensure_logs_directory()
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Format for file logging
    if wallet_id and market_id and order_count is not None:
        log_line = f"[{timestamp}] {message} | Wallet: {wallet_id} | Market: {market_id} | Orders: {order_count}"
        if page_info:
            log_line += f" | Page: {page_info}"
        if tx_hash:
            log_line += f" | TX: {tx_hash}"
    elif wallet_id and order_count is not None:
        log_line = f"[{timestamp}] {message} | Wallet: {wallet_id} | Orders: {order_count}"
        if page_info:
            log_line += f" | Page: {page_info}"
        if tx_hash:
            log_line += f" | TX: {tx_hash}"
    elif wallet_id:
        log_line = f"[{timestamp}] {message} | Wallet: {wallet_id}"
    else:
        log_line = f"[{timestamp}] {message}"
    
    # Write to log file
    try:
        with open(CHAIN_BATCH_CANCEL_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    except Exception as e:
        print(f"⚠️  Warning: Could not write to log file: {e}")
    
    # Also print to console
    print(log_line)

def print_header():
    """Print a beautiful header for the chain batch cancel operation"""
    print("\n" + "=" * 80)
    print("🔗 CHAIN-BASED BATCH CANCEL ALL ORDERS - INJECTIVE TRADING BOT")
    print("=" * 80)
    print("📅 This will cancel ALL open orders across ALL wallets and markets")
    print("🔗 Using direct chain queries for real-time order discovery")
    print("⚠️  Make sure you want to do this before proceeding!")
    print("=" * 80)

def print_wallet_summary(wallets_config):
    """Print a clean summary of wallets"""
    enabled_wallets = [w for w in wallets_config['wallets'] if w.get('enabled', False)]
    disabled_wallets = [w for w in wallets_config['wallets'] if not w.get('enabled', False)]
    
    print(f"\n📋 WALLET SUMMARY:")
    print(f"   ✅ Enabled: {len(enabled_wallets)} wallets")
    print(f"   ⏸️  Disabled: {len(disabled_wallets)} wallets")
    
    if enabled_wallets:
        print(f"\n   🎯 ACTIVE WALLETS:")
        for i, wallet in enumerate(enabled_wallets, 1):
            print(f"      {i}. {wallet['name']} ({wallet['id']})")
    
    if disabled_wallets:
        print(f"\n   ⏸️  DISABLED WALLETS:")
        for i, wallet in enumerate(disabled_wallets, 1):
            print(f"      {i}. {wallet['name']} ({wallet['id']})")

def print_market_summary(markets_config):
    """Print a clean summary of markets"""
    enabled_markets = [m for m in markets_config['markets'].values() if m.get('enabled', False)]
    disabled_markets = [m for m in markets_config['markets'].values() if not m.get('enabled', False)]
    
    print(f"\n📊 MARKET SUMMARY:")
    print(f"   ✅ Enabled: {len(enabled_markets)} markets")
    print(f"   ⏸️  Disabled: {len(disabled_markets)} markets")
    
    if enabled_markets:
        print(f"\n   🎯 ACTIVE MARKETS:")
        for i, (market_id, market_config) in enumerate(markets_config['markets'].items(), 1):
            if market_config.get('enabled', False):
                market_type = market_config.get('type', 'unknown').upper()
                print(f"      {i}. {market_id} ({market_type})")

def print_wallet_header(wallet_name, wallet_id, address):
    """Print a clean header for each wallet"""
    print(f"\n" + "-" * 60)
    print(f"💰 WALLET: {wallet_name}")
    print(f"   ID: {wallet_id}")
    print(f"   Address: {address}")
    print("-" * 60)

def print_market_header(market_id, market_type):
    """Print a clean header for each market"""
    print(f"\n   📊 MARKET: {market_id} ({market_type.upper()})")
    print(f"   " + "-" * 40)

def print_orders_found(count, market_id, total_pages=None):
    """Print when orders are found"""
    if count > 0:
        page_info = f" (across {total_pages} pages)" if total_pages and total_pages > 1 else ""
        print(f"      ✅ Found {count} open orders to cancel{page_info}")
    else:
        print(f"      ✅ No open orders found")

def print_batch_cancel_result(order_type, count, success, tx_hash=None, error=None):
    """Print the result of batch cancellation"""
    print(f"\n   🚨 BATCH CANCEL {order_type.upper()} ORDERS:")
    if success:
        print(f"      ✅ SUCCESS: Cancelled {count} {order_type} orders")
        if tx_hash:
            print(f"      📝 Transaction Hash: {tx_hash}")
    else:
        print(f"      ❌ FAILED: Could not cancel {order_type} orders")
        if error:
            print(f"      📋 Error: {error}")

def print_final_summary(total_cancelled, total_wallets_processed):
    """Print the final summary"""
    print(f"\n" + "=" * 80)
    print(f"🎉 CHAIN-BASED BATCH CANCEL COMPLETE!")
    print("=" * 80)
    print(f"📊 SUMMARY:")
    print(f"   💰 Wallets Processed: {total_wallets_processed}")
    print(f"   🚨 Total Orders Cancelled: {total_cancelled}")
    
    if total_cancelled > 0:
        print(f"\n✅ All open orders have been successfully cancelled!")
        print(f"🎯 Your trading bot is now clean and ready for new orders.")
    else:
        print(f"\n✅ No open orders were found to cancel.")
        print(f"🎯 All wallets are already clean!")
    
    print("=" * 80)

async def fetch_all_orders_from_chain(
    client: AsyncClient, 
    market_type: str, 
    testnet_market_id: str, 
    subaccount_id: str,
    wallet_id: str,
    market_id: str
) -> List[Dict[str, Any]]:
    """
    Fetch all orders from chain with proper pagination handling
    
    Args:
        client: AsyncClient instance
        market_type: 'spot' or 'derivative'
        testnet_market_id: Market ID on testnet
        subaccount_id: Subaccount ID
        wallet_id: Wallet ID for logging
        market_id: Market ID for logging
        
    Returns:
        List of all orders found
    """
    all_orders = []
    skip = 0
    limit = 100  # Standard pagination limit
    page_count = 0
    
    print(f"      🔍 Scanning chain for orders (pagination enabled)...")
    
    while True:
        try:
            page_count += 1
            log_chain_batch_cancel(f"📄 Fetching page {page_count} (skip={skip}, limit={limit})", 
                                 wallet_id=wallet_id, market_id=market_id, page_info=f"page {page_count}")
            
            if market_type == 'spot':
                response = await client.fetch_spot_orders(
                    market_ids=[testnet_market_id],
                    subaccount_id=subaccount_id,
                    skip=skip,
                    limit=limit
                )
            else:
                response = await client.fetch_derivative_orders(
                    market_ids=[testnet_market_id],
                    subaccount_id=subaccount_id,
                    skip=skip,
                    limit=limit
                )
            
            if not response or 'orders' not in response or not response['orders']:
                print(f"      📄 Page {page_count}: No more orders found")
                break
                
            orders = response['orders']
            all_orders.extend(orders)
            
            print(f"      📄 Page {page_count}: Found {len(orders)} orders (total: {len(all_orders)})")
            
            # If we got fewer orders than the limit, we've reached the end
            if len(orders) < limit:
                print(f"      📄 Page {page_count}: Reached end of orders")
                break
                
            skip += limit
            
            # Safety limit to prevent infinite loops
            if page_count > 50:  # Max 5000 orders (50 pages * 100 orders)
                print(f"      ⚠️  Reached safety limit of 50 pages, stopping pagination")
                log_chain_batch_cancel(f"⚠️  Reached pagination safety limit", 
                                     wallet_id=wallet_id, market_id=market_id, page_info=f"50 pages max")
                break
                
        except Exception as e:
            print(f"      ❌ Error fetching page {page_count}: {e}")
            log_chain_batch_cancel(f"❌ Error fetching page {page_count}: {str(e)}", 
                                 wallet_id=wallet_id, market_id=market_id, page_info=f"page {page_count}")
            break
    
    log_chain_batch_cancel(f"📊 Chain scan complete: {len(all_orders)} total orders across {page_count} pages", 
                         wallet_id=wallet_id, market_id=market_id, order_count=len(all_orders), page_info=f"{page_count} pages")
    
    return all_orders

async def chain_batch_cancel_all_orders():
    """Main function to batch cancel all orders using chain-based discovery"""
    print_header()
    
    # Log the start of chain batch cancel operation
    log_chain_batch_cancel("🔗 CHAIN-BASED BATCH CANCEL OPERATION STARTED")
    
    try:
        # Load configurations
        print(f"\n🔒 Loading configurations...")
        wallets_config = load_wallets_from_env()
        
        with open('config/markets_config.json', 'r') as f:
            markets_config = json.load(f)
        
        # Log configuration summary
        enabled_wallets = [w for w in wallets_config['wallets'] if w.get('enabled', False)]
        enabled_markets = [m for m in markets_config['markets'].values() if m.get('enabled', False)]
        log_chain_batch_cancel(f"📋 Configuration loaded: {len(enabled_wallets)} wallets, {len(enabled_markets)} markets")
        
        # Print summaries
        print_wallet_summary(wallets_config)
        print_market_summary(markets_config)
        
        # Initialize network
        network = Network.testnet()
        
        total_cancelled = 0
        total_wallets_processed = 0
        
        # Process each wallet
        for wallet_config in wallets_config['wallets']:
            if not wallet_config.get('enabled', False):
                continue
                
            wallet_id = wallet_config['id']
            wallet_name = wallet_config['name']
            private_key = wallet_config['private_key']
            
            try:
                # Initialize client for this wallet (chain-based)
                client = AsyncClient(network)
                composer = await client.composer()
                
                # Initialize wallet
                pk = PrivateKey.from_hex(private_key)
                address = pk.to_public_key().to_address()
                
                # Print wallet header
                print_wallet_header(wallet_name, wallet_id, address.to_acc_bech32())
                
                # Log wallet processing start
                log_chain_batch_cancel(f"💰 Processing wallet: {wallet_name}", wallet_id=wallet_id)
                
                # Initialize broadcaster with gas heuristics for better gas estimation
                gas_price = await client.current_chain_gas_price()
                gas_price = int(gas_price * 1.1)
                
                broadcaster = MsgBroadcasterWithPk.new_using_gas_heuristics(
                    network=network,
                    private_key=private_key,
                    gas_price=gas_price,
                    client=client,
                    composer=composer,
                )
                
                print(f"   ✅ Wallet initialized successfully (chain-based)")
                log_chain_batch_cancel(f"✅ Wallet initialized: {address.to_acc_bech32()}", wallet_id=wallet_id)
                
                # Collect all orders to cancel
                all_spot_orders_data = []
                all_derivative_orders_data = []
                
                # Process each market
                for market_id, market_config in markets_config['markets'].items():
                    if not market_config.get('enabled', False):
                        continue
                        
                    market_type = market_config.get('type', 'unknown')
                    print_market_header(market_id, market_type)
                    
                    try:
                        # Get subaccount ID
                        subaccount_id = address.get_subaccount_id(0)
                        
                        # Use testnet_market_id for order cancellation (we're on testnet)
                        testnet_market_id = market_config.get('testnet_market_id')
                        if not testnet_market_id:
                            print(f"      ⚠️  No testnet_market_id found for {market_id}")
                            continue
                        
                        # Fetch ALL orders from chain with pagination
                        all_orders = await fetch_all_orders_from_chain(
                            client=client,
                            market_type=market_config.get('type'),
                            testnet_market_id=testnet_market_id,
                            subaccount_id=subaccount_id,
                            wallet_id=wallet_id,
                            market_id=market_id
                        )
                        
                        if all_orders:
                            # Filter for active orders only
                            orders_to_cancel = [o for o in all_orders if o.get('state') == 'booked']
                            print_orders_found(len(orders_to_cancel), market_id, len(all_orders) // 100 + 1)
                            
                            # Log orders found
                            if len(orders_to_cancel) > 0:
                                log_chain_batch_cancel(f"📊 Found {len(orders_to_cancel)} orders to cancel from {len(all_orders)} total orders", 
                                                     wallet_id=wallet_id, market_id=market_id, order_count=len(orders_to_cancel))
                            
                            # Create order data for batch cancel
                            for order in orders_to_cancel:
                                order_hash = order.get('orderHash')
                                if order_hash:
                                    # Create OrderData for batch cancel
                                    order_data = composer.order_data_without_mask(
                                        market_id=testnet_market_id,
                                        subaccount_id=subaccount_id,
                                        order_hash=order_hash
                                    )
                                    
                                    if market_config.get('type') == 'spot':
                                        all_spot_orders_data.append(order_data)
                                    else:
                                        all_derivative_orders_data.append(order_data)
                        else:
                            print_orders_found(0, market_id)
                            log_chain_batch_cancel(f"✅ No orders found", wallet_id=wallet_id, market_id=market_id, order_count=0)
                            
                    except Exception as e:
                        print(f"      ❌ Error processing market {market_id}: {e}")
                        log_chain_batch_cancel(f"❌ Error processing market: {str(e)}", wallet_id=wallet_id, market_id=market_id)
                
                # Batch cancel spot orders
                if all_spot_orders_data:
                    try:
                        log_chain_batch_cancel(f"🚨 Starting chain-based batch cancel for {len(all_spot_orders_data)} spot orders", 
                                             wallet_id=wallet_id, order_count=len(all_spot_orders_data))
                        
                        batch_cancel_msg = composer.msg_batch_cancel_spot_orders(
                            sender=address.to_acc_bech32(),
                            orders_data=all_spot_orders_data
                        )
                        
                        response = await broadcaster.broadcast([batch_cancel_msg])
                        
                        # Check for transaction hash in different response formats
                        tx_hash = response.get('txhash') or response.get('txResponse', {}).get('txhash')
                        success = bool(tx_hash)
                        
                        print_batch_cancel_result("spot", len(all_spot_orders_data), success, tx_hash)
                        
                        if success:
                            log_chain_batch_cancel(f"✅ SUCCESS: Cancelled {len(all_spot_orders_data)} spot orders", 
                                                 wallet_id=wallet_id, order_count=len(all_spot_orders_data), tx_hash=tx_hash)
                            total_cancelled += len(all_spot_orders_data)
                        else:
                            log_chain_batch_cancel(f"❌ FAILED: Could not cancel {len(all_spot_orders_data)} spot orders", 
                                                 wallet_id=wallet_id, order_count=len(all_spot_orders_data))
                            
                    except Exception as e:
                        print_batch_cancel_result("spot", len(all_spot_orders_data), False, error=str(e))
                        log_chain_batch_cancel(f"❌ ERROR: Exception during spot order cancellation: {str(e)}", 
                                             wallet_id=wallet_id, order_count=len(all_spot_orders_data))
                
                # Batch cancel derivative orders
                if all_derivative_orders_data:
                    try:
                        log_chain_batch_cancel(f"🚨 Starting chain-based batch cancel for {len(all_derivative_orders_data)} derivative orders", 
                                             wallet_id=wallet_id, order_count=len(all_derivative_orders_data))
                        
                        batch_cancel_msg = composer.msg_batch_cancel_derivative_orders(
                            sender=address.to_acc_bech32(),
                            orders_data=all_derivative_orders_data
                        )
                        
                        response = await broadcaster.broadcast([batch_cancel_msg])
                        
                        # Check for transaction hash in different response formats
                        tx_hash = response.get('txhash') or response.get('txResponse', {}).get('txhash')
                        success = bool(tx_hash)
                        
                        print_batch_cancel_result("derivative", len(all_derivative_orders_data), success, tx_hash)
                        
                        if success:
                            log_chain_batch_cancel(f"✅ SUCCESS: Cancelled {len(all_derivative_orders_data)} derivative orders", 
                                                 wallet_id=wallet_id, order_count=len(all_derivative_orders_data), tx_hash=tx_hash)
                            total_cancelled += len(all_derivative_orders_data)
                        else:
                            log_chain_batch_cancel(f"❌ FAILED: Could not cancel {len(all_derivative_orders_data)} derivative orders", 
                                                 wallet_id=wallet_id, order_count=len(all_derivative_orders_data))
                            
                    except Exception as e:
                        print_batch_cancel_result("derivative", len(all_derivative_orders_data), False, error=str(e))
                        log_chain_batch_cancel(f"❌ ERROR: Exception during derivative order cancellation: {str(e)}", 
                                             wallet_id=wallet_id, order_count=len(all_derivative_orders_data))
                
                # Close client
                await client.close_chain_channel()
                await client.close_chain_stream_channel()
                
                total_wallets_processed += 1
                log_chain_batch_cancel(f"✅ Wallet processing completed", wallet_id=wallet_id)
                
            except Exception as e:
                print(f"   ❌ Error processing wallet {wallet_id}: {e}")
                log_chain_batch_cancel(f"❌ ERROR: Failed to process wallet: {str(e)}", wallet_id=wallet_id)
        
        # Log final summary
        log_chain_batch_cancel(f"🎉 CHAIN-BASED BATCH CANCEL COMPLETE: {total_cancelled} orders cancelled across {total_wallets_processed} wallets")
        
        # Print final summary
        print_final_summary(total_cancelled, total_wallets_processed)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        log_chain_batch_cancel(f"❌ CRITICAL ERROR: {str(e)}")

if __name__ == "__main__":
    asyncio.run(chain_batch_cancel_all_orders())
