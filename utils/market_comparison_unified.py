#!/usr/bin/env python3
"""
Unified Market Data Comparison Script

This script automatically detects and compares both spot and derivative market data files
between testnet and mainnet environments. It handles different data structures automatically.

Usage:
    python market_comparison_unified.py
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
import argparse


class UnifiedMarketComparator:
    def __init__(self, testnet_file: str, mainnet_file: str):
        self.testnet_file = testnet_file
        self.mainnet_file = mainnet_file
        self.testnet_data = None
        self.mainnet_data = None
        self.market_type = None  # 'spot' or 'derivative'
        
    def detect_market_type(self, data: Dict) -> str:
        """Detect if this is spot or derivative market data."""
        if not data or 'markets' not in data:
            return 'unknown'
        
        # Check first market structure
        first_market = data['markets'][0] if data['markets'] else {}
        
        # Derivative markets have nested 'market' object
        if 'market' in first_market:
            return 'derivative'
        # Spot markets have direct market properties
        elif 'ticker' in first_market:
            return 'spot'
        else:
            return 'unknown'
    
    def load_data(self) -> bool:
        """Load both market data files and detect type."""
        try:
            with open(self.testnet_file, 'r') as f:
                self.testnet_data = json.load(f)
            with open(self.mainnet_file, 'r') as f:
                self.mainnet_data = json.load(f)
            
            # Detect market type from testnet data
            self.market_type = self.detect_market_type(self.testnet_data)
            
            if self.market_type == 'unknown':
                print("Error: Could not determine market type from data structure")
                return False
                
            return True
        except FileNotFoundError as e:
            print(f"Error: {e}")
            return False
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON: {e}")
            return False
    
    def get_market_dict(self, data: Dict) -> Dict[str, Dict]:
        """Convert market list to dictionary keyed by ticker."""
        markets = {}
        
        if self.market_type == 'derivative':
            # Handle derivative markets with nested structure
            for market_item in data.get('markets', []):
                market = market_item.get('market', {})
                ticker = market.get('ticker', '').strip()
                if ticker:
                    markets[ticker] = market
        else:
            # Handle spot markets with direct structure
            for market in data.get('markets', []):
                ticker = market.get('ticker', '').strip()
                if ticker:
                    markets[ticker] = market
                    
        return markets
    
    def get_fields_to_compare(self) -> List[str]:
        """Get the appropriate fields to compare based on market type."""
        if self.market_type == 'derivative':
            # Fields for derivative markets
            return [
                'oracle_type', 'oracle_scale_factor', 'initial_margin_ratio', 
                'maintenance_margin_ratio', 'maker_fee_rate', 'taker_fee_rate', 
                'relayer_fee_share_rate', 'status', 'min_price_tick_size',
                'min_quantity_tick_size', 'min_notional', 'admin', 'admin_permissions', 
                'quote_decimals', 'reduce_margin_ratio'
            ]
        else:
            # Fields for spot markets
            return [
                'maker_fee_rate', 'taker_fee_rate', 'relayer_fee_share_rate', 'status',
                'min_price_tick_size', 'min_quantity_tick_size', 'min_notional',
                'admin', 'admin_permissions', 'base_decimals', 'quote_decimals'
            ]
    
    def compare_markets(self) -> Tuple[Set[str], Set[str], Set[str]]:
        """Compare markets and return common, testnet-only, and mainnet-only sets."""
        testnet_markets = set(self.get_market_dict(self.testnet_data).keys())
        mainnet_markets = set(self.get_market_dict(self.mainnet_data).keys())
        
        common = testnet_markets & mainnet_markets
        testnet_only = testnet_markets - mainnet_markets
        mainnet_only = mainnet_markets - testnet_markets
        
        return common, testnet_only, mainnet_only
    
    def get_configuration_differences(self, ticker: str) -> Dict[str, Dict]:
        """Get configuration differences for a specific market."""
        testnet_markets = self.get_market_dict(self.testnet_data)
        mainnet_markets = self.get_market_dict(self.mainnet_data)
        
        testnet_market = testnet_markets.get(ticker)
        mainnet_market = mainnet_markets.get(ticker)
        
        if not testnet_market or not mainnet_market:
            return {}
        
        differences = {}
        fields_to_compare = self.get_fields_to_compare()
        
        for field in fields_to_compare:
            testnet_value = testnet_market.get(field)
            mainnet_value = mainnet_market.get(field)
            
            if testnet_value != mainnet_value:
                differences[field] = {
                    'testnet': testnet_value,
                    'mainnet': mainnet_value
                }
        
        return differences
    
    def format_differences(self, differences: Dict[str, Dict]) -> str:
        """Format differences in a readable way."""
        if not differences:
            return "  ✓ No configuration differences found"
        
        lines = []
        for field, values in differences.items():
            testnet_val = values['testnet']
            mainnet_val = values['mainnet']
            lines.append(f"    {field}:")
            lines.append(f"      testnet: {testnet_val}")
            lines.append(f"      mainnet: {mainnet_val}")
        
        return "\n".join(lines)
    
    def generate_report(self) -> str:
        """Generate a comprehensive comparison report."""
        if not self.load_data():
            return "Failed to load market data files."
        
        testnet_markets = self.get_market_dict(self.testnet_data)
        mainnet_markets = self.get_market_dict(self.mainnet_data)
        
        common, testnet_only, mainnet_only = self.compare_markets()
        
        # Determine report title based on market type
        market_type_display = self.market_type.capitalize()
        
        report = []
        report.append("=" * 80)
        report.append(f"{market_type_display.upper()} MARKET DATA COMPARISON REPORT")
        report.append("=" * 80)
        report.append("")
        
        # Summary
        report.append("SUMMARY:")
        report.append(f"  Market Type: {market_type_display}")
        report.append(f"  Total markets in testnet: {len(testnet_markets)}")
        report.append(f"  Total markets in mainnet: {len(mainnet_markets)}")
        report.append(f"  Common markets: {len(common)}")
        report.append(f"  Testnet-only markets: {len(testnet_only)}")
        report.append(f"  Mainnet-only markets: {len(mainnet_only)}")
        report.append("")
        
        # Common markets with differences
        if common:
            report.append("COMMON MARKETS (with configuration differences):")
            report.append("-" * 60)
            
            markets_with_differences = []
            markets_without_differences = []
            
            for ticker in sorted(common):
                differences = self.get_configuration_differences(ticker)
                if differences:
                    markets_with_differences.append((ticker, differences))
                else:
                    markets_without_differences.append(ticker)
            
            if markets_with_differences:
                for ticker, differences in markets_with_differences:
                    # Get testnet market_id for this ticker
                    testnet_markets = self.get_market_dict(self.testnet_data)
                    testnet_market_id = testnet_markets.get(ticker, {}).get('market_id', 'N/A')
                    report.append(f"\n{ticker} (Testnet Market ID: {testnet_market_id}):")
                    report.append(self.format_differences(differences))
            else:
                report.append("  ✓ All common markets have identical configurations")
            
            if markets_without_differences:
                report.append(f"\nMarkets with identical configurations ({len(markets_without_differences)}):")
                for ticker in sorted(markets_without_differences):
                    report.append(f"  ✓ {ticker}")
            
            report.append("")
        
        # Testnet-only markets
        if testnet_only:
            report.append("TESTNET-ONLY MARKETS:")
            report.append("-" * 30)
            for ticker in sorted(testnet_only):
                report.append(f"  + {ticker}")
            report.append("")
        
        # Mainnet-only markets
        if mainnet_only:
            report.append("MAINNET-ONLY MARKETS:")
            report.append("-" * 30)
            for ticker in sorted(mainnet_only):
                report.append(f"  + {ticker}")
            report.append("")
        
        # Detailed differences for common markets
        if common and any(self.get_configuration_differences(ticker) for ticker in common):
            report.append("DETAILED CONFIGURATION DIFFERENCES:")
            report.append("=" * 60)
            
            for ticker in sorted(common):
                differences = self.get_configuration_differences(ticker)
                if differences:
                    # Get testnet market_id for this ticker
                    testnet_markets = self.get_market_dict(self.testnet_data)
                    testnet_market_id = testnet_markets.get(ticker, {}).get('market_id', 'N/A')
                    report.append(f"\n{ticker} (Testnet Market ID: {testnet_market_id}):")
                    report.append(self.format_differences(differences))
        
        return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description='Compare testnet and mainnet market data (auto-detects type)')
    parser.add_argument('--testnet', help='Path to testnet market data file')
    parser.add_argument('--mainnet', help='Path to mainnet market data file')
    parser.add_argument('--output', help='Output file path (optional)')
    parser.add_argument('--compare-all', action='store_true', help='Compare both spot and derivative markets automatically')
    
    args = parser.parse_args()
    
    # If --compare-all is used, run both comparisons
    if args.compare_all:
        run_all_comparisons()
        return
    
    # Auto-detect file paths if not provided
    if not args.testnet:
        # Look for testnet files
        possible_testnet_files = [
            'data/testnet_spot_market_data.json',
            'data/testnet_derivative_market_data.json'
        ]
        for file in possible_testnet_files:
            if os.path.exists(file):
                args.testnet = file
                break
    
    if not args.mainnet:
        # Look for mainnet files
        possible_mainnet_files = [
            'data/mainnet_spot_market_data.json',
            'data/mainnet_derivative_market_data.json'
        ]
        for file in possible_mainnet_files:
            if os.path.exists(file):
                args.mainnet = file
                break
    
    if not args.testnet or not args.mainnet:
        print("Error: Could not find market data files. Please specify --testnet and --mainnet paths.")
        print("\nOr use --compare-all to automatically compare both market types.")
        return
    
    # Check if files exist
    if not os.path.exists(args.testnet):
        print(f"Error: Testnet file not found: {args.testnet}")
        return
    
    if not os.path.exists(args.mainnet):
        print(f"Error: Mainnet file not found: {args.mainnet}")
        return
    
    # Generate comparison
    comparator = UnifiedMarketComparator(args.testnet, args.mainnet)
    report = comparator.generate_report()
    
    # Output report
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"Report saved to: {args.output}")
    else:
        print(report)


def run_all_comparisons():
    """Run comparisons for both spot and derivative markets."""
    print("🔍 UNIFIED MARKET COMPARISON TOOL")
    print("=" * 50)
    
    # Check for both market types
    spot_testnet = "data/testnet_spot_market_data.json"
    spot_mainnet = "data/mainnet_spot_market_data.json"
    derivative_testnet = "data/testnet_derivative_market_data.json"
    derivative_mainnet = "data/mainnet_derivative_market_data.json"
    
    comparisons_run = 0
    
    # Compare Spot Markets
    if os.path.exists(spot_testnet) and os.path.exists(spot_mainnet):
        print(f"\n📊 Comparing SPOT markets...")
        print(f"  Testnet: {spot_testnet}")
        print(f"  Mainnet: {spot_mainnet}")
        
        comparator = UnifiedMarketComparator(spot_testnet, spot_mainnet)
        report = comparator.generate_report()
        
        # Save spot report
        output_file = "data/spot_market_comparison_report.txt"
        with open(output_file, 'w') as f:
            f.write(report)
        
        print(f"  ✅ Report saved to: {output_file}")
        comparisons_run += 1
    else:
        print(f"\n❌ SPOT markets: Missing files")
        if not os.path.exists(spot_testnet):
            print(f"    - {spot_testnet} not found")
        if not os.path.exists(spot_mainnet):
            print(f"    - {spot_mainnet} not found")
    
    # Compare Derivative Markets
    if os.path.exists(derivative_testnet) and os.path.exists(derivative_mainnet):
        print(f"\n📈 Comparing DERIVATIVE markets...")
        print(f"  Testnet: {derivative_testnet}")
        print(f"  Mainnet: {derivative_mainnet}")
        
        comparator = UnifiedMarketComparator(derivative_testnet, derivative_mainnet)
        report = comparator.generate_report()
        
        # Save derivative report
        output_file = "data/derivative_market_data_comparison_report.txt"
        with open(output_file, 'w') as f:
            f.write(report)
        
        print(f"  ✅ Report saved to: {output_file}")
        comparisons_run += 1
    else:
        print(f"\n❌ DERIVATIVE markets: Missing files")
        if not os.path.exists(derivative_testnet):
            print(f"    - {derivative_testnet} not found")
        if not os.path.exists(derivative_mainnet):
            print(f"    - {derivative_mainnet} not found")
    
    # Summary
    print(f"\n🎯 SUMMARY")
    print("=" * 50)
    if comparisons_run == 2:
        print("✅ Both market types compared successfully!")
        print("📁 Reports generated:")
        print("   - spot_market_comparison_report.txt")
        print("   - derivative_market_data_comparison_report.txt")
    elif comparisons_run == 1:
        print("⚠️  One market type compared successfully")
    else:
        print("❌ No market comparisons could be completed")
        print("   Please ensure market data files exist in the project root")


if __name__ == "__main__":
    main()
