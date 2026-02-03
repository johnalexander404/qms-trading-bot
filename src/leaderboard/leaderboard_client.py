"""Leaderboard API client."""

import logging
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class LeaderboardClient:
    """Client for fetching leaderboard data."""
    
    def __init__(self, api_url: str, api_token: str, max_retries: int = 3):
        """
        Initialize leaderboard client.
        
        Args:
            api_url: Leaderboard API endpoint URL
            api_token: Authentication token
            max_retries: Maximum number of retry attempts
        """
        self.api_url = api_url.rstrip("/")
        self.api_token = api_token
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default headers
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        })
    
    def _get_previous_sunday(self) -> str:
        """
        Calculate the date of the previous Sunday.
        
        Returns:
            Date string in YYYY-MM-DD format
        """
        today = datetime.now()
        # Calculate days to subtract to get to the previous Sunday
        # Monday = 0, Sunday = 6
        days_since_sunday = (today.weekday() + 1) % 7
        if days_since_sunday == 0:
            # If today is Sunday, get last Sunday (7 days ago)
            days_since_sunday = 7
        
        previous_sunday = today - timedelta(days=days_since_sunday)
        return previous_sunday.strftime("%Y-%m-%d")
    
    def _get_previous_week_sunday(self) -> str:
        """
        Calculate the date of the Sunday from two weeks ago (previous week).
        
        Returns:
            Date string in YYYY-MM-DD format
        """
        previous_sunday = datetime.strptime(self._get_previous_sunday(), "%Y-%m-%d")
        previous_week_sunday = previous_sunday - timedelta(days=7)
        return previous_week_sunday.strftime("%Y-%m-%d")
    
    def get_top_symbols(self, top_n: int = 5, mom_day: Optional[str] = None, index_id: str = "13") -> List[str]:
        """
        Fetch top N symbols from leaderboard.
        
        Args:
            top_n: Number of top symbols to return (default: 5)
            mom_day: Optional date string in YYYY-MM-DD format. If not provided, uses previous Sunday.
            index_id: Index ID for the leaderboard (default: "13" for SP400)
            
        Returns:
            List of stock symbols (strings)
            
        Raises:
            requests.RequestException: If API request fails
        """
        try:
            # Use provided mom_day or calculate previous Sunday
            if mom_day is None:
                mom_day = self._get_previous_sunday()
            
            # Prepare POST request body
            request_body = {
                "indexId": index_id,
                "algoId": "1",
                "momDay": mom_day
            }
            
            logger.info(f"Fetching top {top_n} symbols from leaderboard API with momDay={mom_day}")
            response = self.session.post(
                self.api_url,
                json=request_body,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Handle different response formats
            if isinstance(data, list):
                # If response is a list of objects
                symbols = []
                for item in data[:top_n]:
                    if isinstance(item, dict):
                        # Try common field names for symbol
                        symbol = item.get("symbol") or item.get("ticker") or item.get("stock") or item.get("code")
                        if symbol:
                            symbols.append(str(symbol).upper())
                    elif isinstance(item, str):
                        symbols.append(item.upper())
            elif isinstance(data, dict):
                # If response is an object with a list field
                items = data.get("data") or data.get("results") or data.get("symbols") or data.get("stocks", [])
                symbols = []
                for item in items[:top_n]:
                    if isinstance(item, dict):
                        symbol = item.get("symbol") or item.get("ticker") or item.get("stock") or item.get("code")
                        if symbol:
                            symbols.append(str(symbol).upper())
                    elif isinstance(item, str):
                        symbols.append(item.upper())
            else:
                raise ValueError(f"Unexpected response format: {type(data)}")
            
            if len(symbols) < top_n:
                logger.warning(f"Only received {len(symbols)} symbols, expected {top_n}")

            logger.info(f"Retrieved {len(symbols)} symbols: {symbols}")
            return symbols[:top_n]

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching leaderboard: {e}")
            raise
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing leaderboard response: {e}")
            raise

    def get_symbols_with_ranks(self, top_n: int = 10, mom_day: Optional[str] = None, index_id: str = "13") -> List[Dict[str, Any]]:
        """
        Fetch top N symbols with their ranks from leaderboard API.

        Args:
            top_n: Number of top symbols to return (default: 10)
            mom_day: Optional date string in YYYY-MM-DD format. If not provided, uses previous Sunday.
            index_id: Index ID for the leaderboard (default: "13" for SP400)

        Returns:
            List of dicts with 'symbol' and 'rank' keys

        Raises:
            requests.RequestException: If API request fails
        """
        if mom_day is None:
            mom_day = self._get_previous_sunday()

        request_body = {
            "indexId": index_id,
            "algoId": "1",
            "momDay": mom_day
        }

        logger.info(f"Fetching top {top_n} symbols with ranks from leaderboard API with momDay={mom_day}")
        response = self.session.post(self.api_url, json=request_body, timeout=30)
        response.raise_for_status()
        data = response.json()

        # API returns list sorted by rank (wgdzscorerank field)
        results = []
        if isinstance(data, list):
            for i, item in enumerate(data[:top_n]):
                if isinstance(item, dict):
                    symbol = item.get("symbol") or item.get("ticker") or item.get("stock") or item.get("code")
                    if symbol:
                        results.append({
                            'symbol': str(symbol).upper(),
                            'rank': item.get('wgdzscorerank', i + 1)
                        })
        elif isinstance(data, dict):
            items = data.get("data") or data.get("results") or data.get("symbols") or data.get("stocks", [])
            for i, item in enumerate(items[:top_n]):
                if isinstance(item, dict):
                    symbol = item.get("symbol") or item.get("ticker") or item.get("stock") or item.get("code")
                    if symbol:
                        results.append({
                            'symbol': str(symbol).upper(),
                            'rank': item.get('wgdzscorerank', i + 1)
                        })

        logger.info(f"Retrieved {len(results)} symbols with ranks")
        return results
