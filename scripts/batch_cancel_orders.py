#!/usr/bin/env python3
"""
Batch cancel all orders using Injective's batch cancel functionality.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pyinjective.async_client_v2 import AsyncClient
from pyinjective.indexer_client import IndexerClient
from pyinjective.core.network import Network
from pyinjective.core.broadcaster import MsgBroadcasterWithPk
from pyinjective import PrivateKey

# Add parent directory to path to import from utils
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import the secure wallet loader
from utils.secure_wallet_loader import load_wallets_from_env

# Global log file path
BATCH_CANCEL_LOG_FILE = "logs/batch_cancel.log"

def ensure_logs_directory():
    """Ensure the logs directory exists"""
    os.makedirs("logs", exist_ok=True)

def log_batch_cancel(message, wallet_id=None, market_id=None, order_count=None, tx_hash=None):
    """Log batch cancel operations to file with timestamp"""
    ensure_logs_directory()
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Create log entry
    log_entry = {
        "timestamp": timestamp,
        "message": message,
        "wallet_id": wallet_id,
        "market_id": market_id,
        "order_count": order_count,
        "tx_hash": tx_hash
    }
    
    # Format for file logging
    if wallet_id and market_id and order_count is not None:
        log_line = f"[{timestamp}] {message} | Wallet: {wallet_id} | Market: {market_id} | Orders: {order_count}"
        if tx_hash:
            log_line += f" | TX: {tx_hash}"
    elif wallet_id and order_count is not None:
        log_line = f"[{timestamp}] {message} | Wallet: {wallet_id} | Orders: {order_count}"
        if tx_hash:
            log_line += f" | TX: {tx_hash}"
    elif wallet_id:
        log_line = f"[{timestamp}] {message} | Wallet: {wallet_id}"
    else:
        log_line = f"[{timestamp}] {message}"
    
    # Write to log file
    try:
        with open(BATCH_CANCEL_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    except Exception as e:
        print(f"⚠️  Warning: Could not write to log file: {e}")
    
    # Also print to console
    print(log_line)

def print_header():
    """Print a beautiful header for the batch cancel operation"""
    print("\n" + "=" * 80)
    print("🚨 BATCH CANCEL ALL ORDERS - INJECTIVE TRADING BOT")
    print("=" * 80)
    print("📅 This will cancel ALL open orders across ALL wallets and markets")
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

def print_orders_found(count, market_id):
    """Print when orders are found"""
    if count > 0:
        print(f"      ✅ Found {count} open orders to cancel")
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
    print(f"🎉 BATCH CANCEL COMPLETE!")
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

async def batch_cancel_all_orders():
    print_header()
    
    # Log the start of batch cancel operation
    log_batch_cancel("🚨 BATCH CANCEL OPERATION STARTED")
    
    try:
        # Load configurations
        print(f"\n🔒 Loading configurations...")
        wallets_config = load_wallets_from_env()
        
        with open('config/markets_config.json', 'r') as f:
            markets_config = json.load(f)
        
        # Log configuration summary
        enabled_wallets = [w for w in wallets_config['wallets'] if w.get('enabled', False)]
        enabled_markets = [m for m in markets_config['markets'].values() if m.get('enabled', False)]
        log_batch_cancel(f"📋 Configuration loaded: {len(enabled_wallets)} wallets, {len(enabled_markets)} markets")
        
        # Print summaries
        print_wallet_summary(wallets_config)
        print_market_summary(markets_config)
        
        # Initialize network
        network = Network.testnet()
        indexer_client = IndexerClient(network)
        
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
                # Initialize client for this wallet
                client = AsyncClient(network)
                composer = await client.composer()
                
                # Initialize wallet
                pk = PrivateKey.from_hex(private_key)
                address = pk.to_public_key().to_address()
                
                # Print wallet header
                print_wallet_header(wallet_name, wallet_id, address.to_acc_bech32())
                
                # Log wallet processing start
                log_batch_cancel(f"💰 Processing wallet: {wallet_name}", wallet_id=wallet_id)
                
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
                
                print(f"   ✅ Wallet initialized successfully")
                log_batch_cancel(f"✅ Wallet initialized: {address.to_acc_bech32()}", wallet_id=wallet_id)
                
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
                        # Get orders using indexer client
                        subaccount_id = address.get_subaccount_id(0)
                        
                        # Use testnet_market_id for order cancellation (we're on testnet)
                        testnet_market_id = market_config.get('testnet_market_id')
                        if not testnet_market_id:
                            print(f"      ⚠️  No testnet_market_id found for {market_id}")
                            continue
                        
                        if market_config.get('type') == 'spot':
                            orders = await indexer_client.fetch_spot_orders(
                                market_ids=[testnet_market_id],
                                subaccount_id=subaccount_id
                            )
                        else:
                            orders = await indexer_client.fetch_derivative_orders(
                                market_ids=[testnet_market_id],
                                subaccount_id=subaccount_id
                            )
                        
                        if orders and 'orders' in orders and orders['orders']:
                            orders_to_cancel = [o for o in orders['orders'] if o.get('state') == 'booked']
                            print_orders_found(len(orders_to_cancel), market_id)
                            
                            # Log orders found
                            if len(orders_to_cancel) > 0:
                                log_batch_cancel(f"📊 Found {len(orders_to_cancel)} orders to cancel", 
                                               wallet_id=wallet_id, market_id=market_id, order_count=len(orders_to_cancel))
                            
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
                            log_batch_cancel(f"✅ No orders found", wallet_id=wallet_id, market_id=market_id, order_count=0)
                            
                    except Exception as e:
                        print(f"      ❌ Error processing market {market_id}: {e}")
                
                # Batch cancel spot orders
                if all_spot_orders_data:
                    try:
                        log_batch_cancel(f"🚨 Starting batch cancel for {len(all_spot_orders_data)} spot orders", 
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
                            log_batch_cancel(f"✅ SUCCESS: Cancelled {len(all_spot_orders_data)} spot orders", 
                                           wallet_id=wallet_id, order_count=len(all_spot_orders_data), tx_hash=tx_hash)
                            total_cancelled += len(all_spot_orders_data)
                        else:
                            log_batch_cancel(f"❌ FAILED: Could not cancel {len(all_spot_orders_data)} spot orders", 
                                           wallet_id=wallet_id, order_count=len(all_spot_orders_data))
                            
                    except Exception as e:
                        print_batch_cancel_result("spot", len(all_spot_orders_data), False, error=str(e))
                        log_batch_cancel(f"❌ ERROR: Exception during spot order cancellation: {str(e)}", 
                                       wallet_id=wallet_id, order_count=len(all_spot_orders_data))
                
                # Batch cancel derivative orders
                if all_derivative_orders_data:
                    try:
                        log_batch_cancel(f"🚨 Starting batch cancel for {len(all_derivative_orders_data)} derivative orders", 
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
                            log_batch_cancel(f"✅ SUCCESS: Cancelled {len(all_derivative_orders_data)} derivative orders", 
                                           wallet_id=wallet_id, order_count=len(all_derivative_orders_data), tx_hash=tx_hash)
                            total_cancelled += len(all_derivative_orders_data)
                        else:
                            log_batch_cancel(f"❌ FAILED: Could not cancel {len(all_derivative_orders_data)} derivative orders", 
                                           wallet_id=wallet_id, order_count=len(all_derivative_orders_data))
                            
                    except Exception as e:
                        print_batch_cancel_result("derivative", len(all_derivative_orders_data), False, error=str(e))
                        log_batch_cancel(f"❌ ERROR: Exception during derivative order cancellation: {str(e)}", 
                                       wallet_id=wallet_id, order_count=len(all_derivative_orders_data))
                
                # Close client
                await client.close_chain_channel()
                await client.close_chain_stream_channel()
                
                total_wallets_processed += 1
                log_batch_cancel(f"✅ Wallet processing completed", wallet_id=wallet_id)
                
            except Exception as e:
                print(f"   ❌ Error processing wallet {wallet_id}: {e}")
                log_batch_cancel(f"❌ ERROR: Failed to process wallet: {str(e)}", wallet_id=wallet_id)
        
        # Log final summary
        log_batch_cancel(f"🎉 BATCH CANCEL COMPLETE: {total_cancelled} orders cancelled across {total_wallets_processed} wallets")
        
        # Print final summary
        print_final_summary(total_cancelled, total_wallets_processed)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        log_batch_cancel(f"❌ CRITICAL ERROR: {str(e)}")

if __name__ == "__main__":
    asyncio.run(batch_cancel_all_orders())
