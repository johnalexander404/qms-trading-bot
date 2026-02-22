"""Alpaca broker implementation."""

import logging
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import uuid4
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from ..broker import Broker
from ..models import Allocation

logger = logging.getLogger(__name__)


class AlpacaBroker(Broker):
    """Alpaca broker implementation."""
    
    def __init__(self, api_key: str, api_secret: str, base_url: str):
        """
        Initialize Alpaca broker.
        
        Args:
            api_key: Alpaca API key
            api_secret: Alpaca API secret
            base_url: Alpaca base URL (paper or live)
        """
        self.client = TradingClient(api_key=api_key, secret_key=api_secret, paper=base_url.startswith("https://paper"))
        logger.info(f"Initialized Alpaca broker (paper={base_url.startswith('https://paper')})")
    
    def get_current_allocation(self) -> List[Allocation]:
        """Get current portfolio allocation."""
        try:
            positions = self.client.get_all_positions()
            allocations = []
            
            for position in positions:
                allocations.append(Allocation(
                    symbol=position.symbol,
                    quantity=float(position.qty),
                    current_price=float(position.current_price),
                    market_value=float(position.market_value),
                ))
            
            logger.info(f"Retrieved {len(allocations)} positions from Alpaca")
            return allocations
        except Exception as e:
            logger.error(f"Error getting positions from Alpaca: {e}")
            raise
    
    def _make_client_order_id(self, tag: Optional[str]) -> Optional[str]:
        if tag:
            return f"{tag}-{uuid4().hex[:8]}"
        return None

    def sell(self, symbol: str, quantity: float, tag: Optional[str] = None) -> bool:
        """Sell a stock."""
        try:
            kwargs = dict(
                symbol=symbol,
                qty=quantity,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            client_order_id = self._make_client_order_id(tag)
            if client_order_id:
                kwargs["client_order_id"] = client_order_id
            order_data = MarketOrderRequest(**kwargs)
            order = self.client.submit_order(order_data=order_data)
            logger.info(f"Sold {quantity} shares of {symbol}. Order ID: {order.id}")
            return True
        except Exception as e:
            logger.error(f"Error selling {symbol}: {e}")
            return False
    
    def buy(self, symbol: str, amount: float, tag: Optional[str] = None) -> bool:
        """Buy a stock with a specific dollar amount."""
        try:
            asset = self.client.get_asset(symbol)
            if not asset.tradable:
                logger.error(f"Asset {symbol} is not tradable")
                return False
            
            kwargs = dict(
                symbol=symbol,
                notional=amount,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            )
            client_order_id = self._make_client_order_id(tag)
            if client_order_id:
                kwargs["client_order_id"] = client_order_id
            order_data = MarketOrderRequest(**kwargs)
            order = self.client.submit_order(order_data=order_data)
            logger.info(f"Bought ${amount} worth of {symbol}. Order ID: {order.id}")
            return True
        except Exception as e:
            logger.error(f"Error buying {symbol}: {e}")
            return False
    
    def get_account_cash(self) -> float:
        """Get available cash in the account."""
        try:
            account = self.client.get_account()
            return float(account.cash)
        except Exception as e:
            logger.error(f"Error getting account cash: {e}")
            raise
    
    def get_trade_history(self, since_days: int = 7) -> List[dict]:
        """Get trade history from Alpaca."""
        try:
            from alpaca.trading.enums import OrderStatus
            
            # Calculate start date
            start_date = datetime.now() - timedelta(days=since_days)
            
            # Create GetOrdersRequest filter according to Alpaca API documentation
            # get_orders() accepts a single 'filter' parameter of type GetOrdersRequest
            filter_request = GetOrdersRequest(
                status='all',  # Get all statuses (open, closed, all), we'll filter filled ones below
                limit=500,  # Maximum number of orders (defaults to 50, max is 500)
                after=start_date,  # Only orders submitted after this timestamp
            )
            
            # Get orders using the filter request
            orders = self.client.get_orders(filter=filter_request)
            
            trades = []
            for order in orders:
                # Only include filled orders
                if order.status != OrderStatus.FILLED:
                    continue
                
                # Skip if no filled quantity
                if not order.filled_qty or float(order.filled_qty) == 0:
                    continue
                
                # Filter by date if we got all orders
                order_date = order.filled_at if order.filled_at else order.submitted_at
                if order_date:
                    if isinstance(order_date, str):
                        try:
                            order_dt = datetime.fromisoformat(order_date.replace('Z', '+00:00'))
                        except:
                            continue
                    elif isinstance(order_date, datetime):
                        order_dt = order_date.replace(tzinfo=None) if order_date.tzinfo else order_date
                    else:
                        continue
                    
                    # Skip if order is before start_date
                    if order_dt < start_date:
                        continue
                
                # Determine action from order side
                action = "BUY" if order.side == OrderSide.BUY else "SELL"
                
                # Get fill price (use average fill price if available, otherwise submitted price)
                fill_price = float(order.filled_avg_price) if order.filled_avg_price else float(order.limit_price or order.submitted_price or 0)
                if fill_price == 0:
                    continue
                
                # Calculate total
                quantity = float(order.filled_qty)
                total = quantity * fill_price
                
                # Get timestamp (use filled_at if available, otherwise submitted_at)
                timestamp = order.filled_at if order.filled_at else order.submitted_at
                if timestamp:
                    # Convert to datetime if it's a string
                    if isinstance(timestamp, str):
                        try:
                            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        except:
                            timestamp = datetime.now()
                    elif isinstance(timestamp, datetime):
                        # Remove timezone if present
                        if timestamp.tzinfo:
                            timestamp = timestamp.replace(tzinfo=None)
                    else:
                        timestamp = datetime.now()
                else:
                    timestamp = datetime.now()
                
                trade_entry = {
                    'symbol': order.symbol,
                    'action': action,
                    'quantity': quantity,
                    'price': fill_price,
                    'total': total,
                    'timestamp': timestamp,
                    'trade_id': str(order.id),
                }
                if order.client_order_id:
                    trade_entry['client_order_id'] = order.client_order_id
                    parts = order.client_order_id.rsplit("-", 1)
                    if len(parts) == 2:
                        trade_entry['tag'] = parts[0]
                trades.append(trade_entry)
            
            logger.info(f"Retrieved {len(trades)} filled orders from Alpaca")
            return trades
        except Exception as e:
            logger.warning(f"Error getting trade history from Alpaca: {e}")
            return []
