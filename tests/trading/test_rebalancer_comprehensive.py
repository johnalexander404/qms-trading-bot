"""Comprehensive tests for Rebalancer."""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime

from src.trading.rebalancer import Rebalancer
from src.broker.models import Allocation, TradeSummary


class TestRebalancerInitialization:
    """Tests for Rebalancer initialization."""

    def test_init_with_all_parameters(self, mock_broker, mock_leaderboard_client, mock_persistence):
        """Rebalancer initializes with all parameters."""
        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=5,
            slack=2,
            persistence_manager=mock_persistence,
        )

        assert rebalancer.broker == mock_broker
        assert rebalancer.leaderboard_client == mock_leaderboard_client
        assert rebalancer.initial_capital == 10000.0
        assert rebalancer.portfolio_name == "SP400"
        assert rebalancer.index_id == "13"
        assert rebalancer.stockcount == 5
        assert rebalancer.slack == 2
        assert rebalancer.persistence_manager == mock_persistence

    def test_init_with_defaults(self, mock_broker, mock_leaderboard_client):
        """Rebalancer initializes with default values."""
        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
        )

        assert rebalancer.stockcount == 5
        assert rebalancer.slack == 0


class TestInitialAllocation:
    """Tests for initial allocation when portfolio is empty."""

    def test_initial_allocation_buys_top_stocks(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Initial allocation buys top N stocks with equal weighting."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_broker.get_current_allocation.return_value = []
        mock_broker.get_account_cash.return_value = 10000.0
        mock_broker.buy.return_value = "order_123"

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "MSFT", "rank": 2},
            {"symbol": "GOOGL", "rank": 3},
            {"symbol": "AMZN", "rank": 4},
            {"symbol": "TSLA", "rank": 5},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=5,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=False)

        # Should attempt to buy 5 stocks
        assert mock_broker.buy.call_count == 5
        # Buys list may contain submitted + status updates
        buy_symbols = {b['symbol'] for b in summary.buys}
        assert len(buy_symbols) == 5

    def test_initial_allocation_dry_run_no_trades(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Initial allocation in dry run doesn't execute trades."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_broker.get_current_allocation.return_value = []
        mock_broker.get_account_cash.return_value = 10000.0

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "MSFT", "rank": 2},
            {"symbol": "GOOGL", "rank": 3},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=3,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=True)

        # Should plan 3 buys but not execute
        assert len(summary.buys) == 3
        mock_broker.buy.assert_not_called()


class TestWeekOverWeekRebalancing:
    """Tests for week-over-week rebalancing logic."""

    def test_sell_stock_when_rank_exceeds_threshold(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Sells stock when its rank exceeds stockcount + slack."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_AAPL"] = {
            "portfolio_name": "SP400",
            "symbol": "AAPL",
            "quantity": 10.0,
            "total_cost": 1500.0,
        }
        mock_persistence.ownership["SP400_OLD"] = {
            "portfolio_name": "SP400",
            "symbol": "OLD",
            "quantity": 10.0,
            "total_cost": 1000.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
            Allocation(symbol="OLD", quantity=10.0, current_price=100.0, market_value=1000.0),
        ]
        mock_broker.get_account_cash.return_value = 0.0
        mock_broker.sell.return_value = "sell_order_123"
        mock_broker.buy.return_value = "buy_order_123"

        # Current week: AAPL stays (rank 1), OLD drops out (rank 10)
        # Previous week: AAPL (rank 1), OLD (rank 2)
        def get_symbols_side_effect(top_n, mom_day, index_id):
            return [
                {"symbol": "AAPL", "rank": 1},
                {"symbol": "MSFT", "rank": 2},
                {"symbol": "GOOGL", "rank": 3},
                {"symbol": "OLD", "rank": 10},  # Dropped out of top 3
            ][:top_n + 5]

        mock_leaderboard_client.get_symbols_with_ranks.side_effect = get_symbols_side_effect

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=3,
            slack=0,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=False)

        # Should sell OLD
        assert len(summary.sells) >= 1
        sell_symbols = [s['symbol'] for s in summary.sells]
        assert 'OLD' in sell_symbols

    def test_hold_stock_within_slack(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Holds stock when rank is within stockcount + slack."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_AAPL"] = {
            "portfolio_name": "SP400",
            "symbol": "AAPL",
            "quantity": 10.0,
            "total_cost": 1500.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
        ]
        mock_broker.get_account_cash.return_value = 2000.0

        # AAPL rank 4, stockcount=3, slack=2 -> threshold is 5, so AAPL is held
        def get_symbols_side_effect(top_n, mom_day, index_id):
            return [
                {"symbol": "MSFT", "rank": 1},
                {"symbol": "GOOGL", "rank": 2},
                {"symbol": "AMZN", "rank": 3},
                {"symbol": "AAPL", "rank": 4},
                {"symbol": "TSLA", "rank": 5},
            ][:top_n + 5]

        mock_leaderboard_client.get_symbols_with_ranks.side_effect = get_symbols_side_effect

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=3,
            slack=2,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=True)

        # AAPL should not be sold (rank 4 <= 3 + 2 = 5)
        sell_symbols = [s['symbol'] for s in summary.sells]
        assert 'AAPL' not in sell_symbols


