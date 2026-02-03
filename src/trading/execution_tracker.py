"""Execution run tracking for portfolio rebalancing."""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ExecutionTracker:
    """Tracks execution runs per portfolio per day."""

    def __init__(self, persistence_manager):
        """
        Initialize execution tracker.

        Args:
            persistence_manager: PersistenceManager instance for database operations
        """
        self.persistence_manager = persistence_manager

    def start_run(self, portfolio_name: str) -> str:
        """
        Start a new execution run for a portfolio.

        Creates or restarts an execution run document for today.

        Args:
            portfolio_name: Portfolio name

        Returns:
            Execution run ID (format: {portfolio_name}_{date})
        """
        return self.persistence_manager.start_execution_run(portfolio_name)

    def complete_run(self, run_id: str, trade_counts: Dict[str, int]) -> None:
        """
        Mark execution run as completed with trade counts.

        Args:
            run_id: Execution run ID
            trade_counts: Dict with keys: trades_planned, trades_submitted,
                          trades_filled, trades_failed
        """
        self.persistence_manager.update_execution_run(
            run_id,
            status='completed',
            completed_at=datetime.now(),
            trades_planned=trade_counts.get('trades_planned', 0),
            trades_submitted=trade_counts.get('trades_submitted', 0),
            trades_filled=trade_counts.get('trades_filled', 0),
            trades_failed=trade_counts.get('trades_failed', 0),
        )
        logger.info(f"Execution run {run_id} completed: {trade_counts}")

    def fail_run(self, run_id: str, error: str) -> None:
        """
        Mark execution run as failed.

        Args:
            run_id: Execution run ID
            error: Error message describing the failure
        """
        self.persistence_manager.update_execution_run(
            run_id,
            status='failed',
            completed_at=datetime.now(),
            error_message=error,
        )
        logger.error(f"Execution run {run_id} failed: {error}")

    def was_successful_today(self, portfolio_name: str) -> bool:
        """
        Check if portfolio already completed successfully today.

        A run is successful when:
        1. status == "completed"
        2. trades_submitted == 0 (all trades reached terminal status)

        Args:
            portfolio_name: Portfolio name

        Returns:
            True if portfolio has successfully completed today
        """
        return self.persistence_manager.was_successful_today(portfolio_name)

    def get_today_run(self, portfolio_name: str) -> Optional[Dict[str, Any]]:
        """
        Get today's execution run data for a portfolio.

        Args:
            portfolio_name: Portfolio name

        Returns:
            Execution run data dict, or None if no run today
        """
        return self.persistence_manager.get_execution_run(portfolio_name)

    def update_trade_counts(self, run_id: str, **counts) -> None:
        """
        Update trade counts for an execution run.

        Args:
            run_id: Execution run ID
            **counts: Trade counts to update (trades_submitted, trades_filled, etc.)
        """
        self.persistence_manager.update_execution_run(run_id, **counts)
