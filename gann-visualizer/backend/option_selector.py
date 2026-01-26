"""
Option Selector Module

Utility for selecting appropriate options contracts based on signal direction.
Uses Dhan Option Chain API to fetch available strikes and select ATM options.

This module is designed for future live trading integration.
Currently, backtesting uses index point-based P&L calculation.
"""

import requests
from typing import Dict, Any, Optional, List
from datetime import datetime, date


class OptionSelector:
    """
    Selects appropriate options contract based on signal direction.
    Uses Dhan Option Chain API to fetch available strikes.
    
    Usage:
        selector = OptionSelector(access_token, client_id)
        option = selector.select_option_for_signal(
            signal_type='BUY',  # or 'SELL'
            underlying='NIFTY',
            underlying_price=24500.0
        )
    """
    
    # Security IDs for common underlyings (from Dhan scrip master)
    UNDERLYING_ID_MAP = {
        'NIFTY': 13,       # NIFTY 50 Index
        'BANKNIFTY': 25,   # Bank Nifty Index
        'FINNIFTY': 27,    # Fin Nifty Index
    }
    
    # Lot sizes for index options
    LOT_SIZE_MAP = {
        'NIFTY': 50,
        'BANKNIFTY': 15,
        'FINNIFTY': 40,
    }
    
    def __init__(self, access_token: str, client_id: str):
        """
        Initialize Option Selector with Dhan credentials.
        
        Args:
            access_token: Dhan API access token
            client_id: Dhan client ID
        """
        self.access_token = access_token
        self.client_id = client_id
        self.base_url = "https://api.dhan.co/v2"
        
    def _make_request(self, endpoint: str, method: str = 'POST', data: Dict = None) -> Dict:
        """Make API request to Dhan"""
        headers = {
            'Content-Type': 'application/json',
            'access-token': self.access_token,
            'client-id': self.client_id
        }
        
        url = f"{self.base_url}/{endpoint}"
        
        try:
            if method == 'POST':
                response = requests.post(url, json=data, headers=headers)
            else:
                response = requests.get(url, headers=headers)
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Option Chain API Error: {e}")
            return {}
    
    def get_expiry_list(self, underlying: str) -> List[str]:
        """
        Get list of available expiry dates for an underlying.
        
        Args:
            underlying: 'NIFTY', 'BANKNIFTY', or 'FINNIFTY'
            
        Returns:
            List of expiry dates in 'YYYY-MM-DD' format
        """
        security_id = self.UNDERLYING_ID_MAP.get(underlying.upper())
        if not security_id:
            return []
        
        data = {
            'UnderlyingScrip': security_id,
            'UnderlyingSeg': 'IDX_I'
        }
        
        response = self._make_request('optionchain/expirylist', data=data)
        return response.get('data', [])
    
    def get_option_chain(self, underlying: str, expiry: str) -> Dict:
        """
        Get full option chain for an underlying and expiry.
        
        Args:
            underlying: 'NIFTY', 'BANKNIFTY', or 'FINNIFTY'
            expiry: Expiry date in 'YYYY-MM-DD' format
            
        Returns:
            Option chain data with all strikes
        """
        security_id = self.UNDERLYING_ID_MAP.get(underlying.upper())
        if not security_id:
            return {}
        
        data = {
            'UnderlyingScrip': security_id,
            'UnderlyingSeg': 'IDX_I',
            'Expiry': expiry
        }
        
        response = self._make_request('optionchain', data=data)
        return response.get('data', {})
    
    def get_atm_strike(self, underlying_price: float, strikes: List[float], 
                       strike_interval: float = 50.0) -> float:
        """
        Get the At-The-Money (ATM) strike price.
        
        Args:
            underlying_price: Current price of the underlying
            strikes: List of available strike prices
            strike_interval: Strike price interval (50 for NIFTY, 100 for BANKNIFTY)
            
        Returns:
            ATM strike price
        """
        if not strikes:
            # Fallback: round to nearest interval
            return round(underlying_price / strike_interval) * strike_interval
        
        # Find nearest strike
        return min(strikes, key=lambda x: abs(x - underlying_price))
    
    def get_nearest_expiry(self, underlying: str) -> Optional[str]:
        """Get the nearest (weekly) expiry date."""
        expiries = self.get_expiry_list(underlying)
        if expiries:
            # Sort and return first (nearest)
            return sorted(expiries)[0]
        return None
    
    def select_option_for_signal(
        self, 
        signal_type: str, 
        underlying: str, 
        underlying_price: float,
        expiry: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Select appropriate option based on trading signal.
        
        Args:
            signal_type: 'BUY' (for calls on bullish) or 'SELL' (for puts on bearish)
            underlying: 'NIFTY', 'BANKNIFTY', or 'FINNIFTY'
            underlying_price: Current price of the underlying
            expiry: Optional expiry date, defaults to nearest expiry
            
        Returns:
            Dictionary with option details:
            {
                'underlying': str,
                'strike': float,
                'option_type': 'CE' or 'PE',
                'expiry': str,
                'ltp': float,
                'lot_size': int
            }
        """
        # Get expiry if not provided
        if not expiry:
            expiry = self.get_nearest_expiry(underlying)
            if not expiry:
                print(f"No expiry found for {underlying}")
                return None
        
        # Get option chain
        chain = self.get_option_chain(underlying, expiry)
        if not chain:
            print(f"Failed to fetch option chain for {underlying}")
            return None
        
        # Extract strikes
        oc_data = chain.get('oc', {})
        strikes = [float(k) for k in oc_data.keys()]
        
        if not strikes:
            print("No strikes found in option chain")
            return None
        
        # Find ATM strike
        atm_strike = self.get_atm_strike(underlying_price, strikes)
        strike_data = oc_data.get(f"{atm_strike:.6f}", {})
        
        # Determine option type based on signal
        # BUY signal = bullish = buy CE (Call)
        # SELL signal = bearish = buy PE (Put)
        if signal_type.upper() == 'BUY':
            option_type = 'CE'
            option_data = strike_data.get('ce', {})
        else:
            option_type = 'PE'
            option_data = strike_data.get('pe', {})
        
        if not option_data:
            print(f"No {option_type} data for strike {atm_strike}")
            return None
        
        return {
            'underlying': underlying.upper(),
            'strike': atm_strike,
            'option_type': option_type,
            'expiry': expiry,
            'ltp': option_data.get('last_price', 0),
            'bid': option_data.get('top_bid_price', 0),
            'ask': option_data.get('top_ask_price', 0),
            'oi': option_data.get('oi', 0),
            'iv': option_data.get('implied_volatility', 0),
            'lot_size': self.LOT_SIZE_MAP.get(underlying.upper(), 1),
            'greeks': option_data.get('greeks', {})
        }


# Convenience function for quick ATM selection
def get_atm_option(
    access_token: str,
    client_id: str,
    signal_type: str,
    underlying: str,
    underlying_price: float
) -> Optional[Dict[str, Any]]:
    """
    Quick helper to get ATM option for a signal.
    
    Args:
        access_token: Dhan API access token
        client_id: Dhan client ID
        signal_type: 'BUY' or 'SELL'
        underlying: 'NIFTY', 'BANKNIFTY', or 'FINNIFTY'
        underlying_price: Current underlying price
        
    Returns:
        Option details dict or None
    """
    selector = OptionSelector(access_token, client_id)
    return selector.select_option_for_signal(signal_type, underlying, underlying_price)