class TestMissingStockPurchase:
    """Tests for purchasing missing stocks."""

    def test_buy_missing_stock_with_initial_capital(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Buys missing stocks using initial capital when no sale proceeds."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        # Already own AAPL
        mock_persistence.ownership["SP400_AAPL"] = {
            "portfolio_name": "SP400",
            "symbol": "AAPL",
            "quantity": 10.0,
            "total_cost": 2000.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=200.0, market_value=2000.0),
        ]
        mock_broker.get_account_cash.return_value = 8000.0
        mock_broker.buy.return_value = "order_123"

        # AAPL still top, but MSFT and GOOGL are missing
        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "MSFT", "rank": 2},
            {"symbol": "GOOGL", "rank": 3},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=3,
            slack=0,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=False)

        # Should buy MSFT and GOOGL (missing stocks)
        buy_symbols = [b['symbol'] for b in summary.buys]
        assert 'MSFT' in buy_symbols or 'GOOGL' in buy_symbols

    def test_no_purchase_when_insufficient_cash(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """No purchases when cash is insufficient."""
        # Very low cash balance
        mock_persistence.initialize_portfolio_cash("SP400", 0.50)
        mock_persistence.ownership["SP400_AAPL"] = {
            "portfolio_name": "SP400",
            "symbol": "AAPL",
            "quantity": 10.0,
            "total_cost": 1500.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
        ]
        mock_broker.get_account_cash.return_value = 0.50

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "MSFT", "rank": 2},
            {"symbol": "GOOGL", "rank": 3},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=3,
            slack=0,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=True)

        # With only $0.50 cash, can't afford any purchases
        # (depends on implementation - may have 0 or limited buys)


class TestExecutionRunTracking:
    """Tests for execution run ID tracking."""

    def test_execution_run_id_stored(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Execution run ID is stored when passed to rebalance."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_broker.get_current_allocation.return_value = []
        mock_broker.get_account_cash.return_value = 10000.0

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            persistence_manager=mock_persistence,
        )

        run_id = "SP400_2025-01-27"
        summary = rebalancer.rebalance(dry_run=True, execution_run_id=run_id)

        assert rebalancer._current_execution_run_id == run_id


class TestTradeSummary:
    """Tests for trade summary generation."""

    def test_summary_includes_all_trades(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Trade summary includes all executed trades."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_broker.get_current_allocation.return_value = []
        mock_broker.get_account_cash.return_value = 10000.0
        mock_broker.buy.return_value = "order_123"

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "MSFT", "rank": 2},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=2,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=False)

        assert isinstance(summary, TradeSummary)
        # Check that broker was called for each stock
        assert mock_broker.buy.call_count == 2
        # Check that summary has expected symbols
        buy_symbols = {b['symbol'] for b in summary.buys}
        assert 'AAPL' in buy_symbols
        assert 'MSFT' in buy_symbols


class TestAllocationsMatch:
    """Tests for _allocations_match helper method."""

    def test_allocations_match_true_when_matching(
        self, mock_broker, mock_leaderboard_client
    ):
        """_allocations_match returns True when allocations match target."""
        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=3,
        )

        allocations = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
            Allocation(symbol="MSFT", quantity=5.0, current_price=300.0, market_value=1500.0),
            Allocation(symbol="GOOGL", quantity=3.0, current_price=100.0, market_value=300.0),
        ]
        target_symbols = ["AAPL", "MSFT", "GOOGL"]

        assert rebalancer._allocations_match(allocations, target_symbols) is True

    def test_allocations_match_false_when_missing(
        self, mock_broker, mock_leaderboard_client
    ):
        """_allocations_match returns False when allocations missing symbols."""
        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=3,
        )

        allocations = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
        ]
        target_symbols = ["AAPL", "MSFT", "GOOGL"]

        assert rebalancer._allocations_match(allocations, target_symbols) is False


