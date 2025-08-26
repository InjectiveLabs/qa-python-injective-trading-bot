"""
Helper utility functions for the Injective Market Making Bot.
"""

import json
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import uuid


def load_json_config(file_path: str) -> Dict[str, Any]:
    """
    Load JSON configuration file.
    
    Args:
        file_path: Path to JSON file
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file is invalid JSON
    """
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Invalid JSON in {file_path}: {e}")


def save_json_config(file_path: str, data: Dict[str, Any]) -> None:
    """
    Save data to JSON configuration file.
    
    Args:
        file_path: Path to JSON file
        data: Data to save
    """
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2, default=str)


def generate_order_id() -> str:
    """
    Generate a unique order ID.
    
    Returns:
        Unique order ID string
    """
    return f"order_{uuid.uuid4().hex[:16]}"


def generate_trade_id() -> str:
    """
    Generate a unique trade ID.
    
    Returns:
        Unique trade ID string
    """
    return f"trade_{uuid.uuid4().hex[:16]}"


def calculate_price_deviation(testnet_price: float, oracle_price: float) -> float:
    """
    Calculate price deviation percentage.
    
    Args:
        testnet_price: Testnet market price
        oracle_price: Mainnet oracle price
        
    Returns:
        Deviation percentage (positive if testnet > oracle)
    """
    if oracle_price == 0:
        return 0.0
    return ((testnet_price - oracle_price) / oracle_price) * 100


def calculate_spread_percentage(bid_price: float, ask_price: float) -> float:
    """
    Calculate spread percentage.
    
    Args:
        bid_price: Bid price
        ask_price: Ask price
        
    Returns:
        Spread percentage
    """
    if bid_price == 0:
        return 0.0
    return ((ask_price - bid_price) / bid_price) * 100


def calculate_order_prices(
    base_price: float,
    spread_percent: float,
    side: str
) -> tuple[float, float]:
    """
    Calculate buy and sell order prices based on spread.
    
    Args:
        base_price: Base price (usually oracle price)
        spread_percent: Spread percentage
        side: "buy" or "sell" to determine which side to prioritize
        
    Returns:
        Tuple of (bid_price, ask_price)
    """
    spread_multiplier = spread_percent / 100.0
    
    if side == "buy":
        # Prioritize buy side - place buy orders closer to base price
        bid_price = base_price * (1 - spread_multiplier * 0.3)
        ask_price = base_price * (1 + spread_multiplier * 0.7)
    elif side == "sell":
        # Prioritize sell side - place sell orders closer to base price
        bid_price = base_price * (1 - spread_multiplier * 0.7)
        ask_price = base_price * (1 + spread_multiplier * 0.3)
    else:
        # Balanced spread
        bid_price = base_price * (1 - spread_multiplier * 0.5)
        ask_price = base_price * (1 + spread_multiplier * 0.5)
    
    return bid_price, ask_price


def format_number(number: float, decimals: int = 8) -> str:
    """
    Format number with specified decimal places.
    
    Args:
        number: Number to format
        decimals: Number of decimal places
        
    Returns:
        Formatted number string
    """
    return f"{number:.{decimals}f}"


def is_within_threshold(value: float, target: float, threshold: float) -> bool:
    """
    Check if value is within threshold of target.
    
    Args:
        value: Value to check
        target: Target value
        threshold: Threshold percentage
        
    Returns:
        True if within threshold
    """
    if target == 0:
        return False
    deviation = abs((value - target) / target) * 100
    return deviation <= threshold


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    Split list into chunks of specified size.
    
    Args:
        lst: List to chunk
        chunk_size: Size of each chunk
        
    Returns:
        List of chunks
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


async def retry_async(
    func,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Retry async function with exponential backoff.
    
    Args:
        func: Async function to retry
        max_retries: Maximum number of retries
        delay: Initial delay between retries
        backoff: Backoff multiplier
        exceptions: Exceptions to catch
        
    Returns:
        Function result
        
    Raises:
        Last exception if all retries fail
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            if attempt < max_retries:
                await asyncio.sleep(delay * (backoff ** attempt))
    
    raise last_exception


def timestamp_to_datetime(timestamp: str) -> datetime:
    """
    Convert timestamp string to datetime object.
    
    Args:
        timestamp: Timestamp string
        
    Returns:
        Datetime object
    """
    try:
        return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    except ValueError:
        # Try parsing as Unix timestamp
        try:
            return datetime.fromtimestamp(float(timestamp))
        except ValueError:
            raise ValueError(f"Unable to parse timestamp: {timestamp}")


def datetime_to_timestamp(dt: datetime) -> str:
    """
    Convert datetime object to ISO timestamp string.
    
    Args:
        dt: Datetime object
        
    Returns:
        ISO timestamp string
    """
    return dt.isoformat()
