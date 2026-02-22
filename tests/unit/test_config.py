"""Unit tests for configuration."""

import os
import pytest
from unittest.mock import patch
from src.config.config import Config, BrokerConfig, EmailConfig, SchedulerConfig


def test_broker_config_validation():
    """Test broker configuration validation."""
    # Valid Alpaca config
    config = BrokerConfig(
        broker_type="alpaca",
        alpaca_api_key="key",
        alpaca_api_secret="secret",
    )
    config.validate_broker_credentials()  # Should not raise
    
    # Invalid Alpaca config
    config = BrokerConfig(broker_type="alpaca")
    with pytest.raises(ValueError, match="Alpaca API key"):
        config.validate_broker_credentials()
    
    # Valid Robinhood config
    config = BrokerConfig(
        broker_type="robinhood",
        robinhood_username="user",
        robinhood_password="pass",
    )
    config.validate_broker_credentials()  # Should not raise
    
    # Valid Tradier config
    config = BrokerConfig(
        broker_type="tradier",
        tradier_access_token="token",
        tradier_account_id="account123",
    )
    config.validate_broker_credentials()  # Should not raise
    
    # Invalid Tradier config
    config = BrokerConfig(broker_type="tradier")
    with pytest.raises(ValueError, match="Tradier access token"):
        config.validate_broker_credentials()
    
    # Invalid broker type
    with pytest.raises(ValueError, match="Invalid broker type"):
        BrokerConfig(broker_type="invalid")


def test_email_config_validation():
    """Test email configuration validation."""
    # Disabled email should not require credentials
    config = EmailConfig(enabled=False)
    config.validate_email_credentials()  # Should not raise
    
    # Enabled email without recipient
    config = EmailConfig(enabled=True)
    with pytest.raises(ValueError, match="EMAIL_RECIPIENT"):
        config.validate_email_credentials()
    
    # Valid SMTP config
    config = EmailConfig(
        enabled=True,
        recipient="test@example.com",
        provider="smtp",
        smtp_host="smtp.example.com",
        smtp_username="user",
        smtp_password="pass",
        smtp_from_email="from@example.com",
    )
    config.validate_email_credentials()  # Should not raise
    
    # Invalid email provider
    with pytest.raises(ValueError, match="Invalid email provider"):
        EmailConfig(provider="invalid")


def test_scheduler_config_validation():
    """Test scheduler configuration validation."""
    # Valid internal mode
    config = SchedulerConfig(mode="internal", cron_schedule="0 0 * * 1")
    assert config.mode == "internal"
    
    # Valid external mode
    config = SchedulerConfig(mode="external", webhook_port=8080)
    assert config.mode == "external"
    
    # Invalid mode
    with pytest.raises(ValueError, match="Invalid scheduler mode"):
        SchedulerConfig(mode="invalid")


@patch.dict(os.environ, {
    "LEADERBOARD_API_URL": "https://api.example.com",
    "LEADERBOARD_API_TOKEN": "token123",
    "BROKER_TYPE": "alpaca",
    "ALPACA_API_KEY": "key",
    "ALPACA_API_SECRET": "secret",
})
def test_config_from_env():
    """Test configuration loading from environment variables."""
    config = Config.from_env()
    
    assert config.leaderboard_api_url == "https://api.example.com"
    assert config.leaderboard_api_token == "token123"
    assert config.broker.broker_type == "alpaca"
    assert config.broker.alpaca_api_key == "key"
    assert config.broker.alpaca_api_secret == "secret"


@patch.dict(os.environ, {})
def test_config_missing_required():
    """Test that missing required config raises error."""
    with pytest.raises(ValueError, match="LEADERBOARD_API_URL"):
        Config.from_env()
