#!/usr/bin/env python3
"""
Secure Wallet Configuration Loader
Loads wallet configurations from environment variables instead of JSON files
This prevents private keys from being stored in version control
"""

import os
import sys
from typing import Dict, List

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()  # This loads the .env file into os.environ
except ImportError:
    print("⚠️ python-dotenv not installed. Install with: pip install python-dotenv")
    print("   Environment variables will be loaded from system environment only.")

def load_wallets_from_env() -> Dict:
    """
    Load wallet configuration from environment variables (SECURE)
    This prevents private keys from being stored in version control
    
    Returns:
        Dict: Wallet configuration in the same format as wallets_config.json
    """
    wallets = []
    
    # Look for wallet configurations in environment variables
    # Format: WALLET_<ID>_PRIVATE_KEY, WALLET_<ID>_NAME, etc.
    wallet_ids = set()
    
    # Find all wallet IDs from environment variables
    for key in os.environ.keys():
        if key.startswith('WALLET_') and key.endswith('_PRIVATE_KEY'):
            wallet_id = key.replace('WALLET_', '').replace('_PRIVATE_KEY', '')
            wallet_ids.add(wallet_id)
    
    # Load each wallet configuration
    for wallet_id in sorted(wallet_ids):
        private_key = os.environ.get(f'WALLET_{wallet_id}_PRIVATE_KEY')
        name = os.environ.get(f'WALLET_{wallet_id}_NAME', f'Wallet {wallet_id}')
        enabled = os.environ.get(f'WALLET_{wallet_id}_ENABLED', 'true').lower() == 'true'
        max_orders = int(os.environ.get(f'WALLET_{wallet_id}_MAX_ORDERS', '5'))
        balance_threshold = int(os.environ.get(f'WALLET_{wallet_id}_BALANCE_THRESHOLD', '100'))
        
        if private_key:
            wallet_config = {
                'id': f'wallet_{wallet_id}',
                'name': name,
                'private_key': private_key,
                'enabled': enabled,
                'max_orders_per_market': max_orders,
                'balance_threshold': balance_threshold
            }
            wallets.append(wallet_config)
            print(f"✅ Loaded wallet: {name} ({'enabled' if enabled else 'disabled'})")
        else:
            print(f"⚠️ Wallet {wallet_id} private key not found in environment variables")
    
    if not wallets:
        print("❌ No wallets found in environment variables!")
        print("💡 Please set WALLET_1_PRIVATE_KEY, WALLET_2_PRIVATE_KEY, etc. in your .env file")
        print("📝 Example .env entries:")
        print("   WALLET_1_PRIVATE_KEY=your_private_key_here")
        print("   WALLET_1_NAME=Primary Market Maker")
        print("   WALLET_1_ENABLED=true")
        sys.exit(1)
    
    return {
        'wallets': wallets,
        'distribution': {
            'strategy': 'round_robin',
            'max_wallets_per_market': len(wallets),
            'min_orders_per_wallet': 1
        }
    }

if __name__ == "__main__":
    # Test the function
    print("🔒 Testing secure wallet loading...")
    config = load_wallets_from_env()
    print(f"📊 Loaded {len(config['wallets'])} wallets")
    for wallet in config['wallets']:
        print(f"   - {wallet['name']}: {wallet['id']} ({'enabled' if wallet['enabled'] else 'disabled'})")
