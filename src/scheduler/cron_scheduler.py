"""Internal cron scheduler using APScheduler."""

import logging
from typing import Callable, Optional

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class CronScheduler:
    """Internal cron scheduler for running rebalancing jobs."""
    
    def __init__(self, cron_expression: str, job_function: Callable, timezone: Optional[str] = None):
        """
        Initialize cron scheduler.
        
        Args:
            cron_expression: Cron expression (e.g., "30 9 * * 1" for Mondays at 9:30 AM)
            job_function: Function to execute on schedule
            timezone: Timezone name for cron (e.g. "America/New_York"); cron is interpreted in this zone. If None, uses server local time.
        """
        self.cron_expression = cron_expression
        self.job_function = job_function
        self.timezone = timezone
        self.scheduler = BlockingScheduler()
        self._setup_job()
    
    def _setup_job(self):
        """Set up the scheduled job."""
        # Parse cron expression
        # Format: "minute hour day month day_of_week"
        parts = self.cron_expression.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {self.cron_expression}. Expected format: 'minute hour day month day_of_week'")
        
        minute, hour, day, month, day_of_week = parts
        
        trigger_kw = dict(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
        )
        if self.timezone and self.timezone.strip():
            try:
                trigger_kw["timezone"] = pytz.timezone(self.timezone.strip())
            except pytz.UnknownTimeZoneError:
                logger.warning(f"Unknown timezone {self.timezone!r}, using server local time")
            else:
                logger.info(f"Cron timezone: {self.timezone}")
        
        # Add job to scheduler
        self.scheduler.add_job(
            func=self.job_function,
            trigger=CronTrigger(**trigger_kw),
            id="rebalancing_job",
            name="Portfolio Rebalancing",
            replace_existing=True,
        )
        
        logger.info(f"Scheduled rebalancing job with cron expression: {self.cron_expression}")
    
    def start(self):
        """Start the scheduler."""
        logger.info("Starting internal scheduler...")
        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped")
            self.scheduler.shutdown()
    
    def shutdown(self):
        """Shutdown the scheduler."""
        logger.info("Shutting down scheduler...")
        self.scheduler.shutdown()