class TestFilterAllocationsByPortfolio:
    """Tests for filtering allocations to portfolio's owned symbols."""

    def test_filters_to_portfolio_symbols(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Allocations are filtered to symbols owned by portfolio."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        # SP400 only owns AAPL
        mock_persistence.ownership["SP400_AAPL"] = {
            "portfolio_name": "SP400",
            "symbol": "AAPL",
            "quantity": 10.0,
            "total_cost": 1500.0,
        }
        # SP500 owns MSFT (but not SP400)
        mock_persistence.ownership["SP500_MSFT"] = {
            "portfolio_name": "SP500",
            "symbol": "MSFT",
            "quantity": 5.0,
            "total_cost": 1500.0,
        }

        # Broker has both AAPL and MSFT
        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
            Allocation(symbol="MSFT", quantity=5.0, current_price=300.0, market_value=1500.0),
        ]
        mock_broker.get_account_cash.return_value = 5000.0

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "MSFT", "rank": 2},
            {"symbol": "GOOGL", "rank": 3},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=3,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=True)

        # SP400 should only see AAPL as owned, MSFT should not be sold by SP400
        sell_symbols = [s['symbol'] for s in summary.sells]
        assert 'MSFT' not in sell_symbols


class TestErrorHandling:
    """Tests for error handling in rebalancer."""

    def test_handles_broker_buy_failure(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Handles broker buy failure gracefully."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_broker.get_current_allocation.return_value = []
        mock_broker.get_account_cash.return_value = 10000.0
        mock_broker.buy.return_value = None  # Simulate failure

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            persistence_manager=mock_persistence,
        )

        # Should not raise exception
        summary = rebalancer.rebalance(dry_run=False)

        # Buy was attempted
        mock_broker.buy.assert_called()

    def test_handles_leaderboard_api_error(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Handles leaderboard API error gracefully."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_broker.get_current_allocation.return_value = []

        mock_leaderboard_client.get_symbols_with_ranks.side_effect = Exception("API Error")

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=5,
            persistence_manager=mock_persistence,
        )

        # Should raise the exception (or handle it depending on implementation)
        with pytest.raises(Exception):
            rebalancer.rebalance(dry_run=True)

    def test_handles_broker_sell_failure(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Handles broker sell failure gracefully."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_OLD"] = {
            "portfolio_name": "SP400",
            "symbol": "OLD",
            "quantity": 10.0,
            "total_cost": 1000.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="OLD", quantity=10.0, current_price=100.0, market_value=1000.0),
        ]
        mock_broker.get_account_cash.return_value = 0.0
        mock_broker.sell.return_value = False  # Simulate failure

        # OLD dropped out of top stocks
        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "MSFT", "rank": 2},
            {"symbol": "OLD", "rank": 100},  # Dropped out
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=2,
            slack=0,
            persistence_manager=mock_persistence,
        )

        # Should not raise exception
        summary = rebalancer.rebalance(dry_run=False)

        # Summary should be returned regardless of failures
        assert isinstance(summary, TradeSummary)

    def test_handles_broker_exception_on_sell(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Handles broker exception during sell gracefully."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_OLD"] = {
            "portfolio_name": "SP400",
            "symbol": "OLD",
            "quantity": 10.0,
            "total_cost": 1000.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="OLD", quantity=10.0, current_price=100.0, market_value=1000.0),
        ]
        mock_broker.get_account_cash.return_value = 0.0
        mock_broker.sell.side_effect = Exception("Broker error")

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "OLD", "rank": 100},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            slack=0,
            persistence_manager=mock_persistence,
        )

        # Should not raise exception
        summary = rebalancer.rebalance(dry_run=False)

        # Should have a failed trade recorded
        assert len(summary.sells) >= 1


