"""
Simple in-memory cache for historical data fetching.
Caches API responses to avoid redundant requests when scrolling.
"""
import time
from typing import Dict, Tuple, Optional
import pandas as pd


class DataCache:
    """Simple LRU-style cache with TTL for historical market data."""
    
    def __init__(self, max_size: int = 100):
        self.cache: Dict[str, Tuple[pd.DataFrame, float, float]] = {}  # key -> (data, timestamp, ttl)
        self.max_size = max_size
        self.access_times: Dict[str, float] = {}  # Track access for LRU
    
    def _generate_key(self, symbol: str, from_date: str, to_date: str, interval: str) -> str:
        """Generate cache key from request parameters."""
        return f"{symbol}:{interval}:{from_date}:{to_date}"
    
    def _is_expired(self, timestamp: float, ttl: float) -> bool:
        """Check if cache entry has expired."""
        return (time.time() - timestamp) > ttl
    
    def _evict_lru(self):
        """Evict least recently used entry if cache is full."""
        if len(self.cache) >= self.max_size:
            # Find LRU entry
            lru_key = min(self.access_times.keys(), key=lambda k: self.access_times[k])
            del self.cache[lru_key]
            del self.access_times[lru_key]
            print(f"Cache evicted LRU entry: {lru_key}")
    
    def get(self, symbol: str, from_date: str, to_date: str, interval: str) -> Optional[pd.DataFrame]:
        """
        Retrieve cached data if available and not expired.
        
        Args:
            symbol: Trading symbol
            from_date: Start date
            to_date: End date
            interval: Timeframe interval
            
        Returns:
            Cached DataFrame or None if not found/expired
        """
        key = self._generate_key(symbol, from_date, to_date, interval)
        
        if key in self.cache:
            data, timestamp, ttl = self.cache[key]
            
            if self._is_expired(timestamp, ttl):
                # Expired - remove it
                del self.cache[key]
                del self.access_times[key]
                print(f"Cache expired: {key}")
                return None
            
            # Update access time
            self.access_times[key] = time.time()
            print(f"Cache HIT: {key} (age: {int(time.time() - timestamp)}s)")
            return data.copy()  # Return a copy to prevent external modification
        
        print(f"Cache MISS: {key}")
        return None
    
    def put(self, symbol: str, from_date: str, to_date: str, interval: str, data: pd.DataFrame, ttl: float = 60.0):
        """
        Store data in cache with TTL.
        
        Args:
            symbol: Trading symbol
            from_date: Start date
            to_date: End date
            interval: Timeframe interval
            data: DataFrame to cache
            ttl: Time to live in seconds (default: 60s)
        """
        if data.empty:
            return  # Don't cache empty results
        
        key = self._generate_key(symbol, from_date, to_date, interval)
        
        # Evict if needed
        self._evict_lru()
        
        # Store with timestamp and TTL
        self.cache[key] = (data.copy(), time.time(), ttl)
        self.access_times[key] = time.time()
        print(f"Cache PUT: {key} (TTL: {ttl}s, {len(data)} rows)")
    
    def clear(self):
        """Clear all cache entries."""
        self.cache.clear()
        self.access_times.clear()
        print("Cache cleared")


# Global cache instance
_global_cache = DataCache(max_size=100)


def get_cache() -> DataCache:
    """Get the global cache instance."""
    return _global_cache
