#!/usr/bin/env python3
"""
Balance Checker Utility for Injective Trading Bot
Checks wallet balances for INJ and other tokens
"""

import asyncio
import sys
import os
from typing import Dict, List, Optional
from decimal import Decimal

# Add parent directory to path to import from utils
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import the secure wallet loader
from utils.secure_wallet_loader import load_wallets_from_env

# Injective imports
from pyinjective.async_client_v2 import AsyncClient
from pyinjective.core.network import Network
from pyinjective import PrivateKey, Address


class BalanceChecker:
    """
    Utility class to check wallet balances on Injective testnet
    """
    
    def __init__(self):
        self.network = Network.testnet()
        self.async_client = AsyncClient(self.network)
        
        # Token name mapping for better readability
        self.token_names = {
            'inj': 'INJ',
            'factory/inj17gkuet8f6pssxd8nycm3qr9d9y699rupv6397z/stinj': 'stINJ (Staked INJ)',
            'factory/inj17vytdwqczqz72j65saukplrktd4gyfme5agf6c/atom': 'ATOM',
            'factory/inj17vytdwqczqz72j65saukplrktd4gyfme5agf6c/tia': 'TIA',
            'factory/inj17vytdwqczqz72j65saukplrktd4gyfme5agf6c/usdc': 'USDC',
            'factory/inj17vytdwqczqz72j65saukplrktd4gyfme5agf6c/weth': 'WETH',
            'factory/inj1pk7jhvjj2lufcghmvr7gl49dzwkk3xj0uqkwfk/hdro': 'HDRO',
            'peggy0x87aB3B4C8661e07D6372361211B96ed4Dc36B1B5': 'USDT (Peggy)'
        }
    
    def get_token_display_name(self, denom: str) -> str:
        """
        Get a human-readable token name
        
        Args:
            denom: Token denomination
            
        Returns:
            Human-readable token name
        """
        return self.token_names.get(denom, denom)
    
    async def get_wallet_all_balances(self, private_key: str) -> Dict:
        """
        Get all token balances for a specific wallet
        
        Args:
            private_key: Wallet private key
            
        Returns:
            Dict with all balance information
        """
        try:
            # Convert private key to address
            private_key_obj = PrivateKey.from_hex(private_key)
            address = private_key_obj.to_public_key().to_address()
            
            # Get account balance using the bank module (correct way for Injective)
            try:
                # Use the bank module to get balances
                balances_response = await self.async_client.fetch_bank_balances(address.to_acc_bech32())
                
                if not balances_response:
                    return {
                        'address': address.to_acc_bech32(),
                        'balances': [],
                        'error': 'No balance response'
                    }
                
                # Extract balances from the response
                balances = []
                if hasattr(balances_response, 'balances'):
                    balances = list(balances_response.balances)
                elif isinstance(balances_response, dict) and 'balances' in balances_response:
                    balances = balances_response['balances']
                    
            except Exception as e:
                return {
                    'address': address.to_acc_bech32(),
                    'balances': [],
                    'error': f'Bank balance fetch failed: {e}'
                }
            
            # Process all balances
            processed_balances = []
            for bal in balances:
                # Handle different balance object formats
                denom = None
                amount = None
                
                if hasattr(bal, 'denom') and hasattr(bal, 'amount'):
                    denom = bal.denom
                    amount = bal.amount
                elif isinstance(bal, dict):
                    denom = bal.get('denom')
                    amount = bal.get('amount')
                
                if denom and amount:
                    # Convert from smallest unit to main unit
                    balance_amount = Decimal(str(amount))
                    
                    # Determine decimals based on token type
                    if denom == 'inj':
                        # INJ has 18 decimals
                        balance = float(balance_amount / Decimal('1000000000000000000'))
                    elif 'usdt' in denom.lower() or 'usdc' in denom.lower():
                        # USDT/USDC typically have 6 decimals
                        balance = float(balance_amount / Decimal('1000000'))
                    elif 'peggy' in denom.lower():
                        # Peggy tokens (Ethereum bridged) typically have 18 decimals
                        balance = float(balance_amount / Decimal('1000000000000000000'))
                    elif 'factory/' in denom:
                        # Factory tokens - try to determine decimals based on token name
                        if 'stinj' in denom.lower():
                            # Staked INJ has 18 decimals
                            balance = float(balance_amount / Decimal('1000000000000000000'))
                        elif any(token in denom.lower() for token in ['atom', 'tia', 'weth']):
                            # ATOM, TIA, WETH typically have 6 decimals
                            balance = float(balance_amount / Decimal('1000000'))
                        else:
                            # Default factory tokens to 6 decimals
                            balance = float(balance_amount / Decimal('1000000'))
                    else:
                        # Default to 6 decimals for unknown tokens
                        balance = float(balance_amount / Decimal('1000000'))
                    
                    # Only include non-zero balances
                    if balance > 0:
                        processed_balances.append({
                            'denom': denom,
                            'balance': balance,
                            'amount_raw': str(amount)
                        })
            
            return {
                'address': address.to_acc_bech32(),
                'balances': processed_balances,
                'error': None
            }
            
        except Exception as e:
            return {
                'address': 'unknown',
                'balances': [],
                'error': str(e)
            }

    async def get_wallet_balance(self, private_key: str, token_denom: str = "inj") -> Dict:
        """
        Get balance for a specific wallet and token
        
        Args:
            private_key: Wallet private key
            token_denom: Token denomination (default: "inj")
            
        Returns:
            Dict with balance information
        """
        try:
            # Convert private key to address
            private_key_obj = PrivateKey.from_hex(private_key)
            address = private_key_obj.to_public_key().to_address()
            
            # Get account balance using the bank module (correct way for Injective)
            try:
                # Use the bank module to get balances
                balances_response = await self.async_client.fetch_bank_balances(address.to_acc_bech32())
                
                if not balances_response:
                    return {
                        'address': address.to_acc_bech32(),
                        'balance': 0.0,
                        'denom': token_denom,
                        'error': 'No balance response'
                    }
                
                # Extract balances from the response
                balances = []
                if hasattr(balances_response, 'balances'):
                    balances = list(balances_response.balances)
                elif isinstance(balances_response, dict) and 'balances' in balances_response:
                    balances = balances_response['balances']
                    
            except Exception as e:
                return {
                    'address': address.to_acc_bech32(),
                    'balance': 0.0,
                    'denom': token_denom,
                    'error': f'Bank balance fetch failed: {e}'
                }
            
            # Find the specific token balance
            balance = 0.0
            for bal in balances:
                # Handle different balance object formats
                denom = None
                amount = None
                
                if hasattr(bal, 'denom') and hasattr(bal, 'amount'):
                    denom = bal.denom
                    amount = bal.amount
                elif isinstance(bal, dict):
                    denom = bal.get('denom')
                    amount = bal.get('amount')
                
                if denom == token_denom and amount:
                    # Convert from smallest unit to main unit
                    balance_amount = Decimal(str(amount))
                    if token_denom == 'inj':
                        # INJ has 18 decimals
                        balance = float(balance_amount / Decimal('1000000000000000000'))
                    else:
                        # For other tokens, assume 6 decimals (common for USDT, etc.)
                        balance = float(balance_amount / Decimal('1000000'))
                    break
            
            return {
                'address': address.to_acc_bech32(),
                'balance': balance,
                'denom': token_denom,
                'error': None
            }
            
        except Exception as e:
            return {
                'address': 'unknown',
                'balance': 0.0,
                'denom': token_denom,
                'error': str(e)
            }
    
    async def check_all_wallets_all_tokens(self) -> List[Dict]:
        """
        Check all token balances for all configured wallets
        
        Returns:
            List of balance information for all wallets with all tokens
        """
        print(f"🔍 Checking ALL token balances for all wallets...")
        
        # Load wallet configuration
        wallets_config = load_wallets_from_env()
        wallets = wallets_config.get('wallets', [])
        
        if not wallets:
            print("❌ No wallets found in configuration!")
            return []
        
        all_wallet_balances = []
        for wallet in wallets:
            if not wallet.get('enabled', False):
                print(f"⏭️  Skipping disabled wallet: {wallet.get('name', wallet.get('id'))}")
                continue
                
            print(f"💰 Checking {wallet.get('name', wallet.get('id'))}...")
            
            balance_info = await self.get_wallet_all_balances(wallet['private_key'])
            
            balance_info['wallet_id'] = wallet.get('id')
            balance_info['wallet_name'] = wallet.get('name')
            balance_info['enabled'] = wallet.get('enabled', False)
            
            all_wallet_balances.append(balance_info)
            
            # Print result
            if balance_info['error']:
                print(f"   ❌ Error: {balance_info['error']}")
            else:
                if balance_info['balances']:
                    print(f"   ✅ Found {len(balance_info['balances'])} tokens:")
                    for token in balance_info['balances']:
                        display_name = self.get_token_display_name(token['denom'])
                        print(f"      💎 {display_name}: {token['balance']:.6f}")
                else:
                    print(f"   ⚠️  No token balances found")
        
        return all_wallet_balances

    async def check_all_wallets(self, token_denom: str = "inj") -> List[Dict]:
        """
        Check balances for all configured wallets
        
        Args:
            token_denom: Token denomination to check (default: "inj")
            
        Returns:
            List of balance information for all wallets
        """
        print(f"🔍 Checking {token_denom.upper()} balances for all wallets...")
        
        # Load wallet configuration
        wallets_config = load_wallets_from_env()
        wallets = wallets_config.get('wallets', [])
        
        if not wallets:
            print("❌ No wallets found in configuration!")
            return []
        
        balances = []
        for wallet in wallets:
            if not wallet.get('enabled', False):
                print(f"⏭️  Skipping disabled wallet: {wallet.get('name', wallet.get('id'))}")
                continue
                
            print(f"💰 Checking {wallet.get('name', wallet.get('id'))}...")
            
            balance_info = await self.get_wallet_balance(
                wallet['private_key'], 
                token_denom
            )
            
            balance_info['wallet_id'] = wallet.get('id')
            balance_info['wallet_name'] = wallet.get('name')
            balance_info['enabled'] = wallet.get('enabled', False)
            
            balances.append(balance_info)
            
            # Print result
            if balance_info['error']:
                print(f"   ❌ Error: {balance_info['error']}")
            else:
                print(f"   ✅ Balance: {balance_info['balance']:.4f} {token_denom.upper()}")
        
        return balances
    
    async def check_wallet_by_id(self, wallet_id: str, token_denom: str = "inj") -> Optional[Dict]:
        """
        Check balance for a specific wallet by ID
        
        Args:
            wallet_id: Wallet ID (e.g., "wallet_1")
            token_denom: Token denomination to check
            
        Returns:
            Balance information for the specific wallet
        """
        # Load wallet configuration
        wallets_config = load_wallets_from_env()
        wallets = wallets_config.get('wallets', [])
        
        # Find the specific wallet
        target_wallet = None
        for wallet in wallets:
            if wallet.get('id') == wallet_id:
                target_wallet = wallet
                break
        
        if not target_wallet:
            print(f"❌ Wallet {wallet_id} not found!")
            return None
        
        if not target_wallet.get('enabled', False):
            print(f"⚠️  Wallet {wallet_id} is disabled!")
            return None
        
        print(f"💰 Checking {target_wallet.get('name', wallet_id)}...")
        
        balance_info = await self.get_wallet_balance(
            target_wallet['private_key'], 
            token_denom
        )
        
        balance_info['wallet_id'] = target_wallet.get('id')
        balance_info['wallet_name'] = target_wallet.get('name')
        balance_info['enabled'] = target_wallet.get('enabled', False)
        
        # Print result
        if balance_info['error']:
            print(f"❌ Error: {balance_info['error']}")
        else:
            print(f"✅ Balance: {balance_info['balance']:.4f} {token_denom.upper()}")
        
        return balance_info
    
    def print_all_tokens_summary(self, all_wallet_balances: List[Dict]):
        """
        Print a comprehensive summary of all tokens across all wallets
        
        Args:
            all_wallet_balances: List of wallet balance information with all tokens
        """
        print(f"\n📊 COMPLETE TOKEN PORTFOLIO SUMMARY:")
        print("=" * 60)
        
        # Collect all unique tokens and their total balances
        token_totals = {}
        wallet_count = 0
        
        for wallet_data in all_wallet_balances:
            if wallet_data['error']:
                print(f"❌ {wallet_data['wallet_name']}: ERROR - {wallet_data['error']}")
                continue
            
            wallet_count += 1
            print(f"\n💰 {wallet_data['wallet_name']} ({wallet_data['wallet_id']}):")
            print(f"   Address: {wallet_data['address']}")
            
            if wallet_data['balances']:
                for token in wallet_data['balances']:
                    denom = token['denom']
                    balance = token['balance']
                    display_name = self.get_token_display_name(denom)
                    
                    print(f"   💎 {display_name}: {balance:.6f}")
                    
                    # Add to totals
                    if denom not in token_totals:
                        token_totals[denom] = 0.0
                    token_totals[denom] += balance
            else:
                print(f"   ⚠️  No token balances found")
        
        # Print totals
        print("\n" + "=" * 60)
        print(f"📈 TOTAL PORTFOLIO VALUE:")
        print("=" * 60)
        
        for denom, total_balance in sorted(token_totals.items()):
            display_name = self.get_token_display_name(denom)
            print(f"💎 {display_name}: {total_balance:.6f}")
        
        print("=" * 60)
        print(f"🎯 Active Wallets: {wallet_count}")
        print(f"🪙 Unique Tokens: {len(token_totals)}")
        
        # Portfolio health check
        if not token_totals:
            print("⚠️  WARNING: No tokens found in any wallet!")
        elif len(token_totals) == 1 and 'inj' in token_totals:
            print("💡 INFO: Only INJ tokens found. Consider diversifying your portfolio.")
        else:
            print("🚀 EXCELLENT: Diversified token portfolio! Ready for advanced trading.")

    def print_balance_summary(self, balances: List[Dict], token_denom: str = "inj"):
        """
        Print a nice summary of all wallet balances
        
        Args:
            balances: List of balance information
            token_denom: Token denomination
        """
        print(f"\n📊 {token_denom.upper()} Balance Summary:")
        print("=" * 50)
        
        total_balance = 0.0
        active_wallets = 0
        
        for balance in balances:
            if balance['error']:
                print(f"❌ {balance['wallet_name']}: ERROR - {balance['error']}")
            else:
                print(f"💰 {balance['wallet_name']}: {balance['balance']:.4f} {token_denom.upper()}")
                total_balance += balance['balance']
                active_wallets += 1
        
        print("=" * 50)
        print(f"📈 Total Balance: {total_balance:.4f} {token_denom.upper()}")
        print(f"🎯 Active Wallets: {active_wallets}")
        
        if total_balance < 10.0:
            print("⚠️  WARNING: Total balance is low! Consider adding more tokens.")
        elif total_balance < 50.0:
            print("💡 INFO: Balance is moderate. Good for testing.")
        else:
            print("🚀 EXCELLENT: High balance! Ready for serious trading.")


