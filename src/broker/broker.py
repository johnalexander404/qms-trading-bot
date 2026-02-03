"""Abstract base class for broker implementations."""

from abc import ABC, abstractmethod
from typing import List
from .models import Allocation


class Broker(ABC):
    """Abstract base class for broker implementations."""
    
    @abstractmethod
    def get_current_allocation(self) -> List[Allocation]:
        """
        Get current portfolio allocation.
        
        Returns:
            List of Allocation objects representing current positions.
        """
        pass
    
    @abstractmethod
    def sell(self, symbol: str, quantity: float) -> bool:
        """
        Sell a stock.
        
        Args:
            symbol: Stock symbol to sell
            quantity: Number of shares to sell
            
        Returns:
            True if order was placed successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def buy(self, symbol: str, amount: float) -> bool:
        """
        Buy a stock with a specific dollar amount.
        
        Args:
            symbol: Stock symbol to buy
            amount: Dollar amount to spend
            
        Returns:
            True if order was placed successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def get_account_cash(self) -> float:
        """
        Get available cash in the account.
        
        Returns:
            Available cash amount
        """
        pass
    
    def get_trade_history(self, since_days: int = 7) -> List[dict]:
        """
        Get trade history from broker (optional - for reconciliation).

        Args:
            since_days: Number of days to look back for trades

        Returns:
            List of trade dictionaries with keys: symbol, action, quantity, price, total, timestamp, trade_id
            Returns empty list if not implemented by broker
        """
        # Default implementation - brokers can override
        return []

    def get_order_status(self, order_id: str) -> dict:
        """
        Get status of an order by ID.

        Args:
            order_id: Broker's order ID

        Returns:
            Dict with keys:
            - status: 'filled', 'pending', 'cancelled', 'rejected', 'expired', 'partial'
            - filled_qty: float (shares filled)
            - filled_avg_price: float (average fill price)

        Default implementation returns pending status.
        Brokers should override this method.
        """
        # Default implementation - brokers should override
        return {
            'status': 'pending',
            'filled_qty': 0.0,
            'filled_avg_price': 0.0,
        }
