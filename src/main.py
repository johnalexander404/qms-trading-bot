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
from .trading import Rebalancer
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
        persistence_manager = None
        if self.config.persistence.enabled:
            try:
                if not self.config.persistence.is_configured():
                    logger.warning("Persistence enabled but credentials not configured. Disabling persistence.")
                else:
                    from .persistence import PersistenceManager
                    persistence_manager = PersistenceManager(
                        project_id=self.config.persistence.project_id,
                        credentials_path=self.config.persistence.credentials_path,
                        credentials_json=self.config.persistence.credentials_json,
                    )
                    logger.info("Initialized persistence manager (Firebase Firestore)")
            except Exception as e:
                logger.warning(f"Failed to initialize persistence manager: {e}. Continuing without persistence.")
                persistence_manager = None
        else:
            logger.info("Persistence disabled")
            persistence_manager = None
        
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
            )
            self.config.portfolios = [default_portfolio]
        
        for portfolio_config in self.config.portfolios:
            if not portfolio_config.enabled:
                continue
            
            rebalancer = Rebalancer(
                broker=self.broker,
                leaderboard_client=self.leaderboard_client,
                initial_capital=portfolio_config.initial_capital,
                portfolio_name=portfolio_config.portfolio_name,
                index_id=portfolio_config.index_id,
                email_notifier=self.email_notifier,
                persistence_manager=persistence_manager,
            )
            self.rebalancers[portfolio_config.portfolio_name] = rebalancer
            logger.info(f"Initialized rebalancer for {portfolio_config.portfolio_name} portfolio (index {portfolio_config.index_id})")
        
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
        Check if current time is 9:30 AM Eastern Time (market open).
        This ensures timezone-aware scheduling works correctly with DST.
        Allows a 5-minute window (9:28-9:33 AM) to account for scheduling delays.
        
        Manual triggers skip day/time check and always return True.
        Scheduled runs must be on Monday at 9:30 AM ET.
        
        Returns:
            True if manual trigger, or if it's around 9:30 AM ET on Monday, False otherwise
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
        
        # Check if it's within 5 minutes of 9:30 AM (9:28-9:33 AM)
        # This accounts for potential GitHub Actions scheduling delays
        current_minute = now_et.hour * 60 + now_et.minute
        target_minute = 9 * 60 + 30  # 9:30 AM
        time_diff = abs(current_minute - target_minute)
        
        if time_diff <= 5:  # Within 5 minutes of 9:30 AM
            logger.info(
                f"Market open time confirmed: {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')} "
                f"(within {time_diff} minutes of 9:30 AM ET)"
            )
            return True
        
        logger.info(
            f"Skipping execution - not market open time. "
            f"Current ET time: {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}, "
            f"Expected: Monday 9:30 AM ET (±5 min)"
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
        
        # Timezone-aware check: only execute at 9:30 AM Eastern Time
        # This handles DST automatically since we check the actual ET time
        # FORCE_RUN=true allows execution at any time
        if not self._is_market_open_time():
            logger.info("Not executing rebalancing - not at market open time (9:30 AM ET)")
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
        
        try:
            # Execute rebalancing for each portfolio
            portfolio_summaries: Dict[str, TradeSummary] = {}
            portfolio_leaderboards: Dict[str, List[str]] = {}
            
            if not self.rebalancers:
                raise ValueError("No portfolios configured. Please set TRADE_INDICES environment variable.")
            
            for portfolio_name, rebalancer in self.rebalancers.items():
                try:
                    logger.info(f"[{portfolio_name}] Starting rebalancing...")
                    summary = rebalancer.rebalance(dry_run=dry_run)
                    portfolio_summaries[portfolio_name] = summary
                    
                    # Get leaderboard symbols for this portfolio
                    current_week_mom_day = self.leaderboard_client._get_previous_sunday()
                    leaderboard_symbols = self.leaderboard_client.get_top_symbols(
                        top_n=5, 
                        mom_day=current_week_mom_day,
                        index_id=rebalancer.index_id
                    )
                    portfolio_leaderboards[portfolio_name] = leaderboard_symbols
                    
                    logger.info(f"[{portfolio_name}] Rebalancing {'simulation' if dry_run else 'execution'} completed. Portfolio value: ${summary.portfolio_value:.2f}")
                except Exception as portfolio_error:
                    logger.error(f"[{portfolio_name}] Error during rebalancing: {portfolio_error}")
                    # Continue with other portfolios
            
            # Calculate performance metrics for each portfolio
            performances: Dict[str, PortfolioPerformance] = {}
            for portfolio_name, summary in portfolio_summaries.items():
                performance = self._calculate_portfolio_performance(portfolio_name, summary)
                performances[portfolio_name] = performance
            
            # Create multi-portfolio summary
            if len(portfolio_summaries) > 1:
                multi_summary = self._create_multi_portfolio_summary(portfolio_summaries, performances)
                
                # Send email notification if enabled (only in real execution mode)
                if not dry_run and self.email_notifier and self.config.email.recipient:
                    try:
                        self.email_notifier.send_trade_summary(
                            recipient=self.config.email.recipient,
                            trade_summary=multi_summary,
                            portfolio_leaderboards=portfolio_leaderboards,
                        )
                    except Exception as email_error:
                        logger.error(f"Error sending email notification: {email_error}")
                
                return multi_summary
            else:
                # Single portfolio - return single summary
                if not portfolio_summaries:
                    raise ValueError("No portfolio summaries generated. All portfolios may have failed during rebalancing.")
                
                summary = list(portfolio_summaries.values())[0]
                
                # Send email notification if enabled (only in real execution mode)
                if not dry_run and self.email_notifier and self.config.email.recipient:
                    try:
                        leaderboard_symbols = list(portfolio_leaderboards.values())[0] if portfolio_leaderboards else []
                        self.email_notifier.send_trade_summary(
                            recipient=self.config.email.recipient,
                            trade_summary=summary,
                            leaderboard_symbols=leaderboard_symbols,
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
        trade_summary: TradeSummary
    ) -> PortfolioPerformance:
        """Calculate performance metrics for a portfolio."""
        initial_capital = trade_summary.initial_capital
        current_value = trade_summary.portfolio_value
        total_cost = trade_summary.total_cost
        total_proceeds = trade_summary.total_proceeds
        
        net_invested = total_cost - total_proceeds
        # Calculate returns based on invested capital (not including cash)
        total_return = current_value - net_invested
        total_return_pct = (total_return / net_invested * 100) if net_invested > 0 else 0.0
        unrealized_pnl = current_value - net_invested
        realized_pnl = total_proceeds - total_cost
        
        return PortfolioPerformance(
            portfolio_name=portfolio_name,
            initial_capital=initial_capital,
            current_value=current_value,
            total_return=total_return,
            total_return_pct=total_return_pct,
            total_cost=total_cost,
            total_proceeds=total_proceeds,
            net_invested=net_invested,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
        )
    
    def _create_multi_portfolio_summary(
        self,
        portfolio_summaries: Dict[str, TradeSummary],
        performances: Dict[str, PortfolioPerformance]
    ) -> MultiPortfolioSummary:
        """Create multi-portfolio summary with aggregate metrics."""
        total_initial_capital = sum(p.initial_capital for p in performances.values())
        total_current_value = sum(p.current_value for p in performances.values())
        total_net_invested = sum(p.net_invested for p in performances.values())
        # Calculate returns based on invested capital (not including cash)
        overall_return = total_current_value - total_net_invested
        overall_return_pct = (overall_return / total_net_invested * 100) if total_net_invested > 0 else 0.0
        
        return MultiPortfolioSummary(
            portfolios=portfolio_summaries,
            performances=performances,
            total_initial_capital=total_initial_capital,
            total_current_value=total_current_value,
            total_net_invested=total_net_invested,
            overall_return=overall_return,
            overall_return_pct=overall_return_pct,
        )
    
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