async def main():
    """
    Main function for command-line usage
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='Check Injective wallet balances')
    parser.add_argument('--wallet', '-w', help='Check specific wallet ID (e.g., wallet_1)')
    parser.add_argument('--token', '-t', default='inj', help='Token denomination to check (default: inj)')
    parser.add_argument('--summary', '-s', action='store_true', help='Show balance summary')
    parser.add_argument('--all-tokens', '-a', action='store_true', help='Show all tokens in all wallets')
    
    args = parser.parse_args()
    
    checker = BalanceChecker()
    
    try:
        if args.all_tokens:
            # Check all tokens in all wallets
            all_wallet_balances = await checker.check_all_wallets_all_tokens()
            checker.print_all_tokens_summary(all_wallet_balances)
        elif args.wallet:
            # Check specific wallet
            balance = await checker.check_wallet_by_id(args.wallet, args.token)
            if balance and args.summary:
                checker.print_balance_summary([balance], args.token)
        else:
            # Check all wallets for specific token
            balances = await checker.check_all_wallets(args.token)
            if args.summary:
                checker.print_balance_summary(balances, args.token)
        
    except KeyboardInterrupt:
        print("\n🛑 Balance check interrupted by user")
    except Exception as e:
        print(f"❌ Error during balance check: {e}")
    finally:
        # Close the async client properly
        try:
            if hasattr(checker.async_client, 'close'):
                await checker.async_client.close()
        except Exception:
            pass  # Ignore close errors


if __name__ == "__main__":
    asyncio.run(main())
