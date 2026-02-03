"""Trade status checking for submitted orders."""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class TradeCheckResult:
    """Result of checking submitted trade statuses."""

    checked: int = 0
    filled: int = 0
    failed: int = 0
    still_pending: int = 0
    filled_trades: List[Dict[str, Any]] = field(default_factory=list)
    failed_trades: List[Dict[str, Any]] = field(default_factory=list)

    def all_terminal(self) -> bool:
        """Check if all checked trades reached terminal status."""
        return self.still_pending == 0 and self.checked > 0


class TradeStatusChecker:
    """Checks submitted trades with broker and updates status in database."""

    def __init__(self, persistence_manager, broker):
        """
        Initialize trade status checker.

        Args:
            persistence_manager: PersistenceManager instance for database operations
            broker: Broker instance for checking order status
        """
        self.persistence_manager = persistence_manager
        self.broker = broker

    def check_submitted_trades(self, portfolio_name: str) -> TradeCheckResult:
        """
        Check all submitted trades for a portfolio with broker and update DB.

        Queries the broker for each submitted trade's order status and updates
        the trade record in Firestore accordingly:
        - Filled orders -> status='filled' with fill data
        - Rejected/cancelled/expired -> status='failed' with error
        - Still pending -> remains status='submitted'

        Args:
            portfolio_name: Portfolio name to check

        Returns:
            TradeCheckResult with counts and details of checked trades
        """
        result = TradeCheckResult()

        # Get all submitted trades
        submitted_trades = self.persistence_manager.get_submitted_trades(portfolio_name)

        if not submitted_trades:
            logger.debug(f"[{portfolio_name}] No submitted trades to check")
            return result

        logger.info(f"[{portfolio_name}] Checking {len(submitted_trades)} submitted trades...")

        for trade in submitted_trades:
            broker_order_id = trade.get('broker_order_id')
            if not broker_order_id:
                logger.warning(f"Trade {trade.get('doc_id')} has no broker_order_id, skipping")
                continue

            result.checked += 1

            try:
                # Query broker for order status
                order_status = self.broker.get_order_status(broker_order_id)
                status = order_status.get('status', 'pending')

                if status == 'filled':
                    # Update trade as filled
                    filled_qty = order_status.get('filled_qty', 0.0)
                    filled_price = order_status.get('filled_avg_price', 0.0)
                    total = filled_qty * filled_price

                    self.persistence_manager.update_trade_filled(
                        trade['doc_id'],
                        quantity=filled_qty,
                        price=filled_price,
                        total=total,
                    )

                    result.filled += 1
                    result.filled_trades.append({
                        'symbol': trade.get('symbol'),
                        'action': trade.get('action'),
                        'quantity': filled_qty,
                        'price': filled_price,
                        'total': total,
                        'broker_order_id': broker_order_id,
                    })

                    logger.info(
                        f"[{portfolio_name}] Trade filled: {trade.get('symbol')} "
                        f"{trade.get('action')} {filled_qty:.2f} @ ${filled_price:.2f}"
                    )

                    # Update cash balance if persistence manager supports it
                    self._update_cash_for_filled_trade(
                        portfolio_name,
                        trade.get('action'),
                        total,
                    )

                elif status in ['cancelled', 'rejected', 'expired']:
                    # Update trade as failed
                    error_msg = f"Order {status}"
                    self.persistence_manager.update_trade_failed(
                        trade['doc_id'],
                        error_msg,
                    )

                    result.failed += 1
                    result.failed_trades.append({
                        'symbol': trade.get('symbol'),
                        'action': trade.get('action'),
                        'error': error_msg,
                        'broker_order_id': broker_order_id,
                    })

                    logger.warning(
                        f"[{portfolio_name}] Trade failed: {trade.get('symbol')} "
                        f"{trade.get('action')} - {error_msg}"
                    )

                else:
                    # Still pending
                    result.still_pending += 1
                    logger.debug(
                        f"[{portfolio_name}] Trade still pending: {trade.get('symbol')} "
                        f"{trade.get('action')} (status: {status})"
                    )

            except Exception as e:
                logger.error(
                    f"[{portfolio_name}] Error checking trade {trade.get('doc_id')}: {e}"
                )
                # Don't change status on error, leave as submitted
                result.still_pending += 1

        # Log summary
        logger.info(
            f"[{portfolio_name}] Trade check complete: {result.checked} checked, "
            f"{result.filled} filled, {result.failed} failed, "
            f"{result.still_pending} still pending"
        )

        return result

    def _update_cash_for_filled_trade(
        self,
        portfolio_name: str,
        action: str,
        total: float,
    ) -> None:
        """
        Update portfolio cash balance for a filled trade.

        Args:
            portfolio_name: Portfolio name
            action: Trade action ('BUY' or 'SELL')
            total: Total trade value
        """
        try:
            is_buy = action.upper() == 'BUY'
            self.persistence_manager.update_portfolio_cash(
                portfolio_name,
                total,
                is_buy=is_buy,
            )
        except Exception as e:
            logger.warning(f"[{portfolio_name}] Error updating cash for filled trade: {e}")

    def all_trades_terminal(self, portfolio_name: str) -> bool:
        """
        Check if all trades for a portfolio have reached terminal status.

        Terminal statuses are: 'filled' or 'failed'
        Non-terminal statuses are: 'planned' or 'submitted'

        Args:
            portfolio_name: Portfolio name

        Returns:
            True if no trades in 'submitted' status, False otherwise
        """
        submitted_trades = self.persistence_manager.get_submitted_trades(portfolio_name)
        return len(submitted_trades) == 0

    def get_trade_summary(self, portfolio_name: str) -> Dict[str, int]:
        """
        Get summary of trade statuses for a portfolio from today's run.

        Args:
            portfolio_name: Portfolio name

        Returns:
            Dict with counts: submitted, filled, failed
        """
        # Get today's execution run
        run = self.persistence_manager.get_execution_run(portfolio_name)
        if not run:
            return {'submitted': 0, 'filled': 0, 'failed': 0}

        return {
            'submitted': run.get('trades_submitted', 0),
            'filled': run.get('trades_filled', 0),
            'failed': run.get('trades_failed', 0),
        }
