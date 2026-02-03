"""Tests for CashManager."""

import pytest
from src.trading.cash_manager import CashManager


class TestCashManager:
    """Tests for CashManager class."""

    def test_initialize_creates_record(self, mock_persistence):
        """Initialize creates portfolio_cash doc with initial_capital."""
        manager = CashManager(mock_persistence)
        manager.initialize("SP400", 10000.0)

        assert "SP400" in mock_persistence.portfolio_cash
        record = mock_persistence.portfolio_cash["SP400"]
        assert record['initial_capital'] == 10000.0
        assert record['cash_balance'] == 10000.0

    def test_initialize_idempotent(self, mock_persistence):
        """Second initialize doesn't overwrite existing balance."""
        manager = CashManager(mock_persistence)
        manager.initialize("SP400", 10000.0)

        # Modify balance
        mock_persistence.portfolio_cash["SP400"]['cash_balance'] = 5000.0

        # Initialize again
        manager.initialize("SP400", 10000.0)

        # Balance should still be 5000, not reset to 10000
        assert mock_persistence.portfolio_cash["SP400"]['cash_balance'] == 5000.0

    def test_debit_reduces_balance(self, mock_persistence):
        """Debit subtracts from cash balance."""
        manager = CashManager(mock_persistence)
        manager.initialize("SP400", 10000.0)

        new_balance = manager.debit("SP400", 2000.0)

        assert new_balance == 8000.0
        assert manager.get_balance("SP400") == 8000.0

    def test_credit_increases_balance(self, mock_persistence):
        """Credit adds to cash balance."""
        manager = CashManager(mock_persistence)
        manager.initialize("SP400", 10000.0)

        new_balance = manager.credit("SP400", 1500.0)

        assert new_balance == 11500.0
        assert manager.get_balance("SP400") == 11500.0

    def test_can_afford_true_when_sufficient(self, mock_persistence):
        """can_afford returns True when balance >= amount."""
        manager = CashManager(mock_persistence)
        manager.initialize("SP400", 10000.0)

        assert manager.can_afford("SP400", 5000.0) is True
        assert manager.can_afford("SP400", 10000.0) is True

    def test_can_afford_false_when_insufficient(self, mock_persistence):
        """can_afford returns False when balance < amount."""
        manager = CashManager(mock_persistence)
        manager.initialize("SP400", 10000.0)

        assert manager.can_afford("SP400", 15000.0) is False

    def test_get_balance_returns_zero_when_not_initialized(self, mock_persistence):
        """get_balance returns 0.0 when portfolio not initialized."""
        manager = CashManager(mock_persistence)
        assert manager.get_balance("SP400") == 0.0

    def test_get_allocation_per_stock_basic(self, mock_persistence):
        """get_allocation_per_stock calculates correctly."""
        manager = CashManager(mock_persistence)
        manager.initialize("SP400", 10000.0)

        # 10000 / 5 = 2000 per stock (target)
        # 10000 / 2 = 5000 (max per stock)
        # min(2000, 5000) = 2000
        allocation = manager.get_allocation_per_stock("SP400", 10000.0, 5, 2)
        assert allocation == 2000.0

    def test_get_allocation_per_stock_limited_by_cash(self, mock_persistence):
        """get_allocation_per_stock is limited by available cash."""
        manager = CashManager(mock_persistence)
        manager.initialize("SP400", 10000.0)

        # Spend some cash
        manager.debit("SP400", 8000.0)  # Now have 2000

        # Target: 10000 / 5 = 2000 per stock
        # Max: 2000 / 2 = 1000 (limited by cash)
        allocation = manager.get_allocation_per_stock("SP400", 10000.0, 5, 2)
        assert allocation == 1000.0

    def test_get_allocation_per_stock_zero_when_insufficient(self, mock_persistence):
        """get_allocation_per_stock returns 0 when below $1 minimum."""
        manager = CashManager(mock_persistence)
        manager.initialize("SP400", 1.50)  # Very little cash

        # Can't afford $1 per stock for 2 stocks
        allocation = manager.get_allocation_per_stock("SP400", 10000.0, 5, 2)
        assert allocation == 0.0

    def test_get_allocation_per_stock_zero_when_no_cash(self, mock_persistence):
        """get_allocation_per_stock returns 0 when no cash available."""
        manager = CashManager(mock_persistence)
        manager.initialize("SP400", 0.0)

        allocation = manager.get_allocation_per_stock("SP400", 10000.0, 5, 2)
        assert allocation == 0.0

    def test_get_allocation_per_stock_zero_missing_stocks(self, mock_persistence):
        """get_allocation_per_stock returns 0 when no missing stocks."""
        manager = CashManager(mock_persistence)
        manager.initialize("SP400", 10000.0)

        allocation = manager.get_allocation_per_stock("SP400", 10000.0, 5, 0)
        assert allocation == 0.0

    def test_multiple_portfolios_independent(self, mock_persistence):
        """Cash balances are independent between portfolios."""
        manager = CashManager(mock_persistence)
        manager.initialize("SP400", 10000.0)
        manager.initialize("SP500", 20000.0)

        manager.debit("SP400", 5000.0)

        assert manager.get_balance("SP400") == 5000.0
        assert manager.get_balance("SP500") == 20000.0
