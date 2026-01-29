"""Webull broker implementation using official OpenAPI SDK."""

import logging
import uuid
from typing import List, Optional
from webullsdkcore.client import ApiClient
from webullsdkcore.common.region import Region
from webullsdktrade.api import API

from ..broker import Broker
from ..models import Allocation

logger = logging.getLogger(__name__)


class WebullBroker(Broker):
    """Webull broker implementation using official OpenAPI SDK."""
    
    def __init__(
        self,
        app_key: str,
        app_secret: str,
        account_id: Optional[str] = None,
        region: str = "US",
    ):
        """
        Initialize Webull broker using official OpenAPI SDK.
        
        Args:
            app_key: Webull App Key (obtained from developer.webull.com)
            app_secret: Webull App Secret (obtained from developer.webull.com)
            account_id: Account ID (optional, will use first account if not provided)
            region: Region code (US, HK, JP) - default: US
        """
        self.app_key = app_key
        self.app_secret = app_secret
        
        # Map region string to Region enum value
        region_map = {
            "US": Region.US.value,
            "HK": Region.HK.value,
            "JP": Region.JP.value,
        }
        region_value = region_map.get(region.upper(), Region.US.value)
        
        # Initialize API client
        self.api_client = ApiClient(app_key, app_secret, region_value)
        self.api = API(self.api_client)
        
        try:
            # Get account ID if not provided
            if not account_id:
                # Try to get account from app subscriptions
                response = self.api.account.get_app_subscriptions()
                if response.status_code == 200:
                    subscriptions = response.json()
                    if subscriptions and len(subscriptions) > 0:
                        account_id = subscriptions[0].get("account_id")
                        logger.info(f"Retrieved account ID from subscriptions: {account_id}")
                
                # If still no account_id, try account list
                if not account_id:
                    response = self.api.account.get_account_list("")
                    if response.status_code == 200:
                        accounts = response.json()
                        if accounts and len(accounts) > 0:
                            account_id = accounts[0].get("account_id")
                            logger.info(f"Retrieved account ID from account list: {account_id}")
                
                if not account_id:
                    raise ValueError("Could not retrieve account ID. Please provide account_id explicitly.")
            
            self.account_id = account_id
            logger.info(f"Using account ID: {self.account_id}")
        except Exception as e:
            logger.error(f"Error initializing Webull broker: {e}")
            raise
    
    def _get_instrument_id(self, symbol: str) -> Optional[str]:
        """
        Get instrument_id for a symbol.
        
        Args:
            symbol: Stock symbol (e.g., "AAPL")
            
        Returns:
            Instrument ID or None if not found
        """
        try:
            # Get instrument info - assuming US_STOCK category
            # Note: You may need to adjust category based on your needs
            response = self.api.instrument.get_instrument(symbol, "US_STOCK")
            if response.status_code == 200:
                instruments = response.json()
                if instruments and len(instruments) > 0:
                    instrument_id = instruments[0].get("instrument_id")
                    return instrument_id
            return None
        except Exception as e:
            logger.error(f"Error getting instrument_id for {symbol}: {e}")
            return None
    
    def get_current_allocation(self) -> List[Allocation]:
        """Get current portfolio allocation."""
        try:
            response = self.api.account.get_account_position(self.account_id)
            if response.status_code != 200:
                logger.error(f"Error getting positions: {response.status_code}")
                return []
            
            positions_data = response.json()
            holdings = positions_data.get("holdings", [])
            allocations = []
            
            for holding in holdings:
                symbol = holding.get("symbol")
                quantity = float(holding.get("qty", 0))
                last_price = float(holding.get("last_price", 0))
                market_value = float(holding.get("market_value", 0))
                
                if quantity > 0 and symbol and last_price > 0:
                    allocations.append(Allocation(
                        symbol=symbol,
                        quantity=quantity,
                        current_price=last_price,
                        market_value=market_value,
                    ))
            
            logger.info(f"Retrieved {len(allocations)} positions from Webull")
            return allocations
        except Exception as e:
            logger.error(f"Error getting positions from Webull: {e}")
            raise
    
    def sell(self, symbol: str, quantity: float) -> bool:
        """Sell a stock."""
        try:
            # Get instrument_id
            instrument_id = self._get_instrument_id(symbol)
            if not instrument_id:
                logger.error(f"Could not get instrument_id for {symbol}")
                return False
            
            # Generate unique client order ID
            client_order_id = f"sell_{symbol}_{uuid.uuid4().hex[:16]}"
            
            # Place sell order
            stock_order = {
                "account_id": self.account_id,
                "stock_order": {
                    "client_order_id": client_order_id,
                    "instrument_id": instrument_id,
                    "side": "SELL",
                    "tif": "DAY",
                    "order_type": "MARKET",
                    "qty": int(quantity),
                }
            }
            
            response = self.api.order.place_order_v2(stock_order)
            
            if response.status_code == 200:
                result = response.json()
                order_id = result.get("order_id") or result.get("client_order_id")
                logger.info(f"Sold {quantity} shares of {symbol}. Order ID: {order_id}")
                return True
            else:
                logger.error(f"Failed to sell {symbol}: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error selling {symbol}: {e}")
            return False
    
    def buy(self, symbol: str, amount: float) -> bool:
        """Buy a stock with a specific dollar amount."""
        try:
            # Get instrument_id
            instrument_id = self._get_instrument_id(symbol)
            if not instrument_id:
                logger.error(f"Could not get instrument_id for {symbol}")
                return False
            
            # Get current price to calculate quantity
            # Try to get price from existing positions first (if we have a position)
            last_price = None
            try:
                positions_response = self.api.account.get_account_position(self.account_id)
                if positions_response.status_code == 200:
                    positions_data = positions_response.json()
                    holdings = positions_data.get("holdings", [])
                    for holding in holdings:
                        if holding.get("symbol") == symbol:
                            last_price = float(holding.get("last_price", 0))
                            if last_price > 0:
                                break
            except Exception as e:
                logger.debug(f"Could not get price from positions: {e}")
            
            # If no position, try to get from instrument data or use estimate
            # Note: For accurate real-time pricing, install webull-python-sdk-quotes-core
            # and use the quotes API. For now, we use a reasonable estimate.
            if not last_price or last_price == 0:
                # Use a conservative estimate - market orders will execute at current market price anyway
                # This is just for calculating approximate quantity
                logger.warning(
                    f"Could not get current price for {symbol} from positions. "
                    f"For accurate pricing, consider installing webull-python-sdk-quotes-core. "
                    f"Using estimated price for quantity calculation."
                )
                # Use a reasonable default estimate (e.g., $50/share)
                # The actual execution will be at market price regardless
                estimated_price = 50.0
                quantity = max(1, int(amount / estimated_price))  # At least 1 share
                logger.info(f"Estimated {quantity} shares for ${amount} at ~${estimated_price}/share")
            else:
                quantity = max(1, int(amount / last_price))  # At least 1 share
                logger.info(f"Calculated {quantity} shares for ${amount} at ${last_price}/share")
            
            quantity = int(amount / last_price)
            if quantity == 0:
                logger.warning(f"Amount ${amount} is too small for {symbol} at ${last_price}")
                return False
            
            # Generate unique client order ID
            client_order_id = f"buy_{symbol}_{uuid.uuid4().hex[:16]}"
            
            # Place buy order
            stock_order = {
                "account_id": self.account_id,
                "stock_order": {
                    "client_order_id": client_order_id,
                    "instrument_id": instrument_id,
                    "side": "BUY",
                    "tif": "DAY",
                    "order_type": "MARKET",
                    "qty": quantity,
                }
            }
            
            response = self.api.order.place_order_v2(stock_order)
            
            if response.status_code == 200:
                result = response.json()
                order_id = result.get("order_id") or result.get("client_order_id")
                logger.info(f"Bought ${amount} worth of {symbol} ({quantity} shares). Order ID: {order_id}")
                return True
            else:
                logger.error(f"Failed to buy {symbol}: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error buying {symbol}: {e}")
            return False
    
    def get_account_cash(self) -> float:
        """Get available cash in the account."""
        try:
            response = self.api.account.get_account_balance(self.account_id)
            if response.status_code != 200:
                logger.error(f"Error getting account balance: {response.status_code}")
                raise ValueError(f"Failed to get account balance: {response.status_code}")
            
            balance_data = response.json()
            
            # Try different possible fields for cash balance
            # Prefer available funds over total cash
            cash = (
                balance_data.get("stock_power", 0) or
                balance_data.get("available_to_withdraw", 0) or
                balance_data.get("settled_cash", 0) or
                balance_data.get("total_cash", 0) or
                0.0
            )
            
            return float(cash)
        except Exception as e:
            logger.error(f"Error getting account cash: {e}")
            raise
