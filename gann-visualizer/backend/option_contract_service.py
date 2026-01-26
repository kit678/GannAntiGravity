"""
Option Contract Service

Unified service for all option contract operations in backtesting.
Consolidates logic from option_data_provider.py and option_price_cache.py
with proper year inference, timezone handling, and fallback chains.

Features:
- Context-aware contract resolution (backtest date → correct year)
- Multi-layer caching (memory for prices, security IDs)
- Graceful fallback for expired/missing contracts
- IST timezone handling throughout
"""

import pandas as pd
import requests
import re
import pytz
from typing import Optional, Dict, Tuple, List, Any
from datetime import datetime, timedelta
from dataclasses import dataclass


# IST Timezone - All operations use this explicitly
IST = pytz.timezone('Asia/Kolkata')


@dataclass
class ContractInfo:
    """Represents a resolved option contract."""
    underlying: str
    strike: int
    option_type: str  # 'CE' or 'PE'
    expiry_date: str  # Normalized YYYY-MM-DD format
    security_id: str
    trading_symbol: str
    
    def cache_key(self) -> str:
        return f"{self.underlying}_{self.strike}_{self.option_type}_{self.expiry_date}"


@dataclass  
class PriceResult:
    """Result of a price lookup with source information."""
    price: float
    source: str  # 'exact', 'nearest_bar', 'day_close', 'interpolated', 'failed'
    timestamp_diff: int  # Seconds difference from requested timestamp
    
    @property
    def is_reliable(self) -> bool:
        return self.source in ('exact', 'nearest_bar')


