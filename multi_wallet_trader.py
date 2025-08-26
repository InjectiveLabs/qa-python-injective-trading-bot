#!/usr/bin/env python3
"""
Simple Multi-Wallet Parallel Trader for Injective Testnet
Runs multiple wallets in parallel for spot market trading

WHAT THIS SCRIPT DOES:
- Connects to Injective testnet
- Uses 3 different wallets to place trading orders
- Compares prices between mainnet (real prices) and testnet (fake prices)
- If testnet prices are wrong, it places orders to fix them
- Creates lots of small orders to make the orderbook look busy and natural
"""

# These are the Python libraries we need to make this work
import asyncio          # This lets us do multiple things at the same time (like using 3 wallets at once)
import json             # This helps us read configuration files (like wallet settings)
import signal           # This helps us stop the program when you press Ctrl+C
import sys              # This gives us access to system functions
from typing import Dict, List  # This helps Python understand what type of data we're working with
from decimal import Decimal    # This helps us do precise math with money (no rounding errors!)

# These are the Injective blockchain libraries we need to talk to the blockchain
from pyinjective.async_client_v2 import AsyncClient      # Main client to talk to Injective
from pyinjective.indexer_client import IndexerClient     # Client to get market data (prices, orders)
from pyinjective.core.network import Network             # Helps us connect to testnet vs mainnet
from pyinjective.core.broadcaster import MsgBroadcasterWithPk  # Sends our orders to the blockchain
from pyinjective import PrivateKey, Address              # Helps us manage our wallet keys and addresses

# STEP 1: LOAD OUR CONFIGURATION FILES
# These files tell us which markets to trade and which wallets to use

# Load the markets configuration (which trading pairs we want to trade)
print("📁 Loading market configuration...")
with open('markets_config.json', 'r') as f:
    markets_config = json.load(f)  # This reads the file and converts it to Python data

# Load the wallets configuration (which wallets we want to use)
print("📁 Loading wallet configuration...")
with open('wallets_config.json', 'r') as f:
    wallets_config = json.load(f)  # This reads the file and converts it to Python data

# STEP 2: CREATE A LOGGING FUNCTION
# This function helps us print messages with wallet names so we know which wallet is doing what
def log(message: str, wallet_id: str = None):
    """
    This function prints messages with a wallet name prefix
    Example: log("Hello", "wallet_1") prints: [wallet_1] Hello
    """
    prefix = f"[{wallet_id}] " if wallet_id else ""  # Add wallet name if provided
    print(f"{prefix}{message}")

