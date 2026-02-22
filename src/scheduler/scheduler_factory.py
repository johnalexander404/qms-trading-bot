"""Factory for creating scheduler instances."""

import logging
from typing import Callable, Optional

from ..config import get_config
from .cron_scheduler import CronScheduler

logger = logging.getLogger(__name__)


def create_scheduler(job_function: Callable) -> Optional[CronScheduler]:
    """
    Create a scheduler instance based on configuration.
    
    Args:
        job_function: Function to execute on schedule
        
    Returns:
        CronScheduler instance if internal mode, None if external mode
    """
    config = get_config()
    
    if config.scheduler.mode == "internal":
        return CronScheduler(
            cron_expression=config.scheduler.cron_schedule,
            job_function=job_function,
            timezone=config.scheduler.cron_timezone,
        )
    else:
        logger.info("External scheduler mode - no internal scheduler created")
        return None
