#!/usr/bin/env python3
"""
Wallet Generator for Injective Testnet
Generates wallets from a single mnemonic phrase using BIP44 derivation
"""

import json
import os
from mnemonic import Mnemonic
from eth_account import Account
from pyinjective import PrivateKey

# Enable HD wallet derivation
Account.enable_unaudited_hdwallet_features()

def generate_wallets(num_wallets=20, mnemonic_phrase=None):
    """
    Generate wallets from mnemonic using BIP44 derivation path
    Injective uses: m/44'/60'/0'/0/{index}
    """
    # Generate or use provided mnemonic
    if not mnemonic_phrase:
        mnemo = Mnemonic("english")
        mnemonic_phrase = mnemo.generate(strength=256)  # 24 words
        print(f"🔐 Generated new mnemonic phrase (SAVE THIS SECURELY):")
        print(f"   {mnemonic_phrase}\n")
    else:
        print(f"✅ Using provided mnemonic phrase\n")
    
    wallets = []
    
    for i in range(num_wallets):
        # Derive wallet using BIP44 path for Ethereum (60)
        derivation_path = f"m/44'/60'/0'/0/{i}"
        account = Account.from_mnemonic(mnemonic_phrase, account_path=derivation_path)
        
        # Get private key in hex format (without 0x prefix)
        # Ensure it's padded to 64 characters (32 bytes)
        private_key_hex = account.key.hex()[2:].zfill(64)
        
        # Generate Injective address using pyinjective
        priv_key_obj = PrivateKey.from_hex(private_key_hex)
        injective_address = priv_key_obj.to_public_key().to_address().to_acc_bech32()
        
        wallet_info = {
            "id": f"wallet_{i+1}",
            "name": f"Test Wallet {i+1}",
            "index": i,
            "derivation_path": derivation_path,
            "private_key": private_key_hex,
            "injective_address": injective_address,
            "ethereum_address": account.address
        }
        
        wallets.append(wallet_info)
        print(f"✅ Generated {wallet_info['id']}: {injective_address[:20]}...")
    
    return {
        "mnemonic": mnemonic_phrase,
        "network": "testnet",
        "derivation_standard": "BIP44 (m/44'/60'/0'/0/index)",
        "total_wallets": num_wallets,
        "wallets": wallets
    }

def main():
    print("=" * 70)
    print("🏦 INJECTIVE WALLET GENERATOR - TESTNET")
    print("=" * 70)
    
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    
    # Default file path in data directory
    default_full_path = "data/wallets_testnet_FULL.json"
    
    # Option to use existing mnemonic or generate new one
    use_existing = input("\nDo you have an existing mnemonic phrase? (y/n): ").lower()
    
    if use_existing == 'y':
        mnemonic_input = input(f"\nEnter mnemonic phrase OR press Enter to use {default_full_path}: ").strip()
        
        # Check if user pressed Enter (use default file)
        if not mnemonic_input:
            mnemonic_input = default_full_path
        
        # Check if it's a file path
        if os.path.exists(mnemonic_input):
            try:
                with open(mnemonic_input, 'r') as f:
                    data = json.load(f)
                    mnemonic_phrase = data.get('mnemonic')
                    if not mnemonic_phrase:
                        print("❌ No mnemonic found in file!")
                        return
                    print(f"✅ Loaded mnemonic from {mnemonic_input}")
            except Exception as e:
                print(f"❌ Failed to read file: {e}")
                return
        else:
            # Treat as mnemonic phrase directly
            mnemonic_phrase = mnemonic_input
    else:
        mnemonic_phrase = None
    
    # Ask how many wallets to generate
    num_wallets_input = input("\nHow many wallets to generate? (default: 20): ").strip()
    num_wallets = int(num_wallets_input) if num_wallets_input else 20
    
    # Generate wallets
    print(f"\n🔨 Generating {num_wallets} wallets...\n")
    wallet_data = generate_wallets(num_wallets, mnemonic_phrase)
    
    # Save full version (with mnemonic) - FOR YOU
    full_path = "data/wallets_testnet_FULL.json"
    with open(full_path, 'w') as f:
        json.dump(wallet_data, f, indent=2)
    print(f"\n💾 Saved: {full_path} (includes mnemonic - BACKUP THIS)")
    
    # Save dev version (without mnemonic) - FOR DEV TEAM
    dev_data = {
        "network": wallet_data["network"],
        "total_wallets": wallet_data["total_wallets"],
        "wallets": [{
            "id": w["id"],
            "name": w["name"],
            "private_key": w["private_key"],
            "injective_address": w["injective_address"]
        } for w in wallet_data["wallets"]]
    }
    dev_path = "data/wallets_testnet_DEV.json"
    with open(dev_path, 'w') as f:
        json.dump(dev_data, f, indent=2)
    print(f"💾 Saved: {dev_path} (for dev team funding)")
    
    print("\n" + "=" * 70)
    print("✅ GENERATION COMPLETE")
    print("=" * 70)
    print("\n⚠️  SECURITY:")
    print("   1. Files saved to data/ directory (already in .gitignore)")
    print("   2. Keep FULL.json for yourself (has mnemonic for recovery)")
    print("   3. Share DEV.json with dev team (just private keys)")

if __name__ == "__main__":
    main()

