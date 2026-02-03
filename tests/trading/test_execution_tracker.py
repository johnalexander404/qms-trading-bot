"""Tests for ExecutionTracker."""

import pytest
from datetime import datetime
from src.trading.execution_tracker import ExecutionTracker


class TestExecutionTracker:
    """Tests for ExecutionTracker class."""

    def test_start_run_creates_document(self, mock_persistence):
        """Starting a run creates execution_runs doc with status='started'."""
        tracker = ExecutionTracker(mock_persistence)
        run_id = tracker.start_run("SP400")

        assert run_id is not None
        assert "SP400" in run_id
        run = mock_persistence.execution_runs.get(run_id)
        assert run is not None
        assert run['status'] == 'started'
        assert run['portfolio_name'] == 'SP400'

    def test_complete_run_updates_status(self, mock_persistence):
        """Completing a run sets status='completed' and trade counts."""
        tracker = ExecutionTracker(mock_persistence)
        run_id = tracker.start_run("SP400")

        tracker.complete_run(run_id, {
            'trades_planned': 5,
            'trades_submitted': 3,
            'trades_filled': 2,
            'trades_failed': 0,
        })

        run = mock_persistence.execution_runs.get(run_id)
        assert run['status'] == 'completed'
        assert run['trades_planned'] == 5
        assert run['trades_submitted'] == 3
        assert run['trades_filled'] == 2
        assert run['trades_failed'] == 0
        assert run['completed_at'] is not None

    def test_fail_run_records_error(self, mock_persistence):
        """Failing a run sets status='failed' and error message."""
        tracker = ExecutionTracker(mock_persistence)
        run_id = tracker.start_run("SP400")

        tracker.fail_run(run_id, "Network timeout")

        run = mock_persistence.execution_runs.get(run_id)
        assert run['status'] == 'failed'
        assert run['error_message'] == "Network timeout"
        assert run['completed_at'] is not None

    def test_was_successful_today_true_when_completed_all_terminal(self, mock_persistence):
        """Returns True when completed AND trades_submitted=0."""
        tracker = ExecutionTracker(mock_persistence)
        run_id = tracker.start_run("SP400")

        # Complete with all trades terminal
        tracker.complete_run(run_id, {
            'trades_planned': 5,
            'trades_submitted': 0,  # All trades reached terminal status
            'trades_filled': 4,
            'trades_failed': 1,
        })

        assert tracker.was_successful_today("SP400") is True

    def test_was_successful_today_false_when_trades_pending(self, mock_persistence):
        """Returns False when trades still in submitted status."""
        tracker = ExecutionTracker(mock_persistence)
        run_id = tracker.start_run("SP400")

        # Complete but with trades still pending
        tracker.complete_run(run_id, {
            'trades_planned': 5,
            'trades_submitted': 2,  # Some trades still pending
            'trades_filled': 2,
            'trades_failed': 1,
        })

        assert tracker.was_successful_today("SP400") is False

    def test_was_successful_today_false_when_not_run(self, mock_persistence):
        """Returns False when no run exists for today."""
        tracker = ExecutionTracker(mock_persistence)
        assert tracker.was_successful_today("SP400") is False

    def test_was_successful_today_false_when_failed(self, mock_persistence):
        """Returns False when run status is 'failed'."""
        tracker = ExecutionTracker(mock_persistence)
        run_id = tracker.start_run("SP400")
        tracker.fail_run(run_id, "Error occurred")

        assert tracker.was_successful_today("SP400") is False

    def test_get_today_run_returns_data(self, mock_persistence):
        """get_today_run returns execution run data."""
        tracker = ExecutionTracker(mock_persistence)
        run_id = tracker.start_run("SP400")

        run = tracker.get_today_run("SP400")
        assert run is not None
        assert run['portfolio_name'] == 'SP400'
        assert run['status'] == 'started'

    def test_get_today_run_returns_none_when_no_run(self, mock_persistence):
        """get_today_run returns None when no run exists."""
        tracker = ExecutionTracker(mock_persistence)
        run = tracker.get_today_run("SP400")
        assert run is None

    def test_update_trade_counts(self, mock_persistence):
        """update_trade_counts updates execution run counts."""
        tracker = ExecutionTracker(mock_persistence)
        run_id = tracker.start_run("SP400")

        tracker.update_trade_counts(run_id, trades_filled=3, trades_failed=1)

        run = mock_persistence.execution_runs.get(run_id)
        assert run['trades_filled'] == 3
        assert run['trades_failed'] == 1
