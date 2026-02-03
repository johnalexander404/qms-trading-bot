"""Cash balance management for portfolios."""

import logging

logger = logging.getLogger(__name__)


class CashManager:
    """Manages cash balance per portfolio."""

    def __init__(self, persistence_manager):
        """
        Initialize cash manager.

        Args:
            persistence_manager: PersistenceManager instance for database operations
        """
        self.persistence_manager = persistence_manager

    def initialize(self, portfolio_name: str, initial_capital: float) -> None:
        """
        Initialize cash balance for a portfolio if not exists.

        This is idempotent - calling multiple times won't overwrite existing balance.

        Args:
            portfolio_name: Portfolio name
            initial_capital: Initial capital amount
        """
        self.persistence_manager.initialize_portfolio_cash(portfolio_name, initial_capital)

    def get_balance(self, portfolio_name: str) -> float:
        """
        Get current cash balance for a portfolio.

        Args:
            portfolio_name: Portfolio name

        Returns:
            Current cash balance, or 0.0 if not initialized
        """
        return self.persistence_manager.get_portfolio_cash(portfolio_name)

    def debit(self, portfolio_name: str, amount: float) -> float:
        """
        Debit cash from portfolio (for buys).

        Args:
            portfolio_name: Portfolio name
            amount: Amount to debit

        Returns:
            New balance after debit
        """
        return self.persistence_manager.update_portfolio_cash(
            portfolio_name,
            amount,
            is_buy=True,
        )

    def credit(self, portfolio_name: str, amount: float) -> float:
        """
        Credit cash to portfolio (for sells).

        Args:
            portfolio_name: Portfolio name
            amount: Amount to credit

        Returns:
            New balance after credit
        """
        return self.persistence_manager.update_portfolio_cash(
            portfolio_name,
            amount,
            is_buy=False,
        )

    def can_afford(self, portfolio_name: str, amount: float) -> bool:
        """
        Check if portfolio has enough cash for a purchase.

        Args:
            portfolio_name: Portfolio name
            amount: Amount to check

        Returns:
            True if cash balance >= amount, False otherwise
        """
        balance = self.get_balance(portfolio_name)
        return balance >= amount

    def get_allocation_per_stock(
        self,
        portfolio_name: str,
        initial_capital: float,
        stockcount: int,
        num_missing_stocks: int,
    ) -> float:
        """
        Calculate allocation per stock for missing stock purchases.

        Uses the lesser of:
        - initial_capital / stockcount (target allocation)
        - available_cash / num_missing_stocks (what we can afford)

        Args:
            portfolio_name: Portfolio name
            initial_capital: Portfolio's initial capital
            stockcount: Number of stocks in portfolio
            num_missing_stocks: Number of missing stocks to buy

        Returns:
            Allocation amount per stock, or 0 if insufficient funds
        """
        if num_missing_stocks <= 0:
            return 0.0

        available_cash = self.get_balance(portfolio_name)
        if available_cash <= 0:
            logger.warning(f"[{portfolio_name}] No cash available for missing stock purchases")
            return 0.0

        # Target allocation per stock
        target_allocation = initial_capital / stockcount

        # Maximum we can afford per stock
        max_per_stock = available_cash / num_missing_stocks

        # Use the lesser amount
        allocation = min(target_allocation, max_per_stock)

        # Minimum viable trade check ($1)
        if allocation < 1.0:
            logger.warning(
                f"[{portfolio_name}] Allocation per stock (${allocation:.2f}) below minimum. "
                f"Available: ${available_cash:.2f}, Missing stocks: {num_missing_stocks}"
            )
            return 0.0

        return allocation
