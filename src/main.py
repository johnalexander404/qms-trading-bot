"""Main application entry point."""

import logging
import signal
import sys
import os
from typing import Optional, Dict, List
from datetime import datetime
import pytz

from .config import get_config
from .config.config import INDEX_NAME_TO_ID
from .broker import create_broker
from .broker.models import TradeSummary, PortfolioPerformance, MultiPortfolioSummary
from .leaderboard import LeaderboardClient
from .notifications import create_email_notifier
from .trading import Rebalancer, ExecutionTracker, TradeStatusChecker, CashManager
from .scheduler import create_scheduler
from .api import create_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class TradingBot:
    """Main trading bot application."""
    
    def __init__(self):
        """Initialize the trading bot."""
        self.config = get_config()
        self.broker = None
        self.leaderboard_client = None
        self.email_notifier = None
        self.rebalancers: Dict[str, Rebalancer] = {}
        self.scheduler = None
        self.app = None
        self.persistence_manager = None
        self.execution_tracker = None
        self.trade_status_checker = None
        self.cash_manager = None
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}. Shutting down...")
        self.shutdown()
        sys.exit(0)
    
    def initialize(self):
        """Initialize all components."""
        logger.info("Initializing trading bot...")
        
        # Initialize broker
        try:
            self.broker = create_broker()
            logger.info(f"Initialized broker: {self.config.broker.broker_type}")
        except Exception as e:
            logger.error(f"Error initializing broker: {e}")
            raise
        
        # Initialize leaderboard client
        try:
            self.leaderboard_client = LeaderboardClient(
                api_url=self.config.leaderboard_api_url,
                api_token=self.config.leaderboard_api_token,
            )
            logger.info("Initialized leaderboard client")
        except Exception as e:
            logger.error(f"Error initializing leaderboard client: {e}")
            raise
        
        # Initialize email notifier
        self.email_notifier = create_email_notifier()
        if self.email_notifier:
            logger.info(f"Initialized email notifier: {self.config.email.provider}")
        else:
            logger.info("Email notifications disabled")
        
        # Initialize persistence manager if enabled
        self.persistence_manager = None
        if self.config.persistence.enabled:
            try:
                if not self.config.persistence.is_configured():
                    logger.warning("Persistence enabled but credentials not configured. Disabling persistence.")
                else:
                    from .persistence import PersistenceManager
                    self.persistence_manager = PersistenceManager(
                        project_id=self.config.persistence.project_id,
                        credentials_path=self.config.persistence.credentials_path,
                        credentials_json=self.config.persistence.credentials_json,
                    )
                    logger.info("Initialized persistence manager (Firebase Firestore)")

                    # Initialize execution tracker, trade status checker, and cash manager
                    self.execution_tracker = ExecutionTracker(self.persistence_manager)
                    self.cash_manager = CashManager(self.persistence_manager)
                    logger.info("Initialized execution tracker and cash manager")
            except Exception as e:
                logger.warning(f"Failed to initialize persistence manager: {e}. Continuing without persistence.")
                self.persistence_manager = None
        else:
            logger.info("Persistence disabled")
            self.persistence_manager = None
        
        # Initialize rebalancers (one per portfolio)
        self.rebalancers: Dict[str, Rebalancer] = {}
        
        # If no portfolios configured, create default single portfolio
        if not self.config.portfolios:
            # Default to SP400
            from .config.config import PortfolioConfig
            default_portfolio = PortfolioConfig(
                portfolio_name="SP400",
                index_id=INDEX_NAME_TO_ID["SP400"],
                initial_capital=self.config.initial_capital,
                enabled=True,
                stockcount=self.config.default_stockcount,
                slack=self.config.default_slack,
            )
            self.config.portfolios = [default_portfolio]
        
        for portfolio_config in self.config.portfolios:
            if not portfolio_config.enabled:
                continue

            # Use portfolio config values, falling back to defaults if using default values and no persistence
            stockcount = portfolio_config.stockcount
            if stockcount == 5 and not self.persistence_manager:
                stockcount = self.config.default_stockcount

            slack = portfolio_config.slack
            if slack == 0 and not self.persistence_manager:
                slack = self.config.default_slack

            rebalancer = Rebalancer(
                broker=self.broker,
                leaderboard_client=self.leaderboard_client,
                initial_capital=portfolio_config.initial_capital,
                portfolio_name=portfolio_config.portfolio_name,
                index_id=portfolio_config.index_id,
                stockcount=stockcount,
                slack=slack,
                email_notifier=self.email_notifier,
                persistence_manager=self.persistence_manager,
            )
            self.rebalancers[portfolio_config.portfolio_name] = rebalancer
            logger.info(f"Initialized rebalancer for {portfolio_config.portfolio_name} portfolio (index {portfolio_config.index_id}, stockcount={stockcount}, slack={slack})")

            # Initialize cash balance for this portfolio
            if self.cash_manager:
                self.cash_manager.initialize(
                    portfolio_config.portfolio_name,
                    portfolio_config.initial_capital,
                )

        # Initialize trade status checker (requires broker)
        if self.persistence_manager and self.broker:
            self.trade_status_checker = TradeStatusChecker(
                self.persistence_manager,
                self.broker,
            )
            logger.info("Initialized trade status checker")

        # Initialize scheduler based on mode
        if self.config.scheduler.mode == "internal":
            self.scheduler = create_scheduler(job_function=self._execute_rebalancing)
            logger.info(f"Initialized internal scheduler with cron: {self.config.scheduler.cron_schedule}")
        else:
            # External scheduler mode - create webhook app
            self.app = create_app(
                job_function=self._execute_rebalancing,
                webhook_secret=self.config.scheduler.webhook_secret,
            )
            logger.info(f"Initialized webhook endpoint on port {self.config.scheduler.webhook_port}")
    
    def _is_market_open_time(self) -> bool:
        """
        Check if current time is within the trading window (9:30-10:00 AM ET).
        This ensures timezone-aware scheduling works correctly with DST.
        Expanded to 30-minute window to support cron resilience (every 5 min).

        Manual triggers skip day/time check and always return True.
        Scheduled runs must be on Monday within the 9:30-10:00 AM ET window.

        Returns:
            True if manual trigger, or if within 9:30-10:00 AM ET on Monday
        """
        # Manual triggers skip day/time check
        if self._is_manual_trigger():
            logger.info("Manual trigger detected - skipping day/time check")
            return True

        # Check FORCE_RUN environment variable (for backward compatibility)
        force_run = os.getenv("FORCE_RUN", "false").lower() == "true"
        if force_run:
            logger.info("FORCE_RUN=true - allowing execution regardless of time/day")
            return True

        # Get current time in Eastern Time
        eastern = pytz.timezone('America/New_York')
        now_et = datetime.now(eastern)

        # Check if it's Monday
        is_monday = now_et.weekday() == 0  # Monday is 0

        if not is_monday:
            logger.info(
                f"Skipping execution - not Monday. "
                f"Current ET time: {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}, "
                f"Day: {now_et.strftime('%A')}"
            )
            return False

        # Check if within 9:30 AM - 10:00 AM window (30 minutes)
        current_minute = now_et.hour * 60 + now_et.minute
        window_start = 9 * 60 + 30   # 9:30 AM
        window_end = 10 * 60         # 10:00 AM

        if window_start <= current_minute <= window_end:
            logger.info(
                f"Within trading window: {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')} "
                f"(9:30-10:00 AM ET)"
            )
            return True

        logger.info(
            f"Skipping execution - not within trading window. "
            f"Current ET time: {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}, "
            f"Expected: Monday 9:30-10:00 AM ET"
        )
        return False
    
    def _is_manual_trigger(self) -> bool:
        """
        Check if the execution was manually triggered (vs scheduled).
        
        Returns:
            True if manually triggered, False if scheduled or unknown
        """
        # Check GitHub Actions environment variables
        github_event = os.getenv("GITHUB_EVENT_NAME", "")
        if github_event == "workflow_dispatch":
            return True
        elif github_event == "schedule":
            return False
        
        # If not in GitHub Actions, check FORCE_RUN as indicator of manual trigger
        # (though this is not definitive)
        return False
    
    def _should_execute_trades(self) -> bool:
        """
        Check if trades should actually be executed (not dry-run).
        
        - Scheduled runs (cron): Always execute
        - Manual triggers: Only execute if FORCE_RUN=true, otherwise dry-run
        
        Returns:
            True to execute trades, False for dry-run mode
        """
        is_manual = self._is_manual_trigger()
        
        if not is_manual:
            # Scheduled run - always execute
            return True
        
        # Manual trigger - only execute if FORCE_RUN=true
        force_run = os.getenv("FORCE_RUN", "false").lower() == "true"
        return force_run
    
    def _execute_rebalancing(self):
        """Execute rebalancing (wrapper for scheduler/webhook)."""
        # Detect if this is a manual trigger or scheduled run
        is_manual = self._is_manual_trigger()
        trigger_type = "Manual trigger" if is_manual else "Scheduled run (cron)"
        logger.info(f"Execution triggered by: {trigger_type}")

        # Timezone-aware check: only execute within trading window
        # This handles DST automatically since we check the actual ET time
        # FORCE_RUN=true allows execution at any time
        if not self._is_market_open_time():
            logger.info("Not executing rebalancing - not within trading window (9:30-10:00 AM ET)")
            return None

        # STEP 1: Check status of submitted trades from previous runs
        if self.trade_status_checker:
            for portfolio_name in self.rebalancers.keys():
                check_result = self.trade_status_checker.check_submitted_trades(portfolio_name)
                if check_result.checked > 0:
                    logger.info(
                        f"[{portfolio_name}] Checked {check_result.checked} submitted trades: "
                        f"{check_result.filled} filled, {check_result.failed} failed, "
                        f"{check_result.still_pending} still pending"
                    )

                    # Update execution run counts if we have an execution tracker
                    if self.execution_tracker:
                        run = self.execution_tracker.get_today_run(portfolio_name)
                        if run:
                            self.execution_tracker.update_trade_counts(
                                run['run_id'],
                                trades_filled=run.get('trades_filled', 0) + check_result.filled,
                                trades_failed=run.get('trades_failed', 0) + check_result.failed,
                                trades_submitted=check_result.still_pending,
                            )

        # STEP 2: Check if all portfolios already completed successfully today
        if self.execution_tracker:
            all_successful = all(
                self.execution_tracker.was_successful_today(name)
                for name in self.rebalancers.keys()
            )
            if all_successful:
                logger.info("All portfolios already successfully completed today. Exiting.")
                # Send completion email if not already sent
                self._send_completion_email()
                return None

        # Check if we should execute trades or just simulate (dry-run)
        dry_run = not self._should_execute_trades()

        if dry_run:
            logger.info("=" * 60)
            logger.info("DRY-RUN MODE: Showing what would be executed (no trades will be placed)")
            if is_manual:
                logger.info("Manual trigger detected - Set FORCE_RUN=true to actually execute trades")
            logger.info("=" * 60)
        else:
            if is_manual:
                logger.info("Executing rebalancing (Manual trigger with FORCE_RUN=true)...")
            else:
                logger.info("Executing rebalancing (Scheduled run - always executes)...")

        # STEP 3: Start execution runs for each portfolio
        execution_run_ids = {}
        if self.execution_tracker and not dry_run:
            for portfolio_name in self.rebalancers.keys():
                execution_run_ids[portfolio_name] = self.execution_tracker.start_run(portfolio_name)

        try:
            # Calculate PRE-TRADE performance (before executing any trades)
            # This shows current holdings vs initial capital
            pre_trade_performances: Dict[str, PortfolioPerformance] = {}
            pre_trade_allocations: Dict[str, List[Allocation]] = {}
            portfolio_leaderboards: Dict[str, List[str]] = {}
            
            if not self.rebalancers:
                raise ValueError("No portfolios configured. Please set TRADE_INDICES environment variable.")
            
            # First, get current holdings and calculate pre-trade performance
            for portfolio_name, rebalancer in self.rebalancers.items():
                try:
                    # Get current allocations (before trades)
                    all_allocations = self.broker.get_current_allocation()
                    filtered_allocations = rebalancer._filter_allocations_by_portfolio(all_allocations)
                    pre_trade_allocations[portfolio_name] = filtered_allocations
                    
                    # Calculate pre-trade portfolio value
                    pre_trade_value = sum(alloc.market_value for alloc in filtered_allocations)
                    
                    # Get ownership records for net_invested calculation
                    ownership_records = {}
                    if self.persistence_manager:
                        ownership_records = self.persistence_manager.get_portfolio_ownership_records(portfolio_name)
                    
                    # Create a TradeSummary with current holdings (no trades yet)
                    from .broker.models import TradeSummary
                    pre_trade_summary = TradeSummary(
                        buys=[],
                        sells=[],
                        total_cost=0.0,
                        total_proceeds=0.0,
                        final_allocations=filtered_allocations,
                        portfolio_value=pre_trade_value,
                        portfolio_name=portfolio_name,
                        initial_capital=rebalancer.initial_capital,
                    )
                    
                    # Calculate pre-trade performance
                    pre_trade_performance = self._calculate_portfolio_performance(portfolio_name, pre_trade_summary, ownership_records)
                    pre_trade_performances[portfolio_name] = pre_trade_performance
                    
                    # Get leaderboard symbols for this portfolio
                    current_week_mom_day = self.leaderboard_client._get_previous_sunday()
                    leaderboard_symbols = self.leaderboard_client.get_top_symbols(
                        top_n=rebalancer.stockcount,
                        mom_day=current_week_mom_day,
                        index_id=rebalancer.index_id
                    )
                    portfolio_leaderboards[portfolio_name] = leaderboard_symbols
                    
                    logger.info(f"[{portfolio_name}] Pre-trade portfolio value: ${pre_trade_value:.2f}, Return: ${pre_trade_performance.total_return:.2f} ({pre_trade_performance.total_return_pct:.2f}%)")
                except Exception as portfolio_error:
                    logger.error(f"[{portfolio_name}] Error calculating pre-trade performance: {portfolio_error}")
                    # Continue with other portfolios
            
            # Now execute rebalancing for each portfolio
            portfolio_summaries: Dict[str, TradeSummary] = {}

            for portfolio_name, rebalancer in self.rebalancers.items():
                execution_run_id = execution_run_ids.get(portfolio_name)
                try:
                    logger.info(f"[{portfolio_name}] Starting rebalancing...")
                    summary = rebalancer.rebalance(
                        dry_run=dry_run,
                        execution_run_id=execution_run_id,
                    )
                    portfolio_summaries[portfolio_name] = summary

                    logger.info(f"[{portfolio_name}] Rebalancing {'simulation' if dry_run else 'execution'} completed. Portfolio value: ${summary.portfolio_value:.2f}")

                    # Update execution run on completion
                    if self.execution_tracker and execution_run_id and not dry_run:
                        # Count trades by status
                        submitted_count = len([b for b in summary.buys if b.get('status') == 'submitted']) + \
                                         len([s for s in summary.sells if s.get('status') == 'submitted'])
                        failed_count = len(summary.failed_trades) if summary.failed_trades else 0
                        planned_count = len(summary.buys) + len(summary.sells)

                        self.execution_tracker.complete_run(
                            execution_run_id,
                            {
                                'trades_planned': planned_count,
                                'trades_submitted': submitted_count,
                                'trades_filled': 0,  # Will be updated when orders fill
                                'trades_failed': failed_count,
                            }
                        )
                except Exception as portfolio_error:
                    logger.error(f"[{portfolio_name}] Error during rebalancing: {portfolio_error}")
                    # Mark execution run as failed
                    if self.execution_tracker and execution_run_id and not dry_run:
                        self.execution_tracker.fail_run(execution_run_id, str(portfolio_error))
                    # Continue with other portfolios
            
            # Fetch ownership records for each portfolio (if persistence enabled) - needed for net_invested calculation
            portfolio_ownership = {}
            if self.persistence_manager:
                for portfolio_name in portfolio_summaries.keys():
                    portfolio_ownership[portfolio_name] = self.persistence_manager.get_portfolio_ownership_records(portfolio_name)
            
            # Calculate POST-TRADE performance metrics for each portfolio (after trades)
            performances: Dict[str, PortfolioPerformance] = {}
            for portfolio_name, summary in portfolio_summaries.items():
                ownership_records = portfolio_ownership.get(portfolio_name, {})
                performance = self._calculate_portfolio_performance(portfolio_name, summary, ownership_records)
                performances[portfolio_name] = performance
            
            # Create multi-portfolio summary with PRE-TRADE performance
            if len(portfolio_summaries) > 1:
                # Create pre-trade summary (current holdings before trades)
                pre_trade_summaries = {}
                for name in portfolio_summaries.keys():
                    perf = pre_trade_performances.get(name)
                    if perf:
                        # portfolio_value should be holdings-only (market value), not including cash balance
                        pre_trade_holdings = sum(alloc.market_value for alloc in pre_trade_allocations.get(name, []))
                        pre_trade_summaries[name] = TradeSummary(
                            buys=[],
                            sells=[],
                            total_cost=0.0,
                            total_proceeds=0.0,
                            final_allocations=pre_trade_allocations.get(name, []),
                            portfolio_value=pre_trade_holdings,  # Holdings-only, cash balance calculated separately
                            portfolio_name=name,
                            initial_capital=perf.initial_capital,
                        )
                pre_trade_multi_summary = self._create_multi_portfolio_summary(pre_trade_summaries, pre_trade_performances) if pre_trade_summaries else None
                
                # Create post-trade summary (after trades)
                multi_summary = self._create_multi_portfolio_summary(portfolio_summaries, performances)
                
                # Send email notification if enabled (only in real execution mode)
                if not dry_run and self.email_notifier and self.config.email.recipient:
                    try:
                        # Send email with pre-trade performance and planned trades
                        self.email_notifier.send_trade_summary(
                            recipient=self.config.email.recipient,
                            trade_summary=multi_summary,
                            portfolio_leaderboards=portfolio_leaderboards,
                            portfolio_ownership=portfolio_ownership if portfolio_ownership else None,
                            pre_trade_performance=pre_trade_multi_summary,  # Include pre-trade performance
                        )
                    except Exception as email_error:
                        logger.error(f"Error sending email notification: {email_error}")
                
                return multi_summary
            else:
                # Single portfolio - return single summary
                if not portfolio_summaries:
                    raise ValueError("No portfolio summaries generated. All portfolios may have failed during rebalancing.")
                
                summary = list(portfolio_summaries.values())[0]
                portfolio_name = list(portfolio_summaries.keys())[0]
                
                # Fetch ownership records for single portfolio (if persistence enabled) - needed for net_invested calculation
                portfolio_ownership = None
                ownership_records = {}
                if self.persistence_manager:
                    ownership_records = self.persistence_manager.get_portfolio_ownership_records(portfolio_name)
                    if ownership_records:
                        portfolio_ownership = {portfolio_name: ownership_records}
                
                # Note: Performance was already calculated above in the loop, but if we're here it means
                # we only have one portfolio, so the performance should already be in performances dict
                # However, we need to ensure it was calculated with ownership records
                if portfolio_name not in performances:
                    performance = self._calculate_portfolio_performance(portfolio_name, summary, ownership_records)
                    performances[portfolio_name] = performance
                
                # Send email notification if enabled (only in real execution mode)
                if not dry_run and self.email_notifier and self.config.email.recipient:
                    try:
                        leaderboard_symbols = list(portfolio_leaderboards.values())[0] if portfolio_leaderboards else []
                        self.email_notifier.send_trade_summary(
                            recipient=self.config.email.recipient,
                            trade_summary=summary,
                            leaderboard_symbols=leaderboard_symbols,
                            portfolio_ownership=portfolio_ownership,
                        )
                    except Exception as email_error:
                        logger.error(f"Error sending email notification: {email_error}")
                
                return summary
        except Exception as e:
            logger.error(f"Error during rebalancing: {e}")
            # Send error notification if email is enabled (only in real execution mode)
            if not dry_run and self.email_notifier and self.config.email.recipient:
                try:
                    self.email_notifier.send_error_notification(
                        recipient=self.config.email.recipient,
                        error_message=str(e),
                        context={"component": "rebalancer"},
                    )
                except Exception as email_error:
                    logger.error(f"Error sending error notification: {email_error}")
            raise
    
    def _calculate_portfolio_performance(
        self,
        portfolio_name: str,
        trade_summary: TradeSummary,
        ownership_records: Optional[Dict[str, Dict[str, float]]] = None
    ) -> PortfolioPerformance:
        """
        Calculate performance metrics for a portfolio.
        
        P&L is calculated based on PRE-TRADE state (before queued trades execute).
        Current run's trades are excluded from realized P&L calculation.
        """
        initial_capital = trade_summary.initial_capital
        current_holdings = trade_summary.portfolio_value  # Market value of current holdings
        # total_cost and total_proceeds from current run (these are queued, not executed)
        current_run_cost = trade_summary.total_cost
        current_run_proceeds = trade_summary.total_proceeds
        
        # Calculate cumulative realized P&L from ALL historical trades (EXCLUDING current run)
        # Current run's trades are queued and haven't executed, so they don't affect P&L
        cumulative_realized_pnl = 0.0
        if self.persistence_manager:
            try:
                all_trades = self.persistence_manager.get_all_trades_for_portfolio(portfolio_name)
                # Sum all historical SELL proceeds minus all historical BUY costs
                total_buy_costs = sum(trade['total'] for trade in all_trades if trade['action'] == 'BUY')
                total_sell_proceeds = sum(trade['total'] for trade in all_trades if trade['action'] == 'SELL')
                cumulative_realized_pnl = total_sell_proceeds - total_buy_costs
            except Exception as e:
                logger.warning(f"[{portfolio_name}] Error getting historical trades for P&L calculation: {e}")
                cumulative_realized_pnl = 0.0
        
        # Calculate portfolio cash balance (pre-trade)
        # Cash = initial_capital + cumulative realized P&L from historical trades
        portfolio_cash_balance = initial_capital + cumulative_realized_pnl
        
        # Calculate total current value (pre-trade)
        # Current value = current holdings + cash balance
        current_value = current_holdings + portfolio_cash_balance
        
        # Calculate net_invested: cost basis of current holdings
        # If persistence is enabled, use ownership records (sum of total_cost for all owned symbols)
        # Otherwise, fall back to trades from this run or initial capital
        if ownership_records:
            # Sum the total_cost (cost basis) for all current holdings
            net_invested = sum(record.get('total_cost', 0.0) for record in ownership_records.values())
        else:
            # Fall back to trades from this run, or initial capital if no trades
            net_invested = current_run_cost - current_run_proceeds
            if net_invested == 0 and current_holdings > 0:
                # If no trades this run but we have positions, use initial capital as proxy
                net_invested = initial_capital
        
        # Calculate returns based on initial capital (pre-trade P&L)
        total_return = current_value - initial_capital
        total_return_pct = (total_return / initial_capital * 100) if initial_capital > 0 else 0.0
        
        # Unrealized P&L is the gain/loss on current holdings vs cost basis
        unrealized_pnl = current_holdings - net_invested
        
        # Realized P&L is cumulative from all historical trades (excluding current run)
        realized_pnl = cumulative_realized_pnl
        
        return PortfolioPerformance(
            portfolio_name=portfolio_name,
            initial_capital=initial_capital,
            current_value=current_value,  # Includes cash balance
            total_return=total_return,
            total_return_pct=total_return_pct,
            total_cost=initial_capital,  # Total cost = total initial investment
            total_proceeds=current_run_proceeds,  # Proceeds from current run (for reference, not used in P&L)
            net_invested=net_invested,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,  # Cumulative from all historical trades
        )
    
    def _create_multi_portfolio_summary(
        self,
        portfolio_summaries: Dict[str, TradeSummary],
        performances: Dict[str, PortfolioPerformance]
    ) -> MultiPortfolioSummary:
        """Create multi-portfolio summary with aggregate metrics."""
        total_initial_capital = sum(p.initial_capital for p in performances.values())
        total_current_value = sum(p.current_value for p in performances.values())
        # Total Net Invested = Total Initial Capital (total amount initially invested)
        total_net_invested = total_initial_capital
        # Calculate returns based on initial capital
        overall_return = total_current_value - total_initial_capital
        overall_return_pct = (overall_return / total_initial_capital * 100) if total_initial_capital > 0 else 0.0
        
        return MultiPortfolioSummary(
            portfolios=portfolio_summaries,
            performances=performances,
            total_initial_capital=total_initial_capital,
            total_current_value=total_current_value,
            total_net_invested=total_net_invested,
            overall_return=overall_return,
            overall_return_pct=overall_return_pct,
        )

    def _send_completion_email(self):
        """Send email notification after successful daily completion."""
        if not self.email_notifier or not self.config.email.recipient:
            return

        if not self.persistence_manager:
            return

        # Gather results from today's execution runs
        portfolio_results = {}
        for portfolio_name in self.rebalancers.keys():
            run = self.persistence_manager.get_execution_run(portfolio_name)
            if run:
                portfolio_results[portfolio_name] = run

        if not portfolio_results:
            return

        try:
            self.email_notifier.send_trades_finalized_email(
                recipient=self.config.email.recipient,
                portfolio_results=portfolio_results,
            )
            logger.info("Daily completion email sent")
        except Exception as e:
            logger.error(f"Error sending completion email: {e}")

    def run(self):
        """Run the trading bot."""
        self.initialize()
        
        logger.info("=" * 60)
        logger.info("Trading Bot Started")
        logger.info(f"Broker: {self.config.broker.broker_type}")
        logger.info(f"Scheduler Mode: {self.config.scheduler.mode}")
        logger.info(f"Email: {'Enabled' if self.email_notifier else 'Disabled'}")
        logger.info(f"Persistence: {'Enabled' if self.config.persistence.enabled and self.config.persistence.is_configured() else 'Disabled'}")
        logger.info("=" * 60)
        
        if self.config.scheduler.mode == "internal":
            # Run with internal scheduler
            try:
                self.scheduler.start()
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                self.shutdown()
        else:
            # Run with webhook endpoint
            try:
                self.app.run(
                    host="0.0.0.0",
                    port=self.config.scheduler.webhook_port,
                    debug=False,
                )
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                self.shutdown()
    
    def shutdown(self):
        """Shutdown the trading bot."""
        logger.info("Shutting down trading bot...")
        if self.scheduler:
            self.scheduler.shutdown()


def main():
    """Main entry point."""
    bot = TradingBot()
    bot.run()


if __name__ == "__main__":
    main()
