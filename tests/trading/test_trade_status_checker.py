"""Tests for TradeStatusChecker."""

import pytest
from datetime import datetime
from unittest.mock import Mock
from src.trading.trade_status_checker import TradeStatusChecker, TradeCheckResult
from src.persistence.models import TradeRecord


class TestTradeStatusChecker:
    """Tests for TradeStatusChecker class."""

    def test_check_submitted_trades_updates_filled(self, mock_persistence, mock_broker):
        """Filled orders get status='filled' with fill data."""
        checker = TradeStatusChecker(mock_persistence, mock_broker)

        # Setup a submitted trade
        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=0,
            price=0,
            total=1000,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )
        doc_id = mock_persistence.record_planned_trade(trade, "SP400_2025-01-27")
        mock_persistence.update_trade_submitted(doc_id, "order_123")

        # Mock broker returns filled status
        mock_broker.get_order_status.return_value = {
            'status': 'filled',
            'filled_qty': 10.0,
            'filled_avg_price': 100.0,
        }

        result = checker.check_submitted_trades("SP400")

        assert result.checked == 1
        assert result.filled == 1
        assert result.failed == 0
        assert result.still_pending == 0
        assert len(result.filled_trades) == 1
        assert result.filled_trades[0]['symbol'] == 'AAPL'

        # Verify trade was updated
        trade_data = mock_persistence.trades[doc_id]
        assert trade_data['status'] == 'filled'
        assert trade_data['quantity'] == 10.0
        assert trade_data['price'] == 100.0

    def test_check_submitted_trades_updates_failed(self, mock_persistence, mock_broker):
        """Rejected/cancelled orders get status='failed'."""
        checker = TradeStatusChecker(mock_persistence, mock_broker)

        # Setup a submitted trade
        trade = TradeRecord(
            symbol="MSFT",
            action="SELL",
            quantity=5,
            price=300,
            total=1500,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )
        doc_id = mock_persistence.record_planned_trade(trade, "SP400_2025-01-27")
        mock_persistence.update_trade_submitted(doc_id, "order_456")

        # Mock broker returns rejected status
        mock_broker.get_order_status.return_value = {
            'status': 'rejected',
            'filled_qty': 0,
            'filled_avg_price': 0,
        }

        result = checker.check_submitted_trades("SP400")

        assert result.checked == 1
        assert result.filled == 0
        assert result.failed == 1
        assert result.still_pending == 0
        assert len(result.failed_trades) == 1

        # Verify trade was updated
        trade_data = mock_persistence.trades[doc_id]
        assert trade_data['status'] == 'failed'
        assert 'Order rejected' in trade_data['error_message']

    def test_check_submitted_trades_leaves_pending(self, mock_persistence, mock_broker):
        """Pending orders stay status='submitted'."""
        checker = TradeStatusChecker(mock_persistence, mock_broker)

        # Setup a submitted trade
        trade = TradeRecord(
            symbol="GOOGL",
            action="BUY",
            quantity=0,
            price=0,
            total=500,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )
        doc_id = mock_persistence.record_planned_trade(trade, "SP400_2025-01-27")
        mock_persistence.update_trade_submitted(doc_id, "order_789")

        # Mock broker returns pending status
        mock_broker.get_order_status.return_value = {
            'status': 'pending',
            'filled_qty': 0,
            'filled_avg_price': 0,
        }

        result = checker.check_submitted_trades("SP400")

        assert result.checked == 1
        assert result.filled == 0
        assert result.failed == 0
        assert result.still_pending == 1

        # Verify trade status unchanged
        trade_data = mock_persistence.trades[doc_id]
        assert trade_data['status'] == 'submitted'

    def test_all_trades_terminal_true_when_all_filled_or_failed(self, mock_persistence, mock_broker):
        """Returns True when no submitted trades remain."""
        checker = TradeStatusChecker(mock_persistence, mock_broker)

        # No submitted trades
        assert checker.all_trades_terminal("SP400") is True

        # Add a filled trade (not submitted)
        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=10,
            price=100,
            total=1000,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )
        doc_id = mock_persistence.record_planned_trade(trade, "SP400_2025-01-27")
        mock_persistence.trades[doc_id]['status'] = 'filled'

        assert checker.all_trades_terminal("SP400") is True

    def test_all_trades_terminal_false_when_pending(self, mock_persistence, mock_broker):
        """Returns False when submitted trades exist."""
        checker = TradeStatusChecker(mock_persistence, mock_broker)

        # Add a submitted trade
        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=0,
            price=0,
            total=1000,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )
        doc_id = mock_persistence.record_planned_trade(trade, "SP400_2025-01-27")
        mock_persistence.update_trade_submitted(doc_id, "order_123")

        assert checker.all_trades_terminal("SP400") is False

    def test_broker_error_handled_gracefully(self, mock_persistence, mock_broker):
        """Broker API errors don't crash, trade stays submitted."""
        checker = TradeStatusChecker(mock_persistence, mock_broker)

        # Setup a submitted trade
        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=0,
            price=0,
            total=1000,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )
        doc_id = mock_persistence.record_planned_trade(trade, "SP400_2025-01-27")
        mock_persistence.update_trade_submitted(doc_id, "order_123")

        # Mock broker raises exception
        mock_broker.get_order_status.side_effect = Exception("API error")

        result = checker.check_submitted_trades("SP400")

        assert result.checked == 1
        assert result.still_pending == 1  # Error treated as pending
        assert result.filled == 0
        assert result.failed == 0

        # Trade status should remain submitted
        trade_data = mock_persistence.trades[doc_id]
        assert trade_data['status'] == 'submitted'

    def test_check_result_all_terminal(self):
        """TradeCheckResult.all_terminal() works correctly."""
        # All terminal
        result = TradeCheckResult(checked=5, filled=3, failed=2, still_pending=0)
        assert result.all_terminal() is True

        # Some pending
        result = TradeCheckResult(checked=5, filled=2, failed=1, still_pending=2)
        assert result.all_terminal() is False

        # Nothing checked
        result = TradeCheckResult(checked=0, filled=0, failed=0, still_pending=0)
        assert result.all_terminal() is False

    def test_skips_trades_without_broker_order_id(self, mock_persistence, mock_broker):
        """Trades without broker_order_id are skipped."""
        checker = TradeStatusChecker(mock_persistence, mock_broker)

        # Setup a submitted trade without broker_order_id
        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=0,
            price=0,
            total=1000,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )
        doc_id = mock_persistence.record_planned_trade(trade, "SP400_2025-01-27")
        mock_persistence.trades[doc_id]['status'] = 'submitted'
        # Note: not setting broker_order_id

        result = checker.check_submitted_trades("SP400")

        assert result.checked == 0  # Trade was skipped
        mock_broker.get_order_status.assert_not_called()

    def test_check_submitted_trades_empty(self, mock_persistence, mock_broker):
        """Returns empty result when no submitted trades exist."""
        checker = TradeStatusChecker(mock_persistence, mock_broker)

        # No trades exist
        result = checker.check_submitted_trades("SP400")

        assert result.checked == 0
        assert result.filled == 0
        assert result.failed == 0
        assert result.still_pending == 0
        mock_broker.get_order_status.assert_not_called()

    def test_update_cash_for_filled_trade_buy(self, mock_persistence, mock_broker):
        """Cash is updated correctly for filled BUY trade."""
        checker = TradeStatusChecker(mock_persistence, mock_broker)

        # Initialize cash
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)

        # Setup a submitted trade
        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=0,
            price=0,
            total=1000,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )
        doc_id = mock_persistence.record_planned_trade(trade, "SP400_2025-01-27")
        mock_persistence.update_trade_submitted(doc_id, "order_123")

        # Mock broker returns filled status
        mock_broker.get_order_status.return_value = {
            'status': 'filled',
            'filled_qty': 10.0,
            'filled_avg_price': 100.0,
        }

        result = checker.check_submitted_trades("SP400")

        # Cash should be debited
        assert mock_persistence.get_portfolio_cash("SP400") == 9000.0  # 10000 - 1000

    def test_update_cash_for_filled_trade_sell(self, mock_persistence, mock_broker):
        """Cash is updated correctly for filled SELL trade."""
        checker = TradeStatusChecker(mock_persistence, mock_broker)

        # Initialize cash
        mock_persistence.initialize_portfolio_cash("SP400", 10000.0)

        # Setup a submitted SELL trade
        trade = TradeRecord(
            symbol="AAPL",
            action="SELL",
            quantity=10,
            price=150,
            total=1500,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )
        doc_id = mock_persistence.record_planned_trade(trade, "SP400_2025-01-27")
        mock_persistence.update_trade_submitted(doc_id, "order_123")

        # Mock broker returns filled status
        mock_broker.get_order_status.return_value = {
            'status': 'filled',
            'filled_qty': 10.0,
            'filled_avg_price': 150.0,
        }

        result = checker.check_submitted_trades("SP400")

        # Cash should be credited
        assert mock_persistence.get_portfolio_cash("SP400") == 11500.0  # 10000 + 1500

    def test_update_cash_error_handled(self, mock_persistence, mock_broker):
        """Cash update error is handled gracefully."""
        checker = TradeStatusChecker(mock_persistence, mock_broker)

        # Setup a submitted trade
        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=0,
            price=0,
            total=1000,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )
        doc_id = mock_persistence.record_planned_trade(trade, "SP400_2025-01-27")
        mock_persistence.update_trade_submitted(doc_id, "order_123")

        # Mock broker returns filled
        mock_broker.get_order_status.return_value = {
            'status': 'filled',
            'filled_qty': 10.0,
            'filled_avg_price': 100.0,
        }

        # Mock cash update to raise error
        mock_persistence.update_portfolio_cash = Mock(side_effect=Exception("DB error"))

        # Should not raise, just log warning
        result = checker.check_submitted_trades("SP400")

        assert result.filled == 1  # Trade was still marked as filled

    def test_get_trade_summary_with_run(self, mock_persistence, mock_broker):
        """get_trade_summary returns counts from execution run."""
        checker = TradeStatusChecker(mock_persistence, mock_broker)

        # Create an execution run with trade counts
        run_id = mock_persistence.start_execution_run("SP400")
        mock_persistence.update_execution_run(
            run_id,
            trades_submitted=2,
            trades_filled=3,
            trades_failed=1,
        )

        summary = checker.get_trade_summary("SP400")

        assert summary['submitted'] == 2
        assert summary['filled'] == 3
        assert summary['failed'] == 1

    def test_get_trade_summary_no_run(self, mock_persistence, mock_broker):
        """get_trade_summary returns zeros when no run exists."""
        checker = TradeStatusChecker(mock_persistence, mock_broker)

        # No execution run exists
        summary = checker.get_trade_summary("SP400")

        assert summary['submitted'] == 0
        assert summary['filled'] == 0
        assert summary['failed'] == 0

    def test_cancelled_order_marked_failed(self, mock_persistence, mock_broker):
        """Cancelled orders are marked as failed."""
        checker = TradeStatusChecker(mock_persistence, mock_broker)

        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=0,
            price=0,
            total=1000,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )
        doc_id = mock_persistence.record_planned_trade(trade, "SP400_2025-01-27")
        mock_persistence.update_trade_submitted(doc_id, "order_123")

        mock_broker.get_order_status.return_value = {
            'status': 'cancelled',
            'filled_qty': 0,
            'filled_avg_price': 0,
        }

        result = checker.check_submitted_trades("SP400")

        assert result.failed == 1
        assert mock_persistence.trades[doc_id]['status'] == 'failed'

    def test_expired_order_marked_failed(self, mock_persistence, mock_broker):
        """Expired orders are marked as failed."""
        checker = TradeStatusChecker(mock_persistence, mock_broker)

        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=0,
            price=0,
            total=1000,
            timestamp=datetime.now(),
            portfolio_name="SP400",
        )
        doc_id = mock_persistence.record_planned_trade(trade, "SP400_2025-01-27")
        mock_persistence.update_trade_submitted(doc_id, "order_123")

        mock_broker.get_order_status.return_value = {
            'status': 'expired',
            'filled_qty': 0,
            'filled_avg_price': 0,
        }

        result = checker.check_submitted_trades("SP400")

        assert result.failed == 1
        assert 'Order expired' in mock_persistence.trades[doc_id]['error_message']