# STEP 3: CREATE THE WALLET TRADER CLASS
# This is like a blueprint for each wallet. Each wallet gets its own "trader" that can work independently
class WalletTrader:
    """
    This class represents one wallet that can trade independently
    Think of it like having 3 separate trading accounts, each with its own:
    - Private key (password to access the wallet)
    - Connection to the blockchain
    - Sequence number (like a transaction counter)
    - Ability to place orders
    """
    
    def __init__(self, wallet_id: str, private_key: str):
        """
        This function is called when we create a new wallet trader
        It sets up all the basic information the wallet needs
        
        wallet_id: A name for this wallet (like "wallet_1", "wallet_2", etc.)
        private_key: The secret key that gives access to this wallet
        """
        # Store the basic information
        self.wallet_id = wallet_id                    # Name of this wallet
        self.private_key = private_key                # Secret key to access this wallet
        
        # Set up the network connection (we're using testnet - fake money for testing)
        self.network = Network.testnet()              # Connect to Injective testnet
        
        # These will be set up later when we initialize the wallet
        self.async_client = None                      # Main connection to Injective
        self.indexer_client = None                    # Connection to get market data
        self.composer = None                          # Helps us create order messages
        self.broadcaster = None                       # Sends our orders to the blockchain
        self.address = None                           # Our wallet's public address
        
        # Account information from the blockchain
        self.sequence = 0                             # Transaction counter (like a receipt number)
        self.account_number = 0                       # Our account number on the blockchain
        
        # Control flags
        self.is_running = False                       # Whether this wallet is currently trading
        self.in_cooldown = False                      # Whether this wallet is temporarily paused
        self.cooldown_until = 0                       # When the cooldown ends
        self.sequence_mismatch_count = 0              # How many times we've had sequence problems
        
    async def initialize(self):
        """
        This function sets up everything the wallet needs to start trading
        It's like logging into your trading account and getting everything ready
        """
        try:
            log(f"🔧 Initializing {self.wallet_id}...", self.wallet_id)
            
            # STEP 1: Create separate clients for this wallet
            # Each wallet gets its own connections so they don't interfere with each other
            self.async_client = AsyncClient(self.network)           # Main client for blockchain operations
            self.indexer_client = IndexerClient(self.network)       # Client for getting market data
            self.composer = await self.async_client.composer()      # Helper for creating order messages
            
            # STEP 2: Set up the wallet identity
            # Convert our private key into a wallet address
            private_key_obj = PrivateKey.from_hex(self.private_key)  # Convert string key to object
            self.address = private_key_obj.to_public_key().to_address()  # Get our wallet address
            
            # STEP 3: Get our account information from the blockchain
            # This tells us our current sequence number and account number
            await self.async_client.fetch_account(self.address.to_acc_bech32())
            
            # IMPORTANT: We access sequence directly without calling get_sequence()
            # get_sequence() would increment the sequence, which we don't want yet
            self.sequence = self.async_client.sequence      # Get current transaction counter
            self.account_number = self.async_client.number  # Get our account number
            
            # STEP 4: Set up the broadcaster (this sends our orders to the blockchain)
            # Get the current gas price and add 10% buffer to make sure our orders go through
            gas_price = await self.async_client.current_chain_gas_price()
            gas_price = int(gas_price * 1.1)  # Add 10% buffer to avoid "out of gas" errors
            
            # Create the broadcaster with our wallet information
            self.broadcaster = MsgBroadcasterWithPk.new_using_gas_heuristics(
                network=self.network,                    # Which network to use (testnet)
                private_key=self.private_key,            # Our wallet's private key
                gas_price=gas_price,                     # How much to pay for gas
                client=self.async_client,                # Our blockchain client
                composer=self.composer,                  # Our order composer
            )
            
            # Success! Log what we've set up
            log(f"✅ Wallet initialized: {self.address.to_acc_bech32()}", self.wallet_id)
            log(f"   Sequence: {self.sequence}, Account: {self.account_number}", self.wallet_id)
            
        except Exception as e:
            # If something goes wrong, log the error and stop
            log(f"❌ Failed to initialize wallet: {e}", self.wallet_id)
            raise  # This stops the program because we can't trade without a working wallet
    
    async def get_market_price(self, market_id: str) -> float:
        """
        This function gets the current price from the testnet (fake market)
        It's like checking the price on a test exchange
        
        market_id: The ID of the market we want to check (like INJ/USDT)
        Returns: The current price as a number (like 15.50 for $15.50)
        """
        try:
            log(f"🔍 Fetching testnet price for {market_id}", self.wallet_id)
            
            # Get the orderbook (list of all buy and sell orders) from testnet
            # We ask for 10 levels of orders (best 10 buy prices and best 10 sell prices)
            orderbook = await asyncio.wait_for(
                self.indexer_client.fetch_spot_orderbook_v2(market_id=market_id, depth=10),
                timeout=10.0  # Wait up to 10 seconds, then give up
            )
            
            # Check if we got valid orderbook data
            if orderbook and 'orderbook' in orderbook:
                # Get the buy orders (people wanting to buy) and sell orders (people wanting to sell)
                buys = orderbook['orderbook'].get('buys', [])    # List of buy orders
                sells = orderbook['orderbook'].get('sells', [])  # List of sell orders
                
                log(f"📊 Testnet buys: {len(buys)}, sells: {len(sells)}", self.wallet_id)
                
                # If we have both buy and sell orders, we can calculate a price
                if buys and sells:
                    # Get the best buy price (highest price someone is willing to pay)
                    best_bid = Decimal(str(buys[0]['price']))
                    # Get the best sell price (lowest price someone is willing to sell for)
                    best_ask = Decimal(str(sells[0]['price']))
                    
                    # IMPORTANT: Blockchain prices are in tiny units, we need to scale them up
                    # For INJ/USDT, we multiply by 10^12 to get the real price
                    price_scale_factor = Decimal('1000000000000')  # 10^12
                    best_bid_scaled = best_bid * price_scale_factor  # Convert to real price
                    best_ask_scaled = best_ask * price_scale_factor  # Convert to real price
                    
                    # Calculate the mid price (average of best buy and best sell)
                    mid_price = float((best_bid_scaled + best_ask_scaled) / 2)
                    log(f"✅ Testnet price: ${mid_price:.4f}", self.wallet_id)
                    return mid_price
            
            # If we couldn't get a price, log a warning
            log(f"⚠️ No testnet price data", self.wallet_id)
            return 0.0
            
        except asyncio.TimeoutError:
            # If the request took too long, log an error
            log(f"❌ Timeout getting testnet price", self.wallet_id)
            return 0.0
        except Exception as e:
            # If any other error occurred, log it
            log(f"❌ Error getting market price: {e}", self.wallet_id)
            return 0.0
    
    async def get_mainnet_price(self, market_symbol: str) -> float:
        """
        This function gets the real market price from Injective mainnet
        This is like checking the real price on a real exchange
        
        market_symbol: The trading pair (like "INJ/USDT")
        Returns: The real market price as a number
        """
        try:
            log(f"🔍 Fetching mainnet price for {market_symbol}", self.wallet_id)
            
            # STEP 1: Connect to mainnet (real Injective network)
            mainnet_network = Network.mainnet()  # Connect to real Injective, not testnet
            mainnet_indexer = IndexerClient(mainnet_network)  # Client to get mainnet data
            
            # STEP 2: Get all available spot markets from mainnet
            # We need to find the right market ID for our trading pair
            markets_response = await asyncio.wait_for(
                mainnet_indexer.fetch_spot_markets(),  # Get list of all spot markets
                timeout=10.0  # Wait up to 10 seconds
            )
            
            # Check if we got valid market data
            if not markets_response or 'markets' not in markets_response:
                log(f"❌ No spot markets found on mainnet", self.wallet_id)
                return 0.0
            
            # STEP 3: Find the specific market we want to trade
            # We need to match our symbol (like "INJ/USDT") with a market ID
            market_id = None
            for market in markets_response['markets']:
                # Get the base token (first part of pair, like "INJ")
                base_symbol = market.get('baseTokenMeta', {}).get('symbol', '')
                # Get the quote token (second part of pair, like "USDT")
                quote_symbol = market.get('quoteTokenMeta', {}).get('symbol', '')
                
                # Check if this market matches our trading pair
                if (base_symbol.upper() == market_symbol.split('/')[0].upper() and 
                    quote_symbol.upper() == market_symbol.split('/')[1].upper()):
                    market_id = market.get('marketId')  # Found it! Get the market ID
                    break
            
            # If we couldn't find the market, log an error
            if not market_id:
                log(f"❌ Market {market_symbol} not found on mainnet", self.wallet_id)
                return 0.0
            
            # STEP 4: Get the orderbook for the market we found
            orderbook = await asyncio.wait_for(
                mainnet_indexer.fetch_spot_orderbook_v2(market_id=market_id, depth=10),
                timeout=10.0
            )
            
            # STEP 5: Calculate the price from the orderbook
            if orderbook and 'orderbook' in orderbook:
                buys = orderbook['orderbook'].get('buys', [])    # Buy orders
                sells = orderbook['orderbook'].get('sells', [])  # Sell orders
                
                if buys and sells:
                    # Same price calculation as testnet
                    best_bid = Decimal(str(buys[0]['price']))
                    best_ask = Decimal(str(sells[0]['price']))
                    
                    # Scale up the prices (blockchain uses tiny units)
                    price_scale_factor = Decimal('1000000000000')  # 10^12
                    best_bid_scaled = best_bid * price_scale_factor
                    best_ask_scaled = best_ask * price_scale_factor
                    
                    # Calculate mid price
                    mid_price = float((best_bid_scaled + best_ask_scaled) / 2)
                    log(f"✅ Mainnet price: ${mid_price:.4f}", self.wallet_id)
                    return mid_price
            
            log(f"⚠️ No mainnet price data", self.wallet_id)
            return 0.0
            
        except asyncio.TimeoutError:
            log(f"❌ Timeout getting mainnet price", self.wallet_id)
            return 0.0
        except Exception as e:
            log(f"❌ Error getting mainnet price: {e}", self.wallet_id)
            return 0.0
    
    async def place_order(self, market_id: str, side: str, price: float, quantity: float) -> bool:
        """
        This function places a single order on the blockchain
        It's like submitting a buy or sell order to an exchange
        
        market_id: Which market to trade (like INJ/USDT)
        side: "BUY" or "SELL"
        price: How much to pay/sell for (like $15.50)
        quantity: How much to buy/sell (like 5.0 INJ)
        Returns: True if order was placed successfully, False if it failed
        """
        try:
            # STEP 1: Format the price correctly
            # Blockchain requires prices to be in specific increments (tick size)
            # For INJ/USDT, tick size is 0.001, so $15.123 is valid, but $15.1234 is not
            price_decimal = Decimal(str(price))                    # Convert to Decimal for precise math
            quantity_decimal = Decimal(str(quantity))              # Convert quantity to Decimal
            tick_size = Decimal("0.001")                           # Minimum price increment
            price_rounded = (price_decimal / tick_size).quantize(Decimal("1")) * tick_size  # Round to valid price
            
            # STEP 2: Create the order message
            # This is like filling out an order form
            order_msg = self.composer.msg_create_spot_limit_order(
                sender=self.address.to_acc_bech32(),               # Our wallet address
                market_id=market_id,                               # Which market to trade
                subaccount_id=self.address.get_subaccount_id(0),   # Our subaccount (like a folder in our wallet)
                fee_recipient=self.address.to_acc_bech32(),        # Who gets the trading fees (us)
                price=price_rounded,                               # The price we want
                quantity=quantity_decimal,                         # How much we want to trade
                order_type=side.upper(),                           # BUY or SELL
                cid=None                                           # No custom ID needed
            )
            
            # STEP 3: Send the order to the blockchain
            log(f"📤 Placing {side} order: {quantity} INJ at ${price:.4f}", self.wallet_id)
            response = await self.broadcaster.broadcast([order_msg])  # Send the order
            
            # STEP 4: Check if the order was successful
            tx_hash = response.get('txhash', 'unknown')  # Get the transaction hash (like a receipt number)
            log(f"✅ Order placed successfully! TX: {tx_hash}", self.wallet_id)
            return True
            
        except Exception as e:
            # If something went wrong, log the error
            log(f"❌ Failed to place order: {e}", self.wallet_id)
            return False
    
    async def place_rich_orderbook(self, market_id: str, testnet_price: float, mainnet_price: float, market_symbol: str):
        """
        This function creates a "rich orderbook" by placing many small orders
        Instead of placing one big order, we place many small orders at different prices
        This makes the market look more active and natural
        
        market_id: Which market to trade
        testnet_price: Current price on testnet
        mainnet_price: Real price on mainnet
        market_symbol: Trading pair name (like "INJ/USDT")
        """
        try:
            # STEP 1: Check if this wallet is in cooldown (temporarily paused)
            if await self.check_cooldown():
                log(f"⏸️ {self.wallet_id} skipping order placement due to cooldown", self.wallet_id)
                return
            
            log(f"🎯 Creating rich orderbook for {market_symbol}", self.wallet_id)
            
            # STEP 2: Figure out which direction to move the price
            # Calculate how much the testnet price differs from the real price
            price_diff = abs(testnet_price - mainnet_price)
            price_diff_percent = (price_diff / mainnet_price) * 100
            
            if testnet_price < mainnet_price:
                # Testnet price is too low, we need to push it UP by placing BUY orders
                side = "BUY"
                base_price = testnet_price
                movement = "UP"
                log(f"📈 {self.wallet_id} - Price difference: {price_diff_percent:.2f}% | Pushing price UP from ${testnet_price:.4f} → ${mainnet_price:.4f}", self.wallet_id)
            else:
                # Testnet price is too high, we need to push it DOWN by placing SELL orders
                side = "SELL"
                base_price = testnet_price
                movement = "DOWN"
                log(f"📉 {self.wallet_id} - Price difference: {price_diff_percent:.2f}% | Pushing price DOWN from ${testnet_price:.4f} → ${mainnet_price:.4f}", self.wallet_id)
            
            # STEP 3: Set up tracking variables
            orders_placed = 0      # How many orders we successfully placed
            total_quantity = 0     # Total amount of INJ we traded
            
            # STEP 4: Create randomized order sizes
            # We want different sized orders to make the orderbook look natural
            import random
            # List of possible order sizes from 0.1 INJ to 10.0 INJ
            order_sizes = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]  # INJ
            random.shuffle(order_sizes)  # Mix up the order randomly
            order_sizes = order_sizes[:10]  # Take the first 10 sizes for this cycle
            
            # STEP 5: Create price levels for our orders
            # We'll place orders at slightly different prices to create depth
            if side == "BUY":
                # For BUY orders, place them slightly above current price
                # This pushes the price UP
                price_levels = [
                    base_price * 1.001,  # +0.1% above current price
                    base_price * 1.002,  # +0.2% above current price
                    base_price * 1.003,  # +0.3% above current price
                    base_price * 1.004,  # +0.4% above current price
                    base_price * 1.005,  # +0.5% above current price
                    base_price * 1.006,  # +0.6% above current price
                    base_price * 1.007,  # +0.7% above current price
                    base_price * 1.008,  # +0.8% above current price
                    base_price * 1.009,  # +0.9% above current price
                    base_price * 1.010,  # +1.0% above current price
                ]
            else:
                # For SELL orders, place them slightly below current price
                # This pushes the price DOWN
                price_levels = [
                    base_price * 0.999,  # -0.1% below current price
                    base_price * 0.998,  # -0.2% below current price
                    base_price * 0.997,  # -0.3% below current price
                    base_price * 0.996,  # -0.4% below current price
                    base_price * 0.995,  # -0.5% below current price
                    base_price * 0.994,  # -0.6% below current price
                    base_price * 0.993,  # -0.7% below current price
                    base_price * 0.992,  # -0.8% below current price
                    base_price * 0.991,  # -0.9% below current price
                    base_price * 0.990,  # -1.0% below current price
                ]
            
            # STEP 6: Place orders at each price level
            # We'll place one order at each price level with a different size
            for i, (price, size) in enumerate(zip(price_levels, order_sizes)):
                # Check if we should stop immediately (user pressed Ctrl+C)
                if not self.is_running:
                    log(f"🛑 Stopping order placement for {self.wallet_id}", self.wallet_id)
                    break
                
                # Check if wallet is in cooldown (temporarily paused due to errors)
                if await self.check_cooldown():
                    log(f"⏸️ {self.wallet_id} skipping order {i+1} due to cooldown", self.wallet_id)
                    continue
                
                # STEP 7: Double-check our sequence number before placing order
                # This helps prevent "sequence mismatch" errors
                try:
                    await self.async_client.fetch_account(self.address.to_acc_bech32())
                    current_sequence = self.async_client.sequence
                    if current_sequence != self.sequence:
                        log(f"⚠️ {self.wallet_id} - Sequence mismatch detected before order {i+1}: expected {self.sequence}, got {current_sequence}", self.wallet_id)
                        self.sequence = current_sequence  # Update our local sequence
                        log(f"🔄 {self.wallet_id} - Sequence corrected to {self.sequence}", self.wallet_id)
                except Exception as seq_error:
                    log(f"⚠️ {self.wallet_id} - Could not verify sequence before order {i+1}: {seq_error}", self.wallet_id)
                    
                # STEP 8: Place the actual order
                try:
                    log(f"📤 {self.wallet_id} - Placing {side} order {i+1}: {size} INJ at ${price:.4f} (moving price {movement})", self.wallet_id)
                    success = await self.place_order(market_id, side, price, size)
                    
                    if success:
                        # Order was placed successfully!
                        orders_placed += 1
                        total_quantity += size
                        log(f"   ✅ {self.wallet_id} - {side} order {i+1} SUCCESS: {size} INJ at ${price:.4f}", self.wallet_id)
                        
                        # STEP 9: Wait 5 seconds before placing the next order
                        # This prevents "sequence mismatch" errors
                        for _ in range(5):
                            if not self.is_running:  # Check if user wants to stop
                                break
                            await asyncio.sleep(1)  # Wait 1 second
                        
                        # STEP 10: Refresh our sequence number from the blockchain
                        # This ensures our local sequence matches the blockchain
                        try:
                            await self.async_client.fetch_account(self.address.to_acc_bech32())
                            self.sequence = self.async_client.sequence
                            log(f"   🔄 {self.wallet_id} - Sequence synced: {self.sequence}", self.wallet_id)
                        except Exception as e:
                            log(f"   ⚠️ {self.wallet_id} - Failed to sync sequence: {e}", self.wallet_id)
                    else:
                        # Order failed to place
                        log(f"   ❌ {self.wallet_id} - Failed to place {side} order {i+1}", self.wallet_id)
                    
                except Exception as e:
                    # Something went wrong while placing the order
                    log(f"   ❌ {self.wallet_id} - Error placing {side} order {i+1}: {e}", self.wallet_id)
                    
                    # STEP 11: Check if this is a sequence mismatch error
                    # If so, put this wallet in cooldown to prevent more errors
                    error_str = str(e).lower()
                    if "account sequence mismatch" in error_str or "incorrect account sequence" in error_str:
                        log(f"   🛑 {self.wallet_id} - Sequence mismatch detected, entering 10s cooldown", self.wallet_id)
                        await self.enter_cooldown(10)  # Pause this wallet for 10 seconds
                        break  # Stop placing more orders for this wallet
                    
                    continue  # Try the next order
            
            # STEP 12: Log summary of what we accomplished
            log(f"🎯 Rich orderbook created: {orders_placed} orders, {total_quantity:.1f} INJ total", self.wallet_id)
            
        except Exception as e:
            log(f"❌ Error creating rich orderbook: {e}", self.wallet_id)
    
    async def refresh_sequence(self):
        """
        This function refreshes our sequence number from the blockchain
        The sequence number is like a transaction counter - it must always be correct
        """
        try:
            await self.async_client.fetch_account(self.address.to_acc_bech32())
            self.sequence = self.async_client.sequence
            log(f"🔄 Sequence refreshed for {self.wallet_id}: {self.sequence}", self.wallet_id)
            return True
        except Exception as e:
            log(f"❌ Failed to refresh sequence for {self.wallet_id}: {e}", self.wallet_id)
            return False
    
    async def enter_cooldown(self, duration: int = 10):
        """
        This function puts a wallet in "cooldown" mode
        Cooldown means the wallet is temporarily paused to prevent errors
        
        duration: How many seconds to pause (default 10 seconds)
        """
        import time
        self.in_cooldown = True                           # Mark wallet as in cooldown
        self.cooldown_until = time.time() + duration      # Calculate when cooldown ends
        self.sequence_mismatch_count += 1                 # Count how many times we've had problems
        log(f"🛑 {self.wallet_id} entering {duration}s cooldown (mismatch #{self.sequence_mismatch_count})", self.wallet_id)
    
    async def check_cooldown(self):
        """
        This function checks if a wallet is still in cooldown mode
        Returns: True if wallet is in cooldown, False if it's ready to trade
        """
        import time
        if self.in_cooldown:
            if time.time() >= self.cooldown_until:
                # Cooldown is finished, reactivate the wallet
                self.in_cooldown = False
                log(f"✅ {self.wallet_id} cooldown finished, refreshing sequence", self.wallet_id)
                
                # Refresh sequence after cooldown with retry logic
                # We try up to 3 times in case the first attempts fail
                for attempt in range(3):
                    try:
                        await asyncio.sleep(1)  # Wait a bit before refreshing
                        await self.async_client.fetch_account(self.address.to_acc_bech32())
                        self.sequence = self.async_client.sequence
                        log(f"🔄 {self.wallet_id} - Sequence refreshed to {self.sequence} after cooldown (attempt {attempt+1})", self.wallet_id)
                        break  # Success! Exit the retry loop
                    except Exception as refresh_error:
                        log(f"❌ {self.wallet_id} - Failed to refresh sequence after cooldown (attempt {attempt+1}): {refresh_error}", self.wallet_id)
                        if attempt == 2:  # Last attempt
                            log(f"⚠️ {self.wallet_id} - Could not refresh sequence, will try again later", self.wallet_id)
                
                return False  # Wallet is ready to trade again
            else:
                # Still in cooldown, show how much time is left
                remaining = int(self.cooldown_until - time.time())
                log(f"⏳ {self.wallet_id} in cooldown: {remaining}s remaining", self.wallet_id)
                return True  # Wallet is still in cooldown
        return False  # Wallet is not in cooldown
    
    async def trading_loop(self, market_id: str, market_symbol: str):
        """
        This is the main trading loop for this wallet
        It runs continuously, checking prices and placing orders when needed
        
        market_id: Which market to trade
        market_symbol: Trading pair name (like "INJ/USDT")
        """
        self.is_running = True  # Mark this wallet as active
        log(f"🚀 Starting trading loop for {market_symbol} ({market_id})", self.wallet_id)
        
        # This loop runs forever until we stop it
        while self.is_running:
            try:
                # Check if we should stop immediately (user pressed Ctrl+C)
                if not self.is_running:
                    break
                
                # STEP 1: Get current prices from both testnet and mainnet
                testnet_price = await self.get_market_price(market_id)      # Price on testnet (fake)
                mainnet_price = await self.get_mainnet_price(market_symbol) # Price on mainnet (real)
                
                # STEP 2: If we got valid prices, analyze the difference
                if testnet_price > 0 and mainnet_price > 0:
                    # Calculate how much the prices differ
                    price_diff = abs(testnet_price - mainnet_price)
                    price_diff_percent = (price_diff / mainnet_price) * 100
                    
                    # Figure out which direction we need to move the price
                    if testnet_price > mainnet_price:
                        direction = "DOWN"  # Testnet price is too high, need to push it down
                        arrow = "📉"
                    else:
                        direction = "UP"    # Testnet price is too low, need to push it up
                        arrow = "📈"
                    
                    # Log the current situation
                    log(f"💰 {self.wallet_id} - {market_symbol} | Mainnet: ${mainnet_price:.4f} | Testnet: ${testnet_price:.4f} | Diff: {price_diff_percent:.2f}% | Need to push {arrow} {direction}", self.wallet_id)
                    
                    # STEP 3: If price difference is significant (>5%), place orders to fix it
                    if price_diff_percent > 5:
                        # Create rich orderbook with multiple smaller orders
                        await self.place_rich_orderbook(market_id, testnet_price, mainnet_price, market_symbol)
                
                # STEP 4: Wait 10 seconds before checking prices again
                # We check for stop signal every second during the wait
                for _ in range(10):
                    if not self.is_running:  # User wants to stop
                        break
                    await asyncio.sleep(1)  # Wait 1 second
                
            except Exception as e:
                # If something goes wrong in the trading loop, log it and continue
                log(f"❌ Error in trading loop: {e}", self.wallet_id)
                if self.is_running:
                    await asyncio.sleep(10)  # Wait 10 seconds before trying again
    
    def stop(self):
        """
        This function stops the trading loop for this wallet
        Called when user presses Ctrl+C or when we want to shut down
        """
        self.is_running = False  # Tell the trading loop to stop
        log(f"🛑 Stopping trading loop", self.wallet_id)

