"""
Option Price Cache Service

Pre-fetches and caches historical option OHLC data for replay mode.
Provides O(1) lookup for option prices at any timestamp.

This service is strategy-agnostic - all option strategies benefit automatically.
"""

import pandas as pd
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta
import re


class OptionPriceCache:
    """
    Pre-fetches and caches option OHLC data for a date range.
    
    Usage:
        cache = OptionPriceCache(dhan_client)
        cache.prefetch_option_data('NIFTY', '2025-12-20', '2025-12-26')
        price = cache.get_option_price('NIFTY', 24100, 'CE', '15-Jan', 1735023600)
    """
    
    def __init__(self, dhan_client):
        """
        Initialize with Dhan client.
        
        Args:
            dhan_client: Instance of DhanClient for API calls
        """
        self.client = dhan_client
        
        # Cache structure: {(underlying, strike, type, expiry_normalized): DataFrame}
        self._contract_cache: Dict[Tuple, pd.DataFrame] = {}
        
        # Fast timestamp lookup: {(underlying, strike, type, expiry_normalized, timestamp): price}
        self._price_cache: Dict[Tuple, float] = {}
        
        # Track which contracts we've fetched
        self._fetched_contracts: set = set()
        
        # Security ID cache
        self._security_id_cache: Dict[str, str] = {}
        
        # Store date range for reference
        self.from_date: Optional[str] = None
        self.to_date: Optional[str] = None
        self.is_ready: bool = False
    
    def prefetch_option_data(
        self,
        underlying: str,
        from_date: str,
        to_date: str,
        base_price: float = None,
        strike_range: int = 200,  # OPTIMIZED: +/- 200 points (4 strikes each side for Nifty)
        interval: str = '5',
        max_days: int = 5  # OPTIMIZED: Only prefetch first 5 days max
    ) -> bool:
        """
        Pre-fetch relevant option data before replay starts.
        
        OPTIMIZATIONS:
        - Limits prefetch to first 5 days (can lazy-load more)
        - Only fetches +/- 200 points (4 strikes each side)
        - Only fetches 2 nearest expiries
        
        Args:
            underlying: 'NIFTY' or 'BANKNIFTY'
            from_date: Start date 'YYYY-MM-DD'
            to_date: End date 'YYYY-MM-DD'
            base_price: Current spot price (for determining strike range)
            strike_range: +/- points from spot to fetch (default 200)
            interval: Candle interval ('1', '5', '15', '60')
            max_days: Maximum days to prefetch (default 5)
        
        Returns:
            True if successful, False otherwise
        """
        print(f"[OptionCache] Starting prefetch for {underlying} from {from_date} to {to_date}")
        
        self.from_date = from_date
        self.to_date = to_date
        self._underlying = underlying  # Store for lazy fetch
        self._interval = interval
        
        try:
            # OPTIMIZATION: Limit date range to max_days
            start_dt = datetime.strptime(from_date, '%Y-%m-%d')
            end_dt = datetime.strptime(to_date, '%Y-%m-%d')
            
            if (end_dt - start_dt).days > max_days:
                limited_end = start_dt + timedelta(days=max_days)
                to_date_limited = limited_end.strftime('%Y-%m-%d')
                print(f"[OptionCache] Limiting prefetch to {max_days} days: {from_date} to {to_date_limited}")
            else:
                to_date_limited = to_date
            
            # Determine strike step based on underlying
            strike_step = 50 if underlying == 'NIFTY' else 100
            
            # If no base price, use a reasonable default for current market
            if base_price is None:
                base_price = 24000 if underlying == 'NIFTY' else 52000
            
            # Round to nearest strike
            atm_strike = round(base_price / strike_step) * strike_step
            
            # OPTIMIZATION: Generate fewer strikes (+/- strike_range)
            num_strikes = strike_range // strike_step
            strikes = [atm_strike + (i * strike_step) for i in range(-num_strikes, num_strikes + 1)]
            
            # OPTIMIZATION: Get only 2 nearest expiries
            expiries = self._get_nearest_expiries(from_date, limit=2)
            
            total_contracts = len(strikes) * 2 * len(expiries)
            print(f"[OptionCache] Will fetch {len(strikes)} strikes x 2 types x {len(expiries)} expiries = {total_contracts} contracts")
            
            contracts_fetched = 0
            contracts_failed = 0
            
            for expiry in expiries:
                for strike in strikes:
                    for option_type in ['CE', 'PE']:
                        success = self._fetch_single_contract(
                            underlying, strike, option_type, expiry,
                            from_date, to_date_limited, interval
                        )
                        if success:
                            contracts_fetched += 1
                        else:
                            contracts_failed += 1
            
            print(f"[OptionCache] Prefetch complete: {contracts_fetched} contracts, {contracts_failed} failed")
            self.is_ready = True
            return True
            
        except Exception as e:
            print(f"[OptionCache] Prefetch failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _get_nearest_expiries(self, from_date: str, limit: int = 2) -> List[str]:
        """
        Get the nearest expiry dates (Thursdays) from the start date.
        
        OPTIMIZED: Only returns 'limit' expiries to reduce API calls.
        
        Args:
            from_date: Start date
            limit: Max number of expiries to return
        
        Returns:
            List of expiry dates in 'YYYY-MM-DD' format
        """
        expiries = []
        
        start = datetime.strptime(from_date, '%Y-%m-%d')
        
        # Find Thursdays starting from 1 week before start (in case replay starts mid-week)
        search_start = start - timedelta(days=7)
        
        current = search_start
        while len(expiries) < limit:
            if current.weekday() == 3:  # Thursday
                # Only include if expiry is on or after start date
                if current >= start - timedelta(days=7):
                    expiries.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
            
            # Safety: don't search more than 60 days
            if (current - start).days > 60:
                break
        
        return expiries
    
    def _get_expiries_for_range(self, from_date: str, to_date: str) -> List[str]:
        """
        Get list of expiry dates (Thursdays) that fall within or near the date range.
        Legacy method for full range fetching.
        """
        expiries = []
        
        start = datetime.strptime(from_date, '%Y-%m-%d')
        end = datetime.strptime(to_date, '%Y-%m-%d')
        
        search_start = start - timedelta(days=14)
        search_end = end + timedelta(days=14)
        
        current = search_start
        while current <= search_end:
            if current.weekday() == 3:
                expiries.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
        
        return expiries
    
    def _find_security_id(
        self,
        underlying: str,
        strike: float,
        option_type: str,
        expiry_date: str
    ) -> Optional[str]:
        """
        Find security ID for an option contract using scrip master.
        """
        cache_key = f"{underlying}_{strike}_{option_type}_{expiry_date}"
        
        if cache_key in self._security_id_cache:
            return self._security_id_cache[cache_key]
        
        try:
            # Parse expiry to search format: "NIFTY 15 JAN 2026 24000 CE"
            dt = datetime.strptime(expiry_date, '%Y-%m-%d')
            expiry_str = dt.strftime('%d %b %Y').upper()
            
            search_term = f"{underlying.upper()} {expiry_str} {int(strike)} {option_type.upper()}"
            
            results = self.client.scrip_master.search(search_term)
            
            if results.empty:
                return None
            
            security_id = str(results.iloc[0]['SEM_SMST_SECURITY_ID'])
            self._security_id_cache[cache_key] = security_id
            
            return security_id
            
        except Exception as e:
            return None
    
    def _fetch_single_contract(
        self,
        underlying: str,
        strike: float,
        option_type: str,
        expiry_date: str,
        from_date: str,
        to_date: str,
        interval: str
    ) -> bool:
        """
        Fetch OHLC data for a single option contract and cache it.
        """
        contract_key = (underlying, strike, option_type, expiry_date)
        
        if contract_key in self._fetched_contracts:
            return True
        
        try:
            security_id = self._find_security_id(underlying, strike, option_type, expiry_date)
            
            if not security_id:
                return False
            
            # Fetch from Dhan API
            request_data = {
                'securityId': security_id,
                'exchangeSegment': 'NSE_FNO',
                'instrument': 'OPTIDX',
                'interval': interval,
                'fromDate': f"{from_date} 09:15:00",
                'toDate': f"{to_date} 15:30:00"
            }
            
            response = self.client.session.post(
                f"{self.client.base_url}/charts/intraday",
                json=request_data,
                headers={
                    'Content-Type': 'application/json',
                    'access-token': self.client.access_token
                }
            )
            
            if response.status_code != 200:
                return False
            
            data = response.json()
            
            if not data.get('timestamp'):
                return False
            
            # Create DataFrame
            df = pd.DataFrame({
                'timestamp': data.get('timestamp', []),
                'open': data.get('open', []),
                'high': data.get('high', []),
                'low': data.get('low', []),
                'close': data.get('close', [])
            })
            
            if df.empty:
                return False
            
            # Store in contract cache
            self._contract_cache[contract_key] = df
            self._fetched_contracts.add(contract_key)
            
            # Build fast price lookup cache
            for _, row in df.iterrows():
                price_key = (*contract_key, int(row['timestamp']))
                self._price_cache[price_key] = float(row['close'])
            
            return True
            
        except Exception as e:
            return False
    
    def get_option_price(
        self,
        underlying: str,
        strike: float,
        option_type: str,
        expiry: str,
        timestamp: int
    ) -> Optional[float]:
        """
        Get option price at a specific timestamp.
        
        OPTIMIZED: Attempts lazy fetch if contract not in cache.
        
        Args:
            underlying: 'NIFTY' or 'BANKNIFTY'
            strike: Strike price (e.g., 24100)
            option_type: 'CE' or 'PE'
            expiry: Expiry date (accepts '15-Jan', 'Jan', or 'YYYY-MM-DD')
            timestamp: Unix timestamp
        
        Returns:
            Option close price or None if not available
        """
        # Normalize expiry to YYYY-MM-DD format, using timestamp for year inference
        expiry_normalized = self._normalize_expiry(expiry, reference_timestamp=timestamp)
        
        if not expiry_normalized:
            print(f"[OptionCache] Failed to normalize expiry: {expiry}")
            return None
        
        # Try exact timestamp lookup first (O(1))
        price_key = (underlying, strike, option_type, expiry_normalized, timestamp)
        if price_key in self._price_cache:
            return self._price_cache[price_key]
        
        # Check if contract is in cache
        contract_key = (underlying, strike, option_type, expiry_normalized)
        
        # LAZY FETCH: If contract not in cache, try to fetch it
        if contract_key not in self._contract_cache:
            print(f"[OptionCache] Cache miss for {underlying} {strike} {option_type} ({expiry_normalized}), attempting lazy fetch...")
            if self._try_lazy_fetch(underlying, strike, option_type, expiry_normalized, timestamp):
                # Retry lookup after fetch
                if price_key in self._price_cache:
                    return self._price_cache[price_key]
        
        # Fall back to nearest timestamp lookup
        if contract_key not in self._contract_cache:
            print(f"[OptionCache] Contract not in cache after lazy fetch: {contract_key}")
            return None
        
        df = self._contract_cache[contract_key]
        
        # Find closest timestamp
        df_copy = df.copy()
        df_copy['diff'] = abs(df_copy['timestamp'] - timestamp)
        closest_idx = df_copy['diff'].idxmin()
        
        # Check if within 5 minutes (300 seconds)
        if df_copy.loc[closest_idx, 'diff'] > 300:
            print(f"[OptionCache] Closest timestamp too far: {df_copy.loc[closest_idx, 'diff']}s away")
            return None
        
        return float(df_copy.loc[closest_idx, 'close'])
    
    def _try_lazy_fetch(
        self,
        underlying: str,
        strike: float,
        option_type: str,
        expiry_date: str,
        timestamp: int
    ) -> bool:
        """
        Lazy fetch a single contract on demand (cache miss).
        
        This is called when a signal references a contract not in the prefetch.
        """
        print(f"[OptionCache] Lazy fetching: {strike} {option_type} ({expiry_date})")
        
        # Determine date range around the timestamp
        dt = datetime.fromtimestamp(timestamp)
        from_date = (dt - timedelta(days=1)).strftime('%Y-%m-%d')
        to_date = (dt + timedelta(days=1)).strftime('%Y-%m-%d')
        
        interval = getattr(self, '_interval', '5')
        
        return self._fetch_single_contract(
            underlying, strike, option_type, expiry_date,
            from_date, to_date, interval
        )
    
    def _normalize_expiry(self, expiry: str, reference_timestamp: int = None) -> Optional[str]:
        """
        Normalize expiry string to YYYY-MM-DD format.
        
        Accepts:
            '15-Jan' -> '2026-01-15' (inferred from reference or current year)
            '2026-01-15' -> '2026-01-15'
            'Jan' -> finds next January Thursday
        
        Args:
            expiry: Expiry string in various formats
            reference_timestamp: Unix timestamp for year inference (defaults to now)
        """
        if not expiry:
            return None
        
        # Already in correct format
        if len(expiry) == 10 and '-' in expiry and expiry[4] == '-':
            return expiry
        
        try:
            # Determine reference year from timestamp or current time
            if reference_timestamp:
                ref_dt = datetime.fromtimestamp(reference_timestamp)
                reference_year = ref_dt.year
            else:
                reference_year = datetime.now().year
            
            # Handle '15-Jan' format
            if '-' in expiry and len(expiry) <= 7:
                # Try reference year first
                try:
                    dt = datetime.strptime(f"{expiry}-{reference_year}", '%d-%b-%Y')
                    return dt.strftime('%Y-%m-%d')
                except ValueError:
                    pass
                
                # Try next year
                try:
                    dt = datetime.strptime(f"{expiry}-{reference_year + 1}", '%d-%b-%Y')
                    return dt.strftime('%Y-%m-%d')
                except ValueError:
                    pass
            
            return None
            
        except Exception as e:
            print(f"[OptionCache] Error normalizing expiry '{expiry}': {e}")
            return None
    
    def get_cache_stats(self) -> Dict:
        """Get statistics about the cache."""
        return {
            'contracts_cached': len(self._contract_cache),
            'price_points': len(self._price_cache),
            'fetched_contracts': len(self._fetched_contracts),
            'is_ready': self.is_ready,
            'date_range': f"{self.from_date} to {self.to_date}"
        }


# Global cache instance (singleton pattern for performance)
_global_cache: Optional[OptionPriceCache] = None


def get_option_cache(dhan_client=None) -> OptionPriceCache:
    """
    Get or create the global option price cache.
    
    Args:
        dhan_client: DhanClient instance (required for first call)
    
    Returns:
        OptionPriceCache instance
    """
    global _global_cache
    
    if _global_cache is None and dhan_client is not None:
        _global_cache = OptionPriceCache(dhan_client)
    
    return _global_cache


def clear_option_cache():
    """Clear the global option cache."""
    global _global_cache
    _global_cache = None
