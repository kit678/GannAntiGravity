"""
Option Data Provider

Fetches and caches historical option data for backtesting with actual option premiums.
Uses Dhan API to retrieve OHLC data for specific option contracts.
"""

import pandas as pd
import requests
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
import re


class OptionDataProvider:
    """
    Provides historical option data for backtesting.
    Handles security ID lookup, data fetching, and caching.
    """
    
    def __init__(self, dhan_client):
        """
        Initialize with Dhan client.
        
        Args:
            dhan_client: Instance of DhanClient for API calls
        """
        self.client = dhan_client
        self.data_cache = {}
        self.security_id_cache = {}
    
    def _find_option_security_id(
        self, 
        underlying: str, 
        strike: float, 
        option_type: str, 
        expiry_date: str,
        reference_date: datetime = None
    ) -> Optional[str]:
        """
        Find security ID for an option contract using scrip master.
        
        Args:
            underlying: 'NIFTY', 'BANKNIFTY', etc.
            strike: Strike price (e.g., 24000)
            option_type: 'CE' or 'PE'
            expiry_date: Date string like '15-Jan' or '2026-01-15'
            reference_date: Reference date for year inference (defaults to now)
        
        Returns:
            Security ID string or None
        """
        cache_key = f"{underlying}_{strike}_{option_type}_{expiry_date}"
        
        if cache_key in self.security_id_cache:
            return self.security_id_cache[cache_key]
        
        try:
            # Normalize Inputs
            strike_int = int(float(strike))
            opt_type = option_type.upper() # CE/PE
            
            # Parse expiry date with year inference
            expiry_dt = self._parse_expiry_with_year(expiry_date, reference_date)
            if expiry_dt is None:
                print(f"[OptionDataProvider] Failed to parse expiry: {expiry_date}")
                return None
            
            # Format 1: Monthly (NIFTY-Jan2026-24000-CE)
            # Use Title Case for Month (Jan, Feb) based on Scrip Master observation
            mon_year = expiry_dt.strftime('%b%Y') # Jan2026
            
            # Primary Search: Exact Match for Monthly Format
            search_query = f"{underlying.upper()}-{mon_year}-{strike_int}-{opt_type}"
            
            print(f"[OptionDataProvider] Searching for: {search_query}")
            
            results = self.client.scrip_master.search(search_query)
            
            if not results.empty:
                # Check for exact symbol match
                match_mask = results['SEM_TRADING_SYMBOL'] == search_query
                exact = results[match_mask].copy()
                
                if not exact.empty:
                    # DUPLICATE SYMBOL HANDLING:
                    # Multiple IDs (Weekly/Monthly) share same Trading Symbol (e.g. NIFTY-Jan2026-...)
                    # We prefer the one with the latest Expiry (Monthly) for better data history
                    if len(exact) > 1 and 'SEM_EXPIRY_DATE' in exact.columns:
                         exact['expiry_dt'] = pd.to_datetime(exact['SEM_EXPIRY_DATE'])
                         exact = exact.sort_values('expiry_dt', ascending=False)
                         
                    security_id = str(exact.iloc[0]['SEM_SMST_SECURITY_ID'])
                    self.security_id_cache[cache_key] = security_id
                    return security_id
                
                # If no exact match, take first result (fuzzy)
                security_id = str(results.iloc[0]['SEM_SMST_SECURITY_ID'])
                self.security_id_cache[cache_key] = security_id
                return security_id
            
            # Fallback Logic
            print(f"[OptionDataProvider] Direct search failed for {search_query}. Trying fuzzy search...")
            
            # Broad Search
            fuzzy_query = f"{underlying.upper()}"
            broad_results = self.client.scrip_master.search(fuzzy_query)
            
            # Filter manually
            mask = (
                (broad_results['SEM_TRADING_SYMBOL'].str.contains(str(strike_int))) & 
                (broad_results['SEM_TRADING_SYMBOL'].str.contains(opt_type)) &
                (broad_results['SEM_TRADING_SYMBOL'].str.contains(mon_year))
            )
            filtered = broad_results[mask]
            
            if not filtered.empty:
                print(f"[OptionDataProvider] Fuzzy match found: {filtered.iloc[0]['SEM_TRADING_SYMBOL']}")
                security_id = str(filtered.iloc[0]['SEM_SMST_SECURITY_ID'])
                self.security_id_cache[cache_key] = security_id
                return security_id

            print(f"[OptionDataProvider] No option found for: {search_query} (and fuzzy failed)")
            return None

        except Exception as e:
            print(f"[OptionDataProvider] Error finding option security ID: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _parse_expiry_with_year(self, expiry_date: str, reference_date: datetime = None) -> Optional[datetime]:
        """
        Parse expiry date string with proper year inference.
        
        Args:
            expiry_date: Date string like '15-Jan', '2026-01-15', or '15-Jan-2026'
            reference_date: Reference date for year inference (defaults to now)
        
        Returns:
            datetime object or None
        """
        try:
            # Already in full format (YYYY-MM-DD)
            if len(expiry_date) == 10 and expiry_date.count('-') == 2:
                return pd.to_datetime(expiry_date)
            
            # Format: DD-Mon-YYYY (e.g., 15-Jan-2026)
            if len(expiry_date) >= 10 and expiry_date.count('-') == 2:
                return pd.to_datetime(expiry_date)
            
            # Format: DD-Mon (e.g., 15-Jan) - needs year inference
            if '-' in expiry_date and len(expiry_date) <= 7:
                ref = reference_date or datetime.now()
                
                # Try parsing with current year first
                try:
                    dt = datetime.strptime(f"{expiry_date}-{ref.year}", '%d-%b-%Y')
                    # If parsed date is more than 6 months in the past, use next year
                    if (ref - dt).days > 180:
                        dt = datetime.strptime(f"{expiry_date}-{ref.year + 1}", '%d-%b-%Y')
                    return dt
                except ValueError:
                    # Try next year
                    try:
                        return datetime.strptime(f"{expiry_date}-{ref.year + 1}", '%d-%b-%Y')
                    except ValueError:
                        pass
            
            # Fallback: let pandas try to parse it
            return pd.to_datetime(expiry_date)
            
        except Exception as e:
            print(f"[OptionDataProvider] Error parsing expiry date '{expiry_date}': {e}")
            return None
    
    def fetch_option_historical_data(
        self,
        security_id: str,
        from_date: str,
        to_date: str,
        interval: str = '5'
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical OHLC data for an option contract.
        
        Args:
            security_id: Option contract security ID
            from_date: Start date 'YYYY-MM-DD'
            to_date: End date 'YYYY-MM-DD'
            interval: Timeframe ('1', '5', '15', '60')
        
        Returns:
            DataFrame with OHLC data or None
        """
        cache_key = f"{security_id}_{from_date}_{to_date}_{interval}"
        
        if cache_key in self.data_cache:
            return self.data_cache[cache_key]
        
        try:
            # Use Dhan API to fetch option data
            # The API endpoint is /v2/charts/intraday with instrument='OPTIDX'
            
            # Build request parameters
            request_data = {
                'securityId': security_id,
                'exchangeSegment': 'NSE_FNO',
                'instrument': 'OPTIDX',
                'interval': interval,
                'oi': True,
                'fromDate': f"{from_date} 09:15:00",
                'toDate': f"{to_date} 15:30:00"
            }
            
            # Make API call
            # Use requests directly as DhanClient doesn't expose session
            url = "https://api.dhan.co/v2/charts/intraday"
            
            response = requests.post(
                url,
                json=request_data,
                headers=self.client.headers
            )
            
            if response.status_code != 200:
                print(f"Failed to fetch option data: {response.status_code} - {response.text}")
                return None
            
            data = response.json()
            
            # Convert to DataFrame
            df = pd.DataFrame({
                'timestamp': data.get('timestamp', []),
                'open': data.get('open', []),
                'high': data.get('high', []),
                'low': data.get('low', []),
                'close': data.get('close', []),
                'volume': data.get('volume', [])
            })
            
            if df.empty:
                print(f"No data returned for option {security_id}")
                return None
            
            # Cache the result
            self.data_cache[cache_key] = df
            
            print(f"Fetched {len(df)} bars for option {security_id}")
            return df
            
        except Exception as e:
            print(f"Error fetching option data: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_option_price_at_timestamp(
        self,
        underlying: str,
        strike: float,
        option_type: str,
        expiry_date: str,
        timestamp: int,
        from_date: str,
        to_date: str,
        interval: str = '5'
    ) -> Optional[float]:
        """
        Get option premium at a specific timestamp.
        
        Args:
            underlying: 'NIFTY', 'BANKNIFTY'
            strike: Strike price
            option_type: 'CE' or 'PE'
            expiry_date: Expiry date
            timestamp: Unix timestamp
            from_date: Start date for data fetch
            to_date: End date for data fetch
            interval: Timeframe
        
        Returns:
            Option premium (close price) or None
        """
        # Find security ID (use timestamp for proper year inference)
        reference_date = datetime.fromtimestamp(timestamp) if timestamp else None
        security_id = self._find_option_security_id(
            underlying, strike, option_type, expiry_date, reference_date
        )
        
        if not security_id:
            return None
        
        # Fetch historical data
        df = self.fetch_option_historical_data(
            security_id, from_date, to_date, interval
        )
        
        if df is None or df.empty:
            return None
        
        # Find closest timestamp
        df['time_diff'] = abs(df['timestamp'] - timestamp)
        closest_idx = df['time_diff'].idxmin()
        
        # Check if timestamp is within reasonable range (5 minutes)
        if df.loc[closest_idx, 'time_diff'] > 300:  # 5 minutes
            print(f"Warning: No exact timestamp match, diff = {df.loc[closest_idx, 'time_diff']}s")
        
        return float(df.loc[closest_idx, 'close'])
    
    def enrich_signals_with_option_prices(
        self,
        signals_df: pd.DataFrame,
        underlying: str = 'NIFTY',
        from_date: str = None,
        to_date: str = None,
        interval: str = '5'
    ) -> pd.DataFrame:
        """
        Replace index-based signal prices with actual option premiums.
        
        Args:
            signals_df: DataFrame with signals (must have: timestamp, signal, signal_price, signal_label)
            underlying: Underlying instrument
            from_date: Start date for option data fetch
            to_date: End date for option data fetch
            interval: Timeframe
        
        Returns:
            Modified DataFrame with option prices
        """
        df = signals_df.copy()
        
        # Auto-detect date range if not provided
        if from_date is None:
            from_date = pd.to_datetime(df['timestamp'].min(), unit='s').strftime('%Y-%m-%d')
        if to_date is None:
            to_date = pd.to_datetime(df['timestamp'].max(), unit='s').strftime('%Y-%m-%d')
        
        # Get all signals (Entries and Exits)
        # Using iterrows on filtered DF preserves index which allows updating original DF
        signal_rows = df[df['signal'] != 0]
        
        # State tracking for exits
        active_contract = None  # {strike, option_type, expiry}
        
        print(f"[OptionDataProvider] Enriching {len(signal_rows)} signals...")

        for idx, row in signal_rows.iterrows():
            signal_label = row['signal_label']
            timestamp = row['timestamp']
            
            # Parse option details from signal_label
            # Expected format: "Buy 24100 CE (15-Jan) | SL:24150"
            match = re.search(r'(\d+)\s+(CE|PE)\s+\(([^)]+)\)', signal_label)
            
            current_contract = None
            
            if match:
                # ENTRY SIGNAL (matches regex)
                strike = float(match.group(1))
                option_type = match.group(2)
                expiry = match.group(3)
                
                current_contract = {
                    'strike': strike,
                    'option_type': option_type,
                    'expiry': expiry
                }
                
                # Update active contract state
                active_contract = current_contract
                
            elif active_contract:
                # EXIT SIGNAL (no regex match, but we have an active contract)
                # Use the active contract details to fetch exit price
                current_contract = active_contract
                
                # Check if this looks like an Exit (it should, given loop filter)
                # We could validate 'Exit' in label, but trusting the signal flow is safer
                # Clear active contract after processing this exit
                active_contract = None
            
            else:
                # Unknown signal without context (maybe purely spot based or error)
                continue
                
            # Fetch Price if we resolved a contract
            if current_contract:
                strike = current_contract['strike']
                option_type = current_contract['option_type']
                expiry = current_contract['expiry']
                
                option_price = self.get_option_price_at_timestamp(
                    underlying=underlying,
                    strike=strike,
                    option_type=option_type,
                    expiry_date=expiry,
                    timestamp=timestamp,
                    from_date=from_date,
                    to_date=to_date,
                    interval=interval
                )
                
                if option_price:
                    df.loc[idx, 'signal_price'] = option_price
                    # Optional: Enrich label for exits too?
                    # df.loc[idx, 'signal_label'] += f" | Opt: {option_price}"
                    print(f"Updated signal at {pd.to_datetime(timestamp, unit='s')}: {strike} {option_type} = ₹{option_price} ({'Entry' if match else 'Exit'})")
                else:
                    print(f"Warning: Could not fetch option price for {strike} {option_type} ({expiry})")
        
        return df