# STEP 4: MAIN FUNCTION
# This is the main function that runs everything
async def main():
    """
    This is the main function that sets up and runs all the wallet traders
    It's like the conductor of an orchestra - it coordinates all the wallets
    """
    log("🚀 Starting Multi-Wallet Parallel Trader")
    
    # STEP 1: Get the list of enabled wallets from our configuration
    enabled_wallets = []
    for wallet_config in wallets_config['wallets']:
        if wallet_config.get('enabled', False):  # Only use wallets that are enabled
            enabled_wallets.append({
                'id': wallet_config['id'],                    # Wallet name (like "wallet_1")
                'private_key': wallet_config['private_key']   # Wallet's secret key
            })
    
    # Check if we have any wallets to work with
    if not enabled_wallets:
        log("❌ No enabled wallets found!")
        return
    
    log(f"📋 Found {len(enabled_wallets)} enabled wallets")
    
    # STEP 2: Get the list of enabled markets from our configuration
    enabled_markets = []
    for market_symbol, market_config in markets_config['markets'].items():
        if market_config.get('enabled', False) and market_config.get('type') == 'spot':
            # Only use markets that are enabled and are spot markets (not derivatives)
            enabled_markets.append({
                'symbol': market_symbol,                    # Trading pair name (like "INJ/USDT")
                'market_id': market_config['market_id']     # Market ID on the blockchain
            })
    
    # Check if we have any markets to trade
    if not enabled_markets:
        log("❌ No enabled spot markets found!")
        return
    
    log(f"📊 Found {len(enabled_markets)} enabled spot markets")
    for market in enabled_markets:
        log(f"   {market['symbol']}: {market['market_id']}")
    
    # STEP 3: Create and initialize all wallet traders
    traders = []
    for wallet_data in enabled_wallets:
        # Create a new trader for each wallet
        trader = WalletTrader(wallet_data['id'], wallet_data['private_key'])
        await trader.initialize()  # Set up the wallet
        traders.append(trader)     # Add to our list of traders
    
    # STEP 4: Set up signal handling for graceful shutdown
    # This allows us to stop the program when user presses Ctrl+C
    def signal_handler(signum, frame):
        log("🛑 Received shutdown signal, stopping all traders...")
        for trader in traders:
            trader.stop()  # Stop each trader
    
    signal.signal(signal.SIGINT, signal_handler)   # Handle Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Handle termination signal
    
    # STEP 5: Start trading loops for each wallet and market combination
    tasks = []
    for trader in traders:
        for market in enabled_markets:
            # Create a task for each wallet trading each market
            # This allows all wallets to trade all markets simultaneously
            task = asyncio.create_task(trader.trading_loop(market['market_id'], market['symbol']))
            tasks.append(task)
    
    log(f"🎯 Started {len(tasks)} trading tasks ({len(traders)} wallets × {len(enabled_markets)} markets)")
    
    # STEP 6: Wait for all trading tasks to complete
    try:
        # This runs all the trading tasks in parallel
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        # User pressed Ctrl+C
        log("🛑 Keyboard interrupt received")
    except Exception as e:
        # Something went wrong in the main loop
        log(f"❌ Error in main loop: {e}")
    finally:
        # Always stop all traders when we're done
        for trader in traders:
            trader.stop()
        log("✅ All traders stopped")

# STEP 5: RUN THE PROGRAM
# This is the entry point - when you run this script, this is what happens
if __name__ == "__main__":
    # Run the main function using asyncio (for parallel operations)
    asyncio.run(main())
