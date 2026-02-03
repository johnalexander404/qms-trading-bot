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
    "EMAIL_ENABLED": "false",
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


class TestBrokerConfigExtended:
    """Extended tests for broker configuration."""

    def test_webull_config_validation(self):
        """Test Webull configuration validation."""
        config = BrokerConfig(
            broker_type="webull",
            webull_app_key="key",
            webull_app_secret="secret",
        )
        config.validate_broker_credentials()  # Should not raise

    def test_webull_missing_credentials(self):
        """Test Webull missing credentials raises error."""
        config = BrokerConfig(broker_type="webull")
        with pytest.raises(ValueError, match="Webull App Key"):
            config.validate_broker_credentials()

    def test_broker_type_case_insensitive(self):
        """Test broker type is case insensitive."""
        config = BrokerConfig(broker_type="ALPACA")
        assert config.broker_type == "alpaca"

    def test_alpaca_base_url_default(self):
        """Test Alpaca base URL defaults to paper."""
        config = BrokerConfig(broker_type="alpaca")
        assert "paper" in config.alpaca_base_url


class TestEmailConfigExtended:
    """Extended tests for email configuration."""

    def test_sendgrid_validation(self):
        """Test SendGrid configuration validation."""
        config = EmailConfig(
            enabled=True,
            recipient="test@example.com",
            provider="sendgrid",
            sendgrid_api_key="key",
            sendgrid_from_email="from@example.com",
        )
        config.validate_email_credentials()  # Should not raise

    def test_sendgrid_missing_credentials(self):
        """Test SendGrid missing credentials raises error."""
        config = EmailConfig(
            enabled=True,
            recipient="test@example.com",
            provider="sendgrid",
        )
        with pytest.raises(ValueError, match="SendGrid"):
            config.validate_email_credentials()

    def test_ses_validation(self):
        """Test SES configuration validation."""
        config = EmailConfig(
            enabled=True,
            recipient="test@example.com",
            provider="ses",
            aws_region="us-east-1",
            aws_access_key_id="key",
            aws_secret_access_key="secret",
            ses_from_email="from@example.com",
        )
        config.validate_email_credentials()  # Should not raise

    def test_ses_missing_credentials(self):
        """Test SES missing credentials raises error."""
        config = EmailConfig(
            enabled=True,
            recipient="test@example.com",
            provider="ses",
        )
        with pytest.raises(ValueError, match="AWS SES"):
            config.validate_email_credentials()

    def test_smtp_missing_credentials(self):
        """Test SMTP missing credentials raises error."""
        config = EmailConfig(
            enabled=True,
            recipient="test@example.com",
            provider="smtp",
        )
        with pytest.raises(ValueError, match="SMTP credentials"):
            config.validate_email_credentials()


class TestSchedulerConfigExtended:
    """Extended tests for scheduler configuration."""

    def test_internal_mode_requires_cron(self):
        """Test internal mode configuration."""
        config = SchedulerConfig(mode="internal")
        assert config.mode == "internal"

    def test_external_mode_with_port(self):
        """Test external mode with custom port."""
        config = SchedulerConfig(mode="external", webhook_port=9000)
        assert config.webhook_port == 9000


class TestConfigWithPortfolios:
    """Tests for portfolio configuration."""

    @patch.dict(os.environ, {
        "LEADERBOARD_API_URL": "https://api.example.com",
        "LEADERBOARD_API_TOKEN": "token123",
        "BROKER_TYPE": "alpaca",
        "ALPACA_API_KEY": "key",
        "ALPACA_API_SECRET": "secret",
        "EMAIL_ENABLED": "false",
        "DEFAULT_STOCKCOUNT": "10",
        "DEFAULT_SLACK": "3",
    })
    def test_default_stockcount_and_slack(self):
        """Test default stockcount and slack values."""
        config = Config.from_env()
        assert config.default_stockcount == 10
        assert config.default_slack == 3

    @patch.dict(os.environ, {
        "LEADERBOARD_API_URL": "https://api.example.com",
        "LEADERBOARD_API_TOKEN": "token123",
        "BROKER_TYPE": "alpaca",
        "ALPACA_API_KEY": "key",
        "ALPACA_API_SECRET": "secret",
        "EMAIL_ENABLED": "false",
        "INITIAL_CAPITAL": "25000",
    })
    def test_initial_capital_from_env(self):
        """Test initial capital configuration."""
        config = Config.from_env()
        assert config.initial_capital == 25000.0

    @patch.dict(os.environ, {
        "LEADERBOARD_API_URL": "https://api.example.com",
        "LEADERBOARD_API_TOKEN": "token123",
        "BROKER_TYPE": "alpaca",
        "ALPACA_API_KEY": "key",
        "ALPACA_API_SECRET": "secret",
        "EMAIL_ENABLED": "false",
        "ALPACA_BASE_URL": "https://api.alpaca.markets",
    })
    def test_live_alpaca_url(self):
        """Test live Alpaca URL configuration."""
        config = Config.from_env()
        assert config.broker.alpaca_base_url == "https://api.alpaca.markets"
