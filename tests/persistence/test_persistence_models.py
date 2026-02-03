"""Tests for persistence models."""

import pytest
from datetime import datetime

from src.persistence.models import (
    TradeRecord,
    OwnershipRecord,
    ExternalSaleRecord,
    PortfolioCashRecord,
    ExecutionRunRecord,
)


class TestTradeRecord:
    """Tests for TradeRecord dataclass."""

    def test_to_dict_basic(self):
        """to_dict() returns all fields."""
        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=10.0,
            price=150.0,
            total=1500.0,
            timestamp=datetime(2025, 1, 27, 10, 0, 0),
            portfolio_name="SP400",
        )
        result = trade.to_dict()

        assert result['symbol'] == 'AAPL'
        assert result['action'] == 'BUY'
        assert result['quantity'] == 10.0
        assert result['price'] == 150.0
        assert result['total'] == 1500.0
        assert result['portfolio_name'] == 'SP400'
        assert result['status'] == 'planned'  # Default

    def test_to_dict_with_status_fields(self):
        """to_dict() includes status tracking fields when set."""
        trade = TradeRecord(
            symbol="MSFT",
            action="SELL",
            quantity=5.0,
            price=300.0,
            total=1500.0,
            timestamp=datetime(2025, 1, 27, 10, 0, 0),
            portfolio_name="SP400",
            status="submitted",
            execution_run_id="SP400_2025-01-27",
            broker_order_id="order_123",
            submitted_at=datetime(2025, 1, 27, 10, 5, 0),
        )
        result = trade.to_dict()

        assert result['status'] == 'submitted'
        assert result['execution_run_id'] == 'SP400_2025-01-27'
        assert result['broker_order_id'] == 'order_123'
        assert result['submitted_at'] == datetime(2025, 1, 27, 10, 5, 0)

    def test_to_dict_omits_none_optional_fields(self):
        """to_dict() doesn't include optional fields that are None."""
        trade = TradeRecord(
            symbol="AAPL",
            action="BUY",
            quantity=10.0,
            price=150.0,
            total=1500.0,
            timestamp=datetime(2025, 1, 27, 10, 0, 0),
        )
        result = trade.to_dict()

        assert 'execution_run_id' not in result
        assert 'submitted_at' not in result
        assert 'filled_at' not in result
        assert 'failed_at' not in result
        assert 'error_message' not in result
        assert 'broker_order_id' not in result

    def test_symbol_uppercase(self):
        """Symbol is converted to uppercase in to_dict()."""
        trade = TradeRecord(
            symbol="aapl",
            action="BUY",
            quantity=10.0,
            price=150.0,
            total=1500.0,
            timestamp=datetime(2025, 1, 27, 10, 0, 0),
        )
        result = trade.to_dict()

        assert result['symbol'] == 'AAPL'


class TestPortfolioCashRecord:
    """Tests for PortfolioCashRecord dataclass."""

    def test_to_dict(self):
        """to_dict() returns all fields."""
        now = datetime.now()
        record = PortfolioCashRecord(
            portfolio_name="SP400",
            initial_capital=10000.0,
            cash_balance=8500.0,
            created_at=now,
            last_updated=now,
        )
        result = record.to_dict()

        assert result['portfolio_name'] == 'SP400'
        assert result['initial_capital'] == 10000.0
        assert result['cash_balance'] == 8500.0
        assert result['created_at'] == now
        assert result['last_updated'] == now


class TestExecutionRunRecord:
    """Tests for ExecutionRunRecord dataclass."""

    def test_to_dict_basic(self):
        """to_dict() returns all fields."""
        now = datetime.now()
        record = ExecutionRunRecord(
            portfolio_name="SP400",
            date="2025-01-27",
            status="started",
            started_at=now,
        )
        result = record.to_dict()

        assert result['portfolio_name'] == 'SP400'
        assert result['date'] == '2025-01-27'
        assert result['status'] == 'started'
        assert result['started_at'] == now
        assert result['trades_planned'] == 0
        assert result['trades_submitted'] == 0
        assert result['trades_filled'] == 0
        assert result['trades_failed'] == 0

    def test_to_dict_completed(self):
        """to_dict() includes completed_at when set."""
        now = datetime.now()
        record = ExecutionRunRecord(
            portfolio_name="SP400",
            date="2025-01-27",
            status="completed",
            started_at=now,
            completed_at=now,
            trades_planned=5,
            trades_submitted=0,
            trades_filled=4,
            trades_failed=1,
        )
        result = record.to_dict()

        assert result['status'] == 'completed'
        assert result['completed_at'] == now
        assert result['trades_planned'] == 5
        assert result['trades_filled'] == 4
        assert result['trades_failed'] == 1

    def test_is_successful_completed_all_terminal(self):
        """is_successful() returns True when completed with no pending trades."""
        record = ExecutionRunRecord(
            portfolio_name="SP400",
            date="2025-01-27",
            status="completed",
            started_at=datetime.now(),
            trades_submitted=0,  # All terminal
        )
        assert record.is_successful() is True

    def test_is_successful_false_when_pending(self):
        """is_successful() returns False when trades still pending."""
        record = ExecutionRunRecord(
            portfolio_name="SP400",
            date="2025-01-27",
            status="completed",
            started_at=datetime.now(),
            trades_submitted=2,  # Some pending
        )
        assert record.is_successful() is False

    def test_is_successful_false_when_not_completed(self):
        """is_successful() returns False when status is not 'completed'."""
        record = ExecutionRunRecord(
            portfolio_name="SP400",
            date="2025-01-27",
            status="started",
            started_at=datetime.now(),
            trades_submitted=0,
        )
        assert record.is_successful() is False

    def test_is_successful_false_when_failed(self):
        """is_successful() returns False when status is 'failed'."""
        record = ExecutionRunRecord(
            portfolio_name="SP400",
            date="2025-01-27",
            status="failed",
            started_at=datetime.now(),
            error_message="Error occurred",
        )
        assert record.is_successful() is False

    def test_to_dict_includes_error_message(self):
        """to_dict() includes error_message when set."""
        record = ExecutionRunRecord(
            portfolio_name="SP400",
            date="2025-01-27",
            status="failed",
            started_at=datetime.now(),
            error_message="Network timeout",
        )
        result = record.to_dict()

        assert result['error_message'] == "Network timeout"
