"""Robinhood broker implementation."""

import logging
from datetime import datetime, timedelta
from typing import List, Optional
import robin_stocks.robinhood as rh

from ..broker import Broker
from ..models import Allocation

logger = logging.getLogger(__name__)


class RobinhoodBroker(Broker):
    """Robinhood broker implementation."""
    
    def __init__(self, username: str, password: str, mfa_code: Optional[str] = None):
        """
        Initialize Robinhood broker.
        
        Args:
            username: Robinhood username/email
            password: Robinhood password
            mfa_code: Optional MFA code if 2FA is enabled
        """
        try:
            if mfa_code:
                rh.login(username=username, password=password, mfa_code=mfa_code)
            else:
                rh.login(username=username, password=password)
            logger.info("Successfully logged into Robinhood")
        except Exception as e:
            logger.error(f"Error logging into Robinhood: {e}")
            raise
    
    def get_current_allocation(self) -> List[Allocation]:
        """Get current portfolio allocation."""
        try:
            positions = rh.get_open_stock_positions()
            allocations = []
            
            for position in positions:
                symbol = position.get("symbol")
                quantity = float(position.get("quantity", 0))
                
                if quantity > 0 and symbol:
                    # Get current price
                    quote = rh.get_quotes(symbol)[0] if rh.get_quotes(symbol) else None
                    if quote:
                        current_price = float(quote.get("last_trade_price", 0))
                        market_value = quantity * current_price
                        
                        allocations.append(Allocation(
                            symbol=symbol,
                            quantity=quantity,
                            current_price=current_price,
                            market_value=market_value,
                        ))
            
            logger.info(f"Retrieved {len(allocations)} positions from Robinhood")
            return allocations
        except Exception as e:
            logger.error(f"Error getting positions from Robinhood: {e}")
            raise
    
    def sell(self, symbol: str, quantity: float, tag: Optional[str] = None) -> bool:
        """Sell a stock."""
        try:
            order = rh.order_sell_market(symbol=symbol, quantity=quantity)
            if order and order.get("id"):
                logger.info(f"Sold {quantity} shares of {symbol}. Order ID: {order.get('id')}")
                return True
            else:
                logger.error(f"Failed to sell {symbol}: {order}")
                return False
        except Exception as e:
            logger.error(f"Error selling {symbol}: {e}")
            return False
    
    def buy(self, symbol: str, amount: float, tag: Optional[str] = None) -> bool:
        """Buy a stock with a specific dollar amount."""
        try:
            # Get current price to calculate quantity
            quote = rh.get_quotes(symbol)
            if not quote:
                logger.error(f"Could not get quote for {symbol}")
                return False
            
            current_price = float(quote[0].get("last_trade_price", 0))
            if current_price == 0:
                logger.error(f"Invalid price for {symbol}")
                return False
            
            quantity = amount / current_price
            order = rh.order_buy_market(symbol=symbol, quantity=quantity)
            
            if order and order.get("id"):
                logger.info(f"Bought ${amount} worth of {symbol} ({quantity} shares). Order ID: {order.get('id')}")
                return True
            else:
                logger.error(f"Failed to buy {symbol}: {order}")
                return False
        except Exception as e:
            logger.error(f"Error buying {symbol}: {e}")
            return False
    
    def get_account_cash(self) -> float:
        """Get available cash in the account."""
        try:
            profile = rh.load_account_profile()
            cash = float(profile.get("cash", 0))
            return cash
        except Exception as e:
            logger.error(f"Error getting account cash: {e}")
            raise
    
    def get_trade_history(self, since_days: int = 7) -> List[dict]:
        """Get trade history from Robinhood."""
        try:
            # Get all stock orders
            orders = rh.get_all_stock_orders()
            
            if not orders:
                return []
            
            # Calculate cutoff date
            cutoff_date = datetime.now() - timedelta(days=since_days)
            
            trades = []
            for order in orders:
                # Only include filled orders
                state = order.get("state", "").upper()
                if state not in ["FILLED", "PARTIALLY_FILLED"]:
                    continue
                
                # Get order details
                symbol = order.get("symbol")
                if not symbol:
                    continue
                
                # Determine action from side
                side = order.get("side", "").upper()
                if side == "BUY":
                    action = "BUY"
                elif side == "SELL":
                    action = "SELL"
                else:
                    continue
                
                # Get filled quantity
                quantity = float(order.get("quantity", 0))
                if quantity == 0:
                    continue
                
                # Get average price (filled price)
                average_price = order.get("average_price")
                if not average_price:
                    # Try to get from executions
                    executions = order.get("executions", [])
                    if executions:
                        total_price = sum(float(e.get("price", 0)) * float(e.get("quantity", 0)) for e in executions)
                        total_qty = sum(float(e.get("quantity", 0)) for e in executions)
                        average_price = total_price / total_qty if total_qty > 0 else 0
                    else:
                        average_price = order.get("price", 0)
                
                fill_price = float(average_price) if average_price else 0.0
                if fill_price == 0:
                    continue
                
                # Calculate total
                total = quantity * fill_price
                
                # Get timestamp
                updated_at = order.get("updated_at") or order.get("created_at")
                if updated_at:
                    try:
                        # Parse ISO format timestamp
                        timestamp = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                        # Check if within date range
                        if timestamp.replace(tzinfo=None) < cutoff_date:
                            continue
                    except:
                        timestamp = datetime.now()
                else:
                    timestamp = datetime.now()
                
                trades.append({
                    'symbol': symbol,
                    'action': action,
                    'quantity': quantity,
                    'price': fill_price,
                    'total': total,
                    'timestamp': timestamp,
                    'trade_id': order.get("id"),
                })
            
            logger.info(f"Retrieved {len(trades)} filled orders from Robinhood")
            return trades
        except Exception as e:
            logger.warning(f"Error getting trade history from Robinhood: {e}")
            return []
