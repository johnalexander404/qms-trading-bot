"""Tests for broker models."""

import pytest
from src.broker.models import Allocation, TradeSummary, PortfolioPerformance, MultiPortfolioSummary


class TestAllocation:
    """Tests for Allocation dataclass."""

    def test_allocation_creation(self):
        """Test creating an Allocation."""
        alloc = Allocation(
            symbol="AAPL",
            quantity=10.0,
            current_price=150.0,
            market_value=1500.0,
        )
        assert alloc.symbol == "AAPL"
        assert alloc.quantity == 10.0
        assert alloc.current_price == 150.0
        assert alloc.market_value == 1500.0

    def test_allocation_equality_same_symbol(self):
        """Test Allocation equality with same symbol."""
        alloc1 = Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0)
        alloc2 = Allocation(symbol="AAPL", quantity=5.0, current_price=160.0, market_value=800.0)
        assert alloc1 == alloc2

    def test_allocation_equality_different_case(self):
        """Test Allocation equality is case insensitive."""
        alloc1 = Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0)
        alloc2 = Allocation(symbol="aapl", quantity=5.0, current_price=160.0, market_value=800.0)
        assert alloc1 == alloc2

    def test_allocation_inequality_different_symbol(self):
        """Test Allocation inequality with different symbol."""
        alloc1 = Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0)
        alloc2 = Allocation(symbol="MSFT", quantity=10.0, current_price=150.0, market_value=1500.0)
        assert alloc1 != alloc2

    def test_allocation_inequality_with_non_allocation(self):
        """Test Allocation inequality with non-Allocation object."""
        alloc = Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0)
        assert alloc != "AAPL"
        assert alloc != {"symbol": "AAPL"}
        assert alloc != 123

    def test_allocation_hash(self):
        """Test Allocation hash is based on symbol."""
        alloc1 = Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0)
        alloc2 = Allocation(symbol="aapl", quantity=5.0, current_price=160.0, market_value=800.0)
        # Same symbol (case-insensitive) should have same hash
        assert hash(alloc1) == hash(alloc2)

    def test_allocation_can_be_used_in_set(self):
        """Test Allocations can be used in a set."""
        alloc1 = Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0)
        alloc2 = Allocation(symbol="AAPL", quantity=5.0, current_price=160.0, market_value=800.0)
        alloc3 = Allocation(symbol="MSFT", quantity=5.0, current_price=300.0, market_value=1500.0)

        allocation_set = {alloc1, alloc2, alloc3}
        # alloc1 and alloc2 have same symbol, so set should have 2 elements
        assert len(allocation_set) == 2


class TestTradeSummary:
    """Tests for TradeSummary dataclass."""

    def test_trade_summary_creation(self):
        """Test creating a TradeSummary."""
        summary = TradeSummary(
            buys=[{"symbol": "AAPL", "quantity": 10.0, "cost": 1500.0}],
            sells=[{"symbol": "MSFT", "quantity": 5.0, "proceeds": 1500.0}],
            total_cost=1500.0,
            total_proceeds=1500.0,
            final_allocations=[],
            portfolio_value=3000.0,
        )
        assert len(summary.buys) == 1
        assert len(summary.sells) == 1
        assert summary.total_cost == 1500.0
        assert summary.total_proceeds == 1500.0
        assert summary.portfolio_value == 3000.0

    def test_trade_summary_with_portfolio_name(self):
        """Test TradeSummary with custom portfolio name."""
        summary = TradeSummary(
            buys=[],
            sells=[],
            total_cost=0.0,
            total_proceeds=0.0,
            final_allocations=[],
            portfolio_value=10000.0,
            portfolio_name="SP500",
        )
        assert summary.portfolio_name == "SP500"

    def test_trade_summary_default_values(self):
        """Test TradeSummary default values."""
        summary = TradeSummary(
            buys=[],
            sells=[],
            total_cost=0.0,
            total_proceeds=0.0,
            final_allocations=[],
            portfolio_value=0.0,
        )
        assert summary.portfolio_name == "SP400"
        assert summary.initial_capital == 0.0
        assert summary.failed_trades == []
        assert summary.cash_balance == 0.0

    def test_trade_summary_with_failed_trades(self):
        """Test TradeSummary with failed trades."""
        summary = TradeSummary(
            buys=[],
            sells=[],
            total_cost=0.0,
            total_proceeds=0.0,
            final_allocations=[],
            portfolio_value=0.0,
            failed_trades=[
                {"symbol": "AAPL", "action": "BUY", "error": "Insufficient funds"}
            ],
        )
        assert len(summary.failed_trades) == 1
        assert summary.failed_trades[0]["symbol"] == "AAPL"


class TestPortfolioPerformance:
    """Tests for PortfolioPerformance dataclass."""

    def test_portfolio_performance_creation(self):
        """Test creating PortfolioPerformance."""
        perf = PortfolioPerformance(
            portfolio_name="SP400",
            initial_capital=10000.0,
            current_value=11000.0,
            total_return=1000.0,
            total_return_pct=10.0,
            total_cost=10000.0,
            total_proceeds=0.0,
            net_invested=10000.0,
            unrealized_pnl=1000.0,
            realized_pnl=0.0,
        )
        assert perf.portfolio_name == "SP400"
        assert perf.initial_capital == 10000.0
        assert perf.total_return_pct == 10.0


class TestMultiPortfolioSummary:
    """Tests for MultiPortfolioSummary dataclass."""

    def test_multi_portfolio_summary_creation(self):
        """Test creating MultiPortfolioSummary."""
        summary = MultiPortfolioSummary(
            portfolios={},
            performances={},
            total_initial_capital=20000.0,
            total_current_value=22000.0,
            total_net_invested=20000.0,
            overall_return=2000.0,
            overall_return_pct=10.0,
        )
        assert summary.total_initial_capital == 20000.0
        assert summary.overall_return_pct == 10.0