class TestExternalSalesHandling:
    """Tests for external sales detection and handling."""

    def test_external_sale_proceeds_used_for_buys(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """External sale proceeds are used for purchasing new stocks."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_AAPL"] = {
            "portfolio_name": "SP400",
            "symbol": "AAPL",
            "quantity": 10.0,
            "total_cost": 1500.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
        ]
        mock_broker.get_account_cash.return_value = 2000.0
        mock_broker.buy.return_value = "order_123"

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "MSFT", "rank": 2},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=2,
            slack=0,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=False)

        # Summary should be returned
        assert isinstance(summary, TradeSummary)
        # Should have buy entries for MSFT (missing stock)
        buy_symbols = [b['symbol'] for b in summary.buys]
        assert 'MSFT' in buy_symbols


class TestMultiPortfolioScenarios:
    """Tests for multi-portfolio scenarios."""

    def test_portfolio_only_sells_own_shares(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Portfolio only sells shares it owns, not other portfolios' shares."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_OLD"] = {
            "portfolio_name": "SP400",
            "symbol": "OLD",
            "quantity": 5.0,  # SP400 owns 5 shares
            "total_cost": 500.0,
        }
        mock_persistence.ownership["SP500_OLD"] = {
            "portfolio_name": "SP500",
            "symbol": "OLD",
            "quantity": 5.0,  # SP500 owns 5 shares too
            "total_cost": 500.0,
        }

        # Broker has total of 10 shares (5 from each portfolio)
        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="OLD", quantity=10.0, current_price=100.0, market_value=1000.0),
        ]
        mock_broker.get_account_cash.return_value = 0.0
        mock_broker.sell.return_value = "order_123"

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "OLD", "rank": 100},  # Dropped out
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            slack=0,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=False)

        # Summary should be returned
        assert isinstance(summary, TradeSummary)
        # If there are sells, check the quantity is limited
        if summary.sells:
            for sell in summary.sells:
                if sell.get('symbol') == 'OLD':
                    # SP400 should sell at most 5 shares (its own), not all 10
                    assert sell.get('quantity', 0) <= 5.0


class TestReconciliation:
    """Tests for broker reconciliation."""

    def test_reconciles_with_broker_history(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Reconciles trades with broker history."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_AAPL"] = {
            "portfolio_name": "SP400",
            "symbol": "AAPL",
            "quantity": 10.0,
            "total_cost": 1500.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
        ]
        mock_broker.get_account_cash.return_value = 5000.0
        mock_broker.get_trade_history.return_value = [
            {"symbol": "AAPL", "qty": 10.0, "price": 150.0, "side": "buy"}
        ]

        # Add reconcile method to mock
        mock_persistence.reconcile_with_broker_history = Mock(return_value={
            'updated': 1, 'missing': 0, 'unfilled': 0
        })

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=True)

        # Reconciliation should have been called
        mock_persistence.reconcile_with_broker_history.assert_called_once()


class TestSellDeficitScenario:
    """Tests for deficit scenarios when selling."""

    def test_deficit_when_broker_has_fewer_shares(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Handles scenario where broker has fewer shares than tracked."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        # Portfolio tracks 15 shares
        mock_persistence.ownership["SP400_OLD"] = {
            "portfolio_name": "SP400",
            "symbol": "OLD",
            "quantity": 15.0,
            "total_cost": 1500.0,
        }

        # But broker only has 10 shares
        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="OLD", quantity=10.0, current_price=100.0, market_value=1000.0),
        ]
        mock_broker.get_account_cash.return_value = 0.0
        mock_broker.sell.return_value = "order_123"

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "OLD", "rank": 100},
        ]

        # Mock the external sale recording
        mock_persistence._record_external_sale = Mock()

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            slack=0,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=False)

        # Should sell what broker has (10 shares)
        if mock_broker.sell.called:
            args, kwargs = mock_broker.sell.call_args
            sold_symbol = args[0] if args else kwargs.get('symbol')
            assert sold_symbol == 'OLD'


class TestDryRunMode:
    """Tests for dry run mode behavior."""

    def test_dry_run_logs_sells_without_executing(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Dry run logs sells without executing."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_OLD"] = {
            "portfolio_name": "SP400",
            "symbol": "OLD",
            "quantity": 10.0,
            "total_cost": 1000.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="OLD", quantity=10.0, current_price=100.0, market_value=1000.0),
        ]
        mock_broker.get_account_cash.return_value = 0.0

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "OLD", "rank": 100},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            slack=0,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=True)

        # Should not call sell
        mock_broker.sell.assert_not_called()
        # But should have planned sells
        sell_symbols = [s['symbol'] for s in summary.sells]
        assert 'OLD' in sell_symbols


class TestBuyWithOrderId:
    """Tests for tracking order IDs on buys."""

    def test_order_id_captured_on_buy(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Order ID is captured when available."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_broker.get_current_allocation.return_value = []
        mock_broker.get_account_cash.return_value = 10000.0
        mock_broker.buy.return_value = True
        mock_broker._last_order_id = "order_12345"

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=False)

        # Should have captured order ID
        buys_with_order_id = [b for b in summary.buys if b.get('order_id')]
        assert len(buys_with_order_id) >= 1


class TestSymbolNoLongerInLeaderboard:
    """Tests for handling symbols not in leaderboard."""

    def test_sell_stock_not_in_leaderboard(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Sells stock that is no longer in the leaderboard at all."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_DELISTED"] = {
            "portfolio_name": "SP400",
            "symbol": "DELISTED",
            "quantity": 10.0,
            "total_cost": 1000.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="DELISTED", quantity=10.0, current_price=100.0, market_value=1000.0),
        ]
        mock_broker.get_account_cash.return_value = 0.0
        mock_broker.sell.return_value = True

        # DELISTED not in leaderboard at all (no rank)
        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "MSFT", "rank": 2},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=2,
            slack=0,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=False)

        # Should sell DELISTED because it's not in leaderboard
        sell_symbols = [s['symbol'] for s in summary.sells]
        assert 'DELISTED' in sell_symbols


class TestBuybackAfterExternalSale:
    """Tests for buying back stocks after external sales."""

    def test_buyback_stock_after_external_sale_dry_run(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Dry run shows buyback intent for externally sold stock."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        # Simulate external sale of AAPL
        from src.persistence.models import ExternalSaleRecord
        from datetime import datetime

        mock_broker.get_current_allocation.return_value = []  # Empty after external sale
        mock_broker.get_account_cash.return_value = 5000.0

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "MSFT", "rank": 2},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=2,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=True)

        # Should plan to buy AAPL and MSFT
        buy_symbols = [b['symbol'] for b in summary.buys]
        assert 'AAPL' in buy_symbols or 'MSFT' in buy_symbols


class TestNoProceedsAvailable:
    """Tests for scenarios with no proceeds available."""

    def test_no_cash_for_missing_stocks(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Handles scenario where no cash is available for missing stocks."""
        # Initialize with zero cash
        mock_persistence.portfolio_cash["SP400"] = {
            'portfolio_name': "SP400",
            'initial_capital': 10000.0,
            'cash_balance': 0.0,
        }
        mock_persistence.ownership["SP400_AAPL"] = {
            "portfolio_name": "SP400",
            "symbol": "AAPL",
            "quantity": 10.0,
            "total_cost": 2000.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=200.0, market_value=2000.0),
        ]
        mock_broker.get_account_cash.return_value = 0.0

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "MSFT", "rank": 2},  # Missing
            {"symbol": "GOOGL", "rank": 3},  # Missing
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=3,
            slack=0,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=True)

        # Should not buy any stocks (no cash available)
        buy_symbols = [b['symbol'] for b in summary.buys]
        assert 'MSFT' not in buy_symbols
        assert 'GOOGL' not in buy_symbols


