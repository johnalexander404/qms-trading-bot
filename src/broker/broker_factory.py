"""Factory for creating broker instances."""

import logging
from typing import Optional

from ..config import get_config
from .broker import Broker
from .alpaca import AlpacaBroker
from .robinhood import RobinhoodBroker
from .webull import WebullBroker
from .tradier import TradierBroker

logger = logging.getLogger(__name__)


def create_broker(account_id_override: Optional[str] = None) -> Broker:
    """
    Create a broker instance based on configuration.
    
    Args:
        account_id_override: Optional account ID to use instead of the default.
            When provided, overrides the broker-specific account ID from config
            (e.g. for per-portfolio Tradier sub-accounts).
    
    Returns:
        Broker instance (AlpacaBroker, RobinhoodBroker, WebullBroker, or TradierBroker)
        
    Raises:
        ValueError: If broker type is unsupported or credentials are missing
    """
    config = get_config()
    broker_type = config.broker.broker_type
    
    if broker_type == "alpaca":
        if not config.broker.alpaca_api_key or not config.broker.alpaca_api_secret:
            raise ValueError("Alpaca API key and secret are required")
        
        return AlpacaBroker(
            api_key=config.broker.alpaca_api_key,
            api_secret=config.broker.alpaca_api_secret,
            base_url=config.broker.alpaca_base_url,
        )
    
    elif broker_type == "robinhood":
        if not config.broker.robinhood_username or not config.broker.robinhood_password:
            raise ValueError("Robinhood username and password are required")
        
        return RobinhoodBroker(
            username=config.broker.robinhood_username,
            password=config.broker.robinhood_password,
            mfa_code=config.broker.robinhood_mfa_code,
        )
    
    elif broker_type == "webull":
        if not config.broker.webull_app_key or not config.broker.webull_app_secret:
            raise ValueError("Webull App Key and App Secret are required. Get them from developer.webull.com")
        
        return WebullBroker(
            app_key=config.broker.webull_app_key,
            app_secret=config.broker.webull_app_secret,
            account_id=account_id_override or config.broker.webull_account_id,
            region=config.broker.webull_region,
        )
    
    elif broker_type == "tradier":
        effective_account_id = account_id_override or config.broker.tradier_account_id
        if not config.broker.tradier_access_token or not effective_account_id:
            raise ValueError("Tradier access token and account ID are required")
        
        return TradierBroker(
            access_token=config.broker.tradier_access_token,
            account_id=effective_account_id,
            base_url=config.broker.tradier_base_url,
        )
    
    else:
        raise ValueError(f"Unsupported broker type: {broker_type}")