class OptionContractService:
    """
    Unified service for all option contract operations.
    
    Usage:
        service = OptionContractService(dhan_client)
        
        # Resolve a contract
        contract = service.resolve_contract('NIFTY', 24100, 'CE', '16-Jan', 
                                            reference_date=signal_datetime)
        
        # Get price at timestamp
        result = service.get_price_at_timestamp(contract, unix_timestamp)
        
        # Enrich strategy signals (convenience method)
        df = service.enrich_strategy_signals(df, underlying='NIFTY')
    """
    
    def __init__(self, dhan_client):
        """
        Initialize with Dhan client.
        
        Args:
            dhan_client: Instance of DhanClient for API calls and scrip master
        """
        self.client = dhan_client
        
        # Caches
        self.contract_cache: Dict[str, ContractInfo] = {}  # cache_key -> ContractInfo
        self.security_id_cache: Dict[str, str] = {}  # search_key -> security_id
        self.ohlc_cache: Dict[str, pd.DataFrame] = {}  # contract_cache_key -> DataFrame
        
        # Statistics
        self.stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'api_calls': 0,
            'fallbacks_used': 0
        }
    
    def resolve_contract(
        self,
        underlying: str,
        strike: float,
        option_type: str,
        expiry_str: str,
        reference_date: datetime
    ) -> Optional[ContractInfo]:
        """
        Resolve option contract to ContractInfo with proper year inference.
        
        Args:
            underlying: 'NIFTY', 'BANKNIFTY'
            strike: Strike price (e.g., 24100)
            option_type: 'CE' or 'PE'
            expiry_str: '16-Jan' or 'Jan2026' or '2026-01-16'
            reference_date: The backtest signal date (for year inference)
            
        Returns:
            ContractInfo with security_id, normalized_expiry, trading_symbol
            or None if resolution fails
        """
        if reference_date is None:
            print("[OptionContractService] WARNING: reference_date is None, using current time")
            reference_date = datetime.now(IST)
        
        # Ensure reference_date is timezone-aware
        if reference_date.tzinfo is None:
            reference_date = IST.localize(reference_date)
        
        # Normalize inputs
        strike_int = int(float(strike))
        opt_type = option_type.upper()
        underlying_upper = underlying.upper()
        
        # Parse and normalize expiry with year inference
        expiry_normalized = self._normalize_expiry(expiry_str, reference_date)
        if expiry_normalized is None:
            print(f"[OptionContractService] Failed to normalize expiry: {expiry_str}")
            return None
        
        # Check cache first
        cache_key = f"{underlying_upper}_{strike_int}_{opt_type}_{expiry_normalized}"
        if cache_key in self.contract_cache:
            self.stats['cache_hits'] += 1
            return self.contract_cache[cache_key]
        
        self.stats['cache_misses'] += 1
        
        # Find security ID from scrip master
        security_id, trading_symbol = self._find_security_id(
            underlying_upper, strike_int, opt_type, expiry_normalized
        )
        
        if security_id is None:
            print(f"[OptionContractService] Could not find security ID for {cache_key}")
            return None
        
        # Create and cache ContractInfo
        contract = ContractInfo(
            underlying=underlying_upper,
            strike=strike_int,
            option_type=opt_type,
            expiry_date=expiry_normalized,
            security_id=security_id,
            trading_symbol=trading_symbol or cache_key
        )
        
        self.contract_cache[cache_key] = contract
        return contract
    
    def _normalize_expiry(self, expiry_str: str, reference_date: datetime) -> Optional[str]:
        """
        Normalize expiry string to YYYY-MM-DD format with proper year inference.
        
        Handles:
            '16-Jan' -> '2026-01-16' (year inferred from reference_date)
            'Jan2026' -> '2026-01-30' (last Thursday of month)
            '2026-01-16' -> '2026-01-16' (pass-through)
        """
        expiry_str = expiry_str.strip()
        
        # Format 1: Already YYYY-MM-DD
        if re.match(r'^\d{4}-\d{2}-\d{2}$', expiry_str):
            return expiry_str
        
        # Format 2: DD-Mon (e.g., '16-Jan')
        match_dd_mon = re.match(r'^(\d{1,2})-([A-Za-z]{3})$', expiry_str)
        if match_dd_mon:
            day = int(match_dd_mon.group(1))
            month_str = match_dd_mon.group(2).capitalize()
            
            # Map month name to number
            month_map = {
                'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
            }
            
            if month_str not in month_map:
                print(f"[OptionContractService] Unknown month: {month_str}")
                return None
            
            month = month_map[month_str]
            
            # Year inference logic:
            # If reference is Dec and expiry month is Jan/Feb, use next year
            # If reference is Jan/Feb and expiry month is Dec, use previous year
            ref_year = reference_date.year
            ref_month = reference_date.month
            
            if ref_month >= 11 and month <= 2:
                # Late in year, expiry is early next year
                year = ref_year + 1
            elif ref_month <= 2 and month >= 11:
                # Early in year, expiry is late previous year (unlikely but handle)
                year = ref_year - 1
            else:
                year = ref_year
            
            try:
                expiry_dt = datetime(year, month, day)
                return expiry_dt.strftime('%Y-%m-%d')
            except ValueError as e:
                print(f"[OptionContractService] Invalid date {year}-{month}-{day}: {e}")
                return None
        
        # Format 3: MonYYYY (e.g., 'Jan2026') - Monthly expiry
        match_mon_year = re.match(r'^([A-Za-z]{3})(\d{4})$', expiry_str)
        if match_mon_year:
            month_str = match_mon_year.group(1).capitalize()
            year = int(match_mon_year.group(2))
            
            month_map = {
                'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
            }
            
            if month_str not in month_map:
                return None
            
            month = month_map[month_str]
            
            # Find last Thursday of the month
            last_day = self._get_last_thursday_of_month(year, month)
            return last_day.strftime('%Y-%m-%d')
        
        print(f"[OptionContractService] Unrecognized expiry format: {expiry_str}")
        return None
    
    def _get_last_thursday_of_month(self, year: int, month: int) -> datetime:
        """Get the last Thursday of a given month."""
        # Start from last day of month
        if month == 12:
            next_month = datetime(year + 1, 1, 1)
        else:
            next_month = datetime(year, month + 1, 1)
        
        last_day = next_month - timedelta(days=1)
        
        # Walk backwards to find Thursday (weekday 3)
        while last_day.weekday() != 3:
            last_day -= timedelta(days=1)
        
        return last_day
    
    def _find_security_id(
        self,
        underlying: str,
        strike: int,
        option_type: str,
        expiry_date: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Find security ID from scrip master.
        
        Returns:
            Tuple of (security_id, trading_symbol) or (None, None)
        """
        # Parse expiry for search format
        try:
            expiry_dt = datetime.strptime(expiry_date, '%Y-%m-%d')
        except ValueError:
            return None, None
        
        # Format: NIFTY-Jan2026-24100-CE
        mon_year = expiry_dt.strftime('%b%Y')  # Jan2026
        search_query = f"{underlying}-{mon_year}-{strike}-{option_type}"
        
        # Check cache
        if search_query in self.security_id_cache:
            return self.security_id_cache[search_query], search_query
        
        print(f"[OptionContractService] Searching scrip master: {search_query}")
        
        try:
            results = self.client.scrip_master.search(search_query)
            
            if results.empty:
                print(f"[OptionContractService] No results for {search_query}")
                return None, None
            
            # Look for exact match
            exact_mask = results['SEM_TRADING_SYMBOL'] == search_query
            exact_results = results[exact_mask]
            
            if not exact_results.empty:
                # Handle duplicates by preferring latest expiry
                if len(exact_results) > 1 and 'SEM_EXPIRY_DATE' in exact_results.columns:
                    exact_results = exact_results.copy()
                    exact_results['expiry_dt'] = pd.to_datetime(exact_results['SEM_EXPIRY_DATE'])
                    exact_results = exact_results.sort_values('expiry_dt', ascending=False)
                
                security_id = str(exact_results.iloc[0]['SEM_SMST_SECURITY_ID'])
                trading_symbol = str(exact_results.iloc[0]['SEM_TRADING_SYMBOL'])
            else:
                # Fuzzy match - take first result
                security_id = str(results.iloc[0]['SEM_SMST_SECURITY_ID'])
                trading_symbol = str(results.iloc[0]['SEM_TRADING_SYMBOL'])
                print(f"[OptionContractService] Fuzzy match: {trading_symbol}")
            
            self.security_id_cache[search_query] = security_id
            return security_id, trading_symbol
            
        except Exception as e:
            print(f"[OptionContractService] Scrip master search error: {e}")
            return None, None
    
    def get_price_at_timestamp(
        self,
        contract: ContractInfo,
        timestamp: int,
        from_date: str = None,
        to_date: str = None,
        interval: str = '5'
    ) -> PriceResult:
        """
        Get option premium at specific timestamp with fallback chain.
        
        Fallback Chain:
        1. Exact timestamp match
        2. Nearest bar within 5 minutes
        3. Nearest bar within 1 hour (with warning)
        4. Day's close price (with warning)
        5. Failed (returns None price)
        
        Args:
            contract: Resolved ContractInfo
            timestamp: Unix timestamp (seconds)
            from_date: Optional fetch range start (YYYY-MM-DD)
            to_date: Optional fetch range end (YYYY-MM-DD)
            interval: Timeframe ('1', '5', '15', '60')
            
        Returns:
            PriceResult with price and source information
        """
        cache_key = contract.cache_key()
        
        # Ensure we have OHLC data
        if cache_key not in self.ohlc_cache:
            # Derive date range from timestamp if not provided
            ts_dt = datetime.fromtimestamp(timestamp, tz=IST)
            
            if from_date is None:
                from_date = (ts_dt - timedelta(days=1)).strftime('%Y-%m-%d')
            if to_date is None:
                to_date = (ts_dt + timedelta(days=1)).strftime('%Y-%m-%d')
            
            # Fetch and cache OHLC data
            df = self._fetch_option_ohlc(contract, from_date, to_date, interval)
            
            if df is None or df.empty:
                return PriceResult(price=0.0, source='failed', timestamp_diff=0)
            
            self.ohlc_cache[cache_key] = df
        
        df = self.ohlc_cache[cache_key]
        
        # Find price with fallback chain
        return self._find_price_with_fallback(df, timestamp)
    
    def _fetch_option_ohlc(
        self,
        contract: ContractInfo,
        from_date: str,
        to_date: str,
        interval: str
    ) -> Optional[pd.DataFrame]:
        """Fetch OHLC data for an option contract from Dhan API."""
        self.stats['api_calls'] += 1
        
        try:
            request_data = {
                'securityId': contract.security_id,
                'exchangeSegment': 'NSE_FNO',
                'instrument': 'OPTIDX',
                'interval': interval,
                'oi': True,
                'fromDate': f"{from_date} 09:15:00",
                'toDate': f"{to_date} 15:30:00"
            }
            
            url = "https://api.dhan.co/v2/charts/intraday"
            
            response = requests.post(
                url,
                json=request_data,
                headers=self.client.headers
            )
            
            if response.status_code != 200:
                print(f"[OptionContractService] API error {response.status_code}: {response.text[:200]}")
                return None
            
            data = response.json()
            
            df = pd.DataFrame({
                'timestamp': data.get('timestamp', []),
                'open': data.get('open', []),
                'high': data.get('high', []),
                'low': data.get('low', []),
                'close': data.get('close', []),
                'volume': data.get('volume', [])
            })
            
            if df.empty:
                print(f"[OptionContractService] No data returned for {contract.trading_symbol}")
                return None
            
            print(f"[OptionContractService] Fetched {len(df)} bars for {contract.trading_symbol}")
            return df
            
        except Exception as e:
            print(f"[OptionContractService] Fetch error: {e}")
            return None
    
    def _find_price_with_fallback(self, df: pd.DataFrame, timestamp: int) -> PriceResult:
        """Find price at timestamp with fallback chain."""
        
        # Calculate time differences
        df = df.copy()
        df['time_diff'] = abs(df['timestamp'] - timestamp)
        
        # Sort by time difference
        df_sorted = df.sort_values('time_diff')
        
        if df_sorted.empty:
            return PriceResult(price=0.0, source='failed', timestamp_diff=0)
        
        closest = df_sorted.iloc[0]
        time_diff = int(closest['time_diff'])
        
        # Determine source based on time difference
        if time_diff == 0:
            source = 'exact'
        elif time_diff <= 300:  # 5 minutes
            source = 'nearest_bar'
        elif time_diff <= 3600:  # 1 hour
            source = 'nearest_bar'
            self.stats['fallbacks_used'] += 1
            print(f"[OptionContractService] WARNING: Using bar {time_diff}s away from target")
        else:
            source = 'day_close'
            self.stats['fallbacks_used'] += 1
            print(f"[OptionContractService] WARNING: Large time gap ({time_diff}s), using nearest available")
        
        return PriceResult(
            price=float(closest['close']),
            source=source,
            timestamp_diff=time_diff
        )
    
    def enrich_strategy_signals(
        self,
        signals_df: pd.DataFrame,
        underlying: str = 'NIFTY',
        interval: str = '5'
    ) -> pd.DataFrame:
        """
        Convenience method to enrich strategy signals with option prices.
        
        Replaces index-based signal_price with actual option premiums.
        This is the main integration point for strategies.
        
        Args:
            signals_df: DataFrame with signals (timestamp, signal, signal_label, signal_price)
            underlying: 'NIFTY' or 'BANKNIFTY'
            interval: Timeframe for option data
            
        Returns:
            Modified DataFrame with option prices
        """
        df = signals_df.copy()
        
        # Determine date range
        from_date = pd.to_datetime(df['timestamp'].min(), unit='s').strftime('%Y-%m-%d')
        to_date = pd.to_datetime(df['timestamp'].max(), unit='s').strftime('%Y-%m-%d')
        
        # Get signal rows
        signal_mask = df['signal'] != 0
        signal_rows = df[signal_mask]
        
        if signal_rows.empty:
            print("[OptionContractService] No signals to enrich")
            return df
        
        print(f"[OptionContractService] Enriching {len(signal_rows)} signals...")
        
        # Track active contract for exits
        active_contract: Optional[ContractInfo] = None
        
        for idx, row in signal_rows.iterrows():
            signal_label = str(row.get('signal_label', ''))
            timestamp = int(row['timestamp'])
            reference_date = datetime.fromtimestamp(timestamp, tz=IST)
            
            # Parse entry signal: "Buy 24100 CE (16-Jan) | SL:..."
            match = re.search(r'(\d+)\s+(CE|PE)\s+\(([^)]+)\)', signal_label)
            
            contract = None
            
            if match:
                # Entry signal
                strike = float(match.group(1))
                option_type = match.group(2)
                expiry = match.group(3)
                
                contract = self.resolve_contract(
                    underlying, strike, option_type, expiry, reference_date
                )
                
                if contract:
                    active_contract = contract
                    
            elif active_contract and 'Exit' in signal_label:
                # Exit signal - use active contract
                contract = active_contract
                active_contract = None  # Clear after exit
            
            # Fetch price if we have a contract
            if contract:
                result = self.get_price_at_timestamp(
                    contract, timestamp, from_date, to_date, interval
                )
                
                if result.price > 0:
                    df.loc[idx, 'signal_price'] = result.price
                    action = 'Entry' if match else 'Exit'
                    print(f"  {action}: {contract.trading_symbol} @ ₹{result.price:.2f} ({result.source})")
                else:
                    print(f"  WARNING: Failed to get price for {contract.trading_symbol}")
        
        # Print stats
        print(f"[OptionContractService] Stats: {self.stats}")
        
        return df
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            **self.stats,
            'contracts_cached': len(self.contract_cache),
            'ohlc_cached': len(self.ohlc_cache),
            'security_ids_cached': len(self.security_id_cache)
        }
    
    def clear_cache(self):
        """Clear all caches."""
        self.contract_cache.clear()
        self.security_id_cache.clear()
        self.ohlc_cache.clear()
        self.stats = {k: 0 for k in self.stats}
        print("[OptionContractService] Cache cleared")