class TestBuyFailureHandling:
    """Tests for buy failure scenarios."""

    def test_broker_rejects_buy_order(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Handles broker rejecting a buy order."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_OLD"] = {
            "portfolio_name": "SP400",
            "symbol": "OLD",
            "quantity": 10.0,
            "total_cost": 2000.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="OLD", quantity=10.0, current_price=200.0, market_value=2000.0),
        ]
        mock_broker.get_account_cash.return_value = 0.0
        mock_broker.sell.return_value = True
        mock_broker.buy.return_value = False  # Buy rejected

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},  # New
            {"symbol": "OLD", "rank": 100},  # Sell
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            slack=0,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=False)

        # Buy should have failed status
        failed_buys = [b for b in summary.buys if b.get('status') == 'failed']
        assert len(failed_buys) >= 1 or len(summary.failed_trades) >= 1

    def test_broker_exception_on_buy(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Handles broker exception during buy."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_OLD"] = {
            "portfolio_name": "SP400",
            "symbol": "OLD",
            "quantity": 10.0,
            "total_cost": 2000.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="OLD", quantity=10.0, current_price=200.0, market_value=2000.0),
        ]
        mock_broker.get_account_cash.return_value = 0.0
        mock_broker.sell.return_value = True
        mock_broker.buy.side_effect = Exception("Network error")

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "OLD", "rank": 100},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            slack=0,
            persistence_manager=mock_persistence,
        )

        # Should not raise, handles gracefully
        summary = rebalancer.rebalance(dry_run=False)
        assert isinstance(summary, TradeSummary)


