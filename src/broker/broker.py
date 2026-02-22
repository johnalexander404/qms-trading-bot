"""Abstract base class for broker implementations."""

from abc import ABC, abstractmethod
from typing import List, Optional
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
    def sell(self, symbol: str, quantity: float, tag: Optional[str] = None) -> bool:
        """
        Sell a stock.
        
        Args:
            symbol: Stock symbol to sell
            quantity: Number of shares to sell
            tag: Optional portfolio tag to attach to the order
            
        Returns:
            True if order was placed successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def buy(self, symbol: str, amount: float, tag: Optional[str] = None) -> bool:
        """
        Buy a stock with a specific dollar amount.
        
        Args:
            symbol: Stock symbol to buy
            amount: Dollar amount to spend
            tag: Optional portfolio tag to attach to the order
            
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