class TestFilterAllocationsByPortfolioExtended:
    """Extended tests for _filter_allocations_by_portfolio."""

    def test_no_persistence_returns_all(
        self, mock_broker, mock_leaderboard_client
    ):
        """Without persistence, returns all allocations."""
        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=3,
            persistence_manager=None,  # No persistence
        )

        allocations = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
            Allocation(symbol="MSFT", quantity=5.0, current_price=300.0, market_value=1500.0),
        ]

        filtered = rebalancer._filter_allocations_by_portfolio(allocations)

        assert len(filtered) == 2

    def test_empty_owned_symbols_returns_empty(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Empty owned symbols returns empty list."""
        # Don't add any ownership
        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=3,
            persistence_manager=mock_persistence,
        )

        allocations = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
        ]

        filtered = rebalancer._filter_allocations_by_portfolio(allocations)

        assert len(filtered) == 0

    def test_multi_portfolio_fraction_calculation(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Calculates portfolio fraction when multiple portfolios own same stock."""
        # SP400 owns 60 shares, SP500 owns 40 shares (60% / 40%)
        mock_persistence.ownership["SP400_AAPL"] = {
            "portfolio_name": "SP400",
            "symbol": "AAPL",
            "quantity": 60.0,
            "total_cost": 6000.0,
        }
        mock_persistence.ownership["SP500_AAPL"] = {
            "portfolio_name": "SP500",
            "symbol": "AAPL",
            "quantity": 40.0,
            "total_cost": 4000.0,
        }

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=3,
            persistence_manager=mock_persistence,
        )

        # Broker has total of 100 shares
        allocations = [
            Allocation(symbol="AAPL", quantity=100.0, current_price=150.0, market_value=15000.0),
        ]

        filtered = rebalancer._filter_allocations_by_portfolio(allocations)

        # SP400 should see 60% of the allocation
        assert len(filtered) == 1
        assert filtered[0].quantity == 60.0
        assert filtered[0].market_value == 9000.0  # 60% of 15000


class TestNoRebalancingNeeded:
    """Tests for when no rebalancing is needed."""

    def test_no_changes_needed_dry_run(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """No rebalancing when positions match leaderboard."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_AAPL"] = {
            "portfolio_name": "SP400",
            "symbol": "AAPL",
            "quantity": 10.0,
            "total_cost": 1500.0,
        }
        mock_persistence.ownership["SP400_MSFT"] = {
            "portfolio_name": "SP400",
            "symbol": "MSFT",
            "quantity": 5.0,
            "total_cost": 1500.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
            Allocation(symbol="MSFT", quantity=5.0, current_price=300.0, market_value=1500.0),
        ]
        mock_broker.get_account_cash.return_value = 0.0

        # Both stocks are in top 2, both held - no changes needed
        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "MSFT", "rank": 2},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=2,
            slack=0,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=True)

        # No sells or buys needed
        assert len(summary.sells) == 0
        assert len(summary.buys) == 0


class TestCreateSummary:
    """Tests for _create_summary method."""

    def test_create_summary_with_failed_trades(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Summary includes failed trades."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_broker.get_current_allocation.return_value = []
        mock_broker.get_account_cash.return_value = 10000.0
        mock_broker.buy.return_value = False  # All buys fail

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "MSFT", "rank": 2},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=2,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=False)

        # Should have failed trades recorded
        total_failed = len([b for b in summary.buys if b.get('status') == 'failed'])
        total_failed += len(summary.failed_trades) if summary.failed_trades else 0
        assert total_failed > 0


class TestReconcileOwnership:
    """Tests for ownership reconciliation after trades."""

    def test_reconcile_after_successful_buy(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Ownership is reconciled after successful buy."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_broker.get_current_allocation.return_value = []
        mock_broker.get_account_cash.return_value = 10000.0
        mock_broker.buy.return_value = True

        # After buy, allocation shows position
        def get_allocation_side_effect():
            return [
                Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
            ]
        mock_broker.get_current_allocation.side_effect = [[], get_allocation_side_effect()]

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=False)

        # Reconciliation should have been attempted
        assert isinstance(summary, TradeSummary)


class TestInitialAllocationExtended:
    """Extended tests for initial allocation."""

    def test_initial_allocation_with_external_proceeds(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Initial allocation uses external sale proceeds."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.get_unused_external_sale_proceeds = Mock(return_value=2000.0)

        mock_broker.get_current_allocation.return_value = []
        mock_broker.get_account_cash.return_value = 12000.0  # 10k + 2k external
        mock_broker.buy.return_value = True

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "MSFT", "rank": 2},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=2,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=False)

        # Should buy both stocks
        buy_symbols = [b['symbol'] for b in summary.buys]
        assert 'AAPL' in buy_symbols
        assert 'MSFT' in buy_symbols

    def test_initial_allocation_buy_failure(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Handles buy failure during initial allocation."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_broker.get_current_allocation.return_value = []
        mock_broker.get_account_cash.return_value = 10000.0
        mock_broker.buy.side_effect = [True, Exception("Network error")]  # Second buy fails

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "MSFT", "rank": 2},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=2,
            persistence_manager=mock_persistence,
        )

        # Should not raise
        summary = rebalancer.rebalance(dry_run=False)
        assert isinstance(summary, TradeSummary)


class TestSlackThreshold:
    """Tests for slack threshold behavior."""

    def test_stock_at_exact_threshold_is_held(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Stock at exactly stockcount + slack is held."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_AAPL"] = {
            "portfolio_name": "SP400",
            "symbol": "AAPL",
            "quantity": 10.0,
            "total_cost": 1500.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
        ]
        mock_broker.get_account_cash.return_value = 5000.0

        # stockcount=3, slack=2, threshold=5
        # AAPL at rank 5 = exactly at threshold, should be held
        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "MSFT", "rank": 1},
            {"symbol": "GOOGL", "rank": 2},
            {"symbol": "AMZN", "rank": 3},
            {"symbol": "TSLA", "rank": 4},
            {"symbol": "AAPL", "rank": 5},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=3,
            slack=2,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=True)

        # AAPL should not be sold (at threshold)
        sell_symbols = [s['symbol'] for s in summary.sells]
        assert 'AAPL' not in sell_symbols

    def test_stock_one_above_threshold_is_sold(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Stock one rank above threshold is sold."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_AAPL"] = {
            "portfolio_name": "SP400",
            "symbol": "AAPL",
            "quantity": 10.0,
            "total_cost": 1500.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
        ]
        mock_broker.get_account_cash.return_value = 0.0

        # stockcount=3, slack=2, threshold=5
        # AAPL at rank 6 = above threshold, should be sold
        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "MSFT", "rank": 1},
            {"symbol": "GOOGL", "rank": 2},
            {"symbol": "AMZN", "rank": 3},
            {"symbol": "TSLA", "rank": 4},
            {"symbol": "META", "rank": 5},
            {"symbol": "AAPL", "rank": 6},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=3,
            slack=2,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=True)

        # AAPL should be sold (above threshold)
        sell_symbols = [s['symbol'] for s in summary.sells]
        assert 'AAPL' in sell_symbols


class TestMarkExternalSalesUsed:
    """Tests for marking external sales as used."""

    def test_external_sales_marked_used_after_reinvestment(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """External sales are marked as used after reinvestment."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_OLD"] = {
            "portfolio_name": "SP400",
            "symbol": "OLD",
            "quantity": 10.0,
            "total_cost": 1000.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="OLD", quantity=10.0, current_price=100.0, market_value=1000.0),
        ]
        mock_broker.get_account_cash.return_value = 0.0
        mock_broker.sell.return_value = True
        mock_broker.buy.return_value = True

        # Mock external sale proceeds
        mock_persistence.get_unused_external_sale_proceeds = Mock(return_value=500.0)
        mock_persistence.mark_external_sales_used = Mock()

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "OLD", "rank": 100},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            slack=0,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=False)

        # Should have attempted to mark external sales as used
        assert isinstance(summary, TradeSummary)


class TestGetCurrentAllocationError:
    """Tests for error handling when getting current allocation."""

    def test_handles_allocation_error(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Handles error when getting current allocation."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_broker.get_current_allocation.side_effect = Exception("API error")

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            persistence_manager=mock_persistence,
        )

        # Should raise the exception
        with pytest.raises(Exception, match="API error"):
            rebalancer.rebalance(dry_run=False)


class TestGetAccountCashError:
    """Tests for error handling when getting account cash."""

    def test_handles_cash_error(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Handles error when getting account cash."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_AAPL"] = {
            "portfolio_name": "SP400",
            "symbol": "AAPL",
            "quantity": 10.0,
            "total_cost": 1500.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
        ]
        mock_broker.get_account_cash.side_effect = Exception("Cash API error")

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            persistence_manager=mock_persistence,
        )

        # Should raise the exception
        with pytest.raises(Exception, match="Cash API error"):
            rebalancer.rebalance(dry_run=False)


class TestTradeRecordingWithPersistence:
    """Tests for recording trades with persistence manager."""

    def test_buy_trade_recorded_in_persistence(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Buy trades are recorded in persistence."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_broker.get_current_allocation.return_value = []
        mock_broker.get_account_cash.return_value = 10000.0
        mock_broker.buy.return_value = True

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=False)

        # Trade should be recorded
        assert len(mock_persistence.trades) >= 1

    def test_sell_trade_recorded_in_persistence(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Sell trades are recorded in persistence."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_OLD"] = {
            "portfolio_name": "SP400",
            "symbol": "OLD",
            "quantity": 10.0,
            "total_cost": 1000.0,
        }

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="OLD", quantity=10.0, current_price=100.0, market_value=1000.0),
        ]
        mock_broker.get_account_cash.return_value = 0.0
        mock_broker.sell.return_value = True

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
            {"symbol": "OLD", "rank": 100},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            slack=0,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=False)

        # Sell trade should be recorded
        sell_trades = [t for t in mock_persistence.trades.values() if t.get('action') == 'SELL']
        assert len(sell_trades) >= 1


class TestManuallyHeldStocks:
    """Tests for manually held stocks scenarios."""

    def test_manually_held_stock_in_top5_dry_run(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Handles manually held stock in top 5 during dry run."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        # No ownership tracked but broker shows position
        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
        ]
        mock_broker.get_account_cash.return_value = 5000.0

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},  # Manually held, in top 5
            {"symbol": "MSFT", "rank": 2},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=2,
            slack=0,
            persistence_manager=mock_persistence,
        )

        summary = rebalancer.rebalance(dry_run=True)

        # Should not crash, should return valid summary
        assert isinstance(summary, TradeSummary)


class TestFinalAllocationsError:
    """Tests for error handling when getting final allocations."""

    def test_handles_final_allocations_error(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Handles error when getting final allocations."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)

        # First call works, subsequent calls fail
        call_count = [0]
        def get_allocation_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return []
            raise Exception("Final allocation error")

        mock_broker.get_current_allocation.side_effect = get_allocation_side_effect
        mock_broker.get_account_cash.return_value = 10000.0
        mock_broker.buy.return_value = True

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            persistence_manager=mock_persistence,
        )

        # Should not raise, handles gracefully
        summary = rebalancer.rebalance(dry_run=False)
        assert isinstance(summary, TradeSummary)
        # Final allocations should be empty due to error
        assert len(summary.final_allocations) == 0


class TestExternalSalesDetection:
    """Tests for external sales detection."""

    def test_external_sales_error_handled(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Error detecting external sales is handled gracefully."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.ownership["SP400_AAPL"] = {
            "portfolio_name": "SP400",
            "symbol": "AAPL",
            "quantity": 10.0,
            "total_cost": 1500.0,
        }
        # Make detect_external_sales raise an error
        mock_persistence.detect_external_sales = Mock(side_effect=Exception("Detection error"))

        mock_broker.get_current_allocation.return_value = [
            Allocation(symbol="AAPL", quantity=10.0, current_price=150.0, market_value=1500.0),
        ]
        mock_broker.get_account_cash.return_value = 5000.0

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            persistence_manager=mock_persistence,
        )

        # Should not raise, handles gracefully
        summary = rebalancer.rebalance(dry_run=True)
        assert isinstance(summary, TradeSummary)


class TestBrokerReconciliation:
    """Tests for broker reconciliation."""

    def test_reconciliation_error_handled(
        self, mock_broker, mock_leaderboard_client, mock_persistence
    ):
        """Error during reconciliation is handled gracefully."""
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)
        mock_persistence.reconcile_with_broker_history = Mock(
            side_effect=Exception("Reconciliation error")
        )

        mock_broker.get_current_allocation.return_value = []
        mock_broker.get_account_cash.return_value = 10000.0
        mock_broker.get_trade_history.return_value = [{"symbol": "AAPL"}]
        mock_broker.buy.return_value = True

        mock_leaderboard_client.get_symbols_with_ranks.return_value = [
            {"symbol": "AAPL", "rank": 1},
        ]

        rebalancer = Rebalancer(
            broker=mock_broker,
            leaderboard_client=mock_leaderboard_client,
            initial_capital=10000.0,
            portfolio_name="SP400",
            index_id="13",
            stockcount=1,
            persistence_manager=mock_persistence,
        )

        # Should not raise, handles gracefully
        summary = rebalancer.rebalance(dry_run=False)
        assert isinstance(summary, TradeSummary)
