"""Configuration management for the trading bot."""

import os
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

# Load environment variables from .env file
load_dotenv()


class BrokerConfig(BaseModel):
    """Broker configuration."""

    broker_type: str = Field(default="alpaca", description="Broker type: 'alpaca', 'robinhood', or 'webull'")
    
    # Alpaca credentials
    alpaca_api_key: Optional[str] = None
    alpaca_api_secret: Optional[str] = None
    alpaca_base_url: str = Field(default="https://paper-api.alpaca.markets", description="Alpaca base URL")
    
    # Robinhood credentials
    robinhood_username: Optional[str] = None
    robinhood_password: Optional[str] = None
    robinhood_mfa_code: Optional[str] = None
    
    # Webull credentials (official OpenAPI SDK)
    webull_app_key: Optional[str] = None
    webull_app_secret: Optional[str] = None
    webull_account_id: Optional[str] = Field(default=None, description="Webull account ID (optional, will use first account if not provided)")
    webull_region: str = Field(default="US", description="Webull region: US, HK, or JP")

    @field_validator("broker_type")
    @classmethod
    def validate_broker_type(cls, v: str) -> str:
        """Validate broker type."""
        v_lower = v.lower()
        valid_types = ["alpaca", "robinhood", "webull"]
        if v_lower not in valid_types:
            raise ValueError(f"Invalid broker type: {v}. Must be one of: {', '.join(valid_types)}")
        return v_lower

    def validate_broker_credentials(self) -> None:
        """Validate that required broker credentials are present."""
        if self.broker_type == "alpaca":
            if not self.alpaca_api_key or not self.alpaca_api_secret:
                raise ValueError("Alpaca API key and secret are required when BROKER_TYPE=alpaca")
        elif self.broker_type == "robinhood":
            if not self.robinhood_username or not self.robinhood_password:
                raise ValueError("Robinhood username and password are required when BROKER_TYPE=robinhood")
        elif self.broker_type == "webull":
            if not self.webull_app_key or not self.webull_app_secret:
                raise ValueError("Webull App Key and App Secret are required when BROKER_TYPE=webull. Get them from developer.webull.com")


class EmailConfig(BaseModel):
    """Email notification configuration."""

    enabled: bool = Field(default=True, description="Enable email notifications")
    recipient: Optional[str] = Field(default=None, description="Recipient email address")
    provider: str = Field(default="smtp", description="Email provider: 'smtp', 'sendgrid', or 'ses'")
    
    # SMTP settings
    smtp_host: Optional[str] = None
    smtp_port: int = Field(default=587, description="SMTP port")
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[str] = None
    
    # SendGrid settings
    sendgrid_api_key: Optional[str] = None
    sendgrid_from_email: Optional[str] = None
    
    # AWS SES settings
    aws_region: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    ses_from_email: Optional[str] = None

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """Validate email provider."""
        v_lower = v.lower()
        if v_lower not in ["smtp", "sendgrid", "ses"]:
            raise ValueError(f"Invalid email provider: {v}. Must be 'smtp', 'sendgrid', or 'ses'")
        return v_lower

    def validate_email_credentials(self) -> None:
        """Validate that required email credentials are present."""
        if not self.enabled:
            return
        
        if not self.recipient:
            raise ValueError("EMAIL_RECIPIENT is required when email is enabled")
        
        if self.provider == "smtp":
            if not all([self.smtp_host, self.smtp_username, self.smtp_password, self.smtp_from_email]):
                raise ValueError("SMTP credentials are required when EMAIL_PROVIDER=smtp")
        elif self.provider == "sendgrid":
            if not self.sendgrid_api_key or not self.sendgrid_from_email:
                raise ValueError("SendGrid API key and from email are required when EMAIL_PROVIDER=sendgrid")
        elif self.provider == "ses":
            if not all([self.aws_region, self.aws_access_key_id, self.aws_secret_access_key, self.ses_from_email]):
                raise ValueError("AWS SES credentials are required when EMAIL_PROVIDER=ses")


class SchedulerConfig(BaseModel):
    """Scheduler configuration."""

    mode: str = Field(default="internal", description="Scheduler mode: 'internal' or 'external'")
    cron_schedule: str = Field(default="0 0 * * 1", description="Cron expression for internal scheduler (Mondays at midnight)")
    webhook_port: int = Field(default=8080, description="Port for webhook endpoint")
    webhook_secret: Optional[str] = Field(default=None, description="Optional secret token for webhook authentication")

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """Validate scheduler mode."""
        v_lower = v.lower()
        if v_lower not in ["internal", "external"]:
            raise ValueError(f"Invalid scheduler mode: {v}. Must be 'internal' or 'external'")
        return v_lower


class Config(BaseModel):
    """Main configuration class."""

    # Leaderboard API
    leaderboard_api_url: str = Field(description="Leaderboard API endpoint")
    leaderboard_api_token: str = Field(description="Leaderboard API authentication token")
    
    # Trading
    initial_capital: float = Field(default=10000.0, description="Initial capital for portfolio allocation")
    
    # Broker configuration
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    
    # Email configuration
    email: EmailConfig = Field(default_factory=EmailConfig)
    
    # Scheduler configuration
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)

    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables."""
        broker_config = BrokerConfig(
            broker_type=os.getenv("BROKER_TYPE", "alpaca"),
            alpaca_api_key=os.getenv("ALPACA_API_KEY"),
            alpaca_api_secret=os.getenv("ALPACA_API_SECRET"),
            alpaca_base_url=os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"),
            robinhood_username=os.getenv("ROBINHOOD_USERNAME"),
            robinhood_password=os.getenv("ROBINHOOD_PASSWORD"),
            robinhood_mfa_code=os.getenv("ROBINHOOD_MFA_CODE"),
            webull_app_key=os.getenv("WEBULL_APP_KEY"),
            webull_app_secret=os.getenv("WEBULL_APP_SECRET"),
            webull_account_id=os.getenv("WEBULL_ACCOUNT_ID"),
            webull_region=os.getenv("WEBULL_REGION", "US"),
        )
        
        # Handle SMTP_PORT with proper default for empty strings
        smtp_port_str = os.getenv("SMTP_PORT", "587")
        smtp_port = int(smtp_port_str) if smtp_port_str and smtp_port_str.strip() else 587
        
        email_config = EmailConfig(
            enabled=os.getenv("EMAIL_ENABLED", "true").lower() == "true",
            recipient=os.getenv("EMAIL_RECIPIENT"),
            provider=os.getenv("EMAIL_PROVIDER", "smtp"),
            smtp_host=os.getenv("SMTP_HOST"),
            smtp_port=smtp_port,
            smtp_username=os.getenv("SMTP_USERNAME"),
            smtp_password=os.getenv("SMTP_PASSWORD"),
            smtp_from_email=os.getenv("SMTP_FROM_EMAIL"),
            sendgrid_api_key=os.getenv("SENDGRID_API_KEY"),
            sendgrid_from_email=os.getenv("SENDGRID_FROM_EMAIL"),
            aws_region=os.getenv("AWS_REGION"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            ses_from_email=os.getenv("SES_FROM_EMAIL"),
        )
        
        # Handle WEBHOOK_PORT with proper default for empty strings
        webhook_port_str = os.getenv("WEBHOOK_PORT", "8080")
        webhook_port = int(webhook_port_str) if webhook_port_str and webhook_port_str.strip() else 8080
        
        scheduler_config = SchedulerConfig(
            mode=os.getenv("SCHEDULER_MODE", "internal"),
            cron_schedule=os.getenv("CRON_SCHEDULE", "0 0 * * 1"),
            webhook_port=webhook_port,
            webhook_secret=os.getenv("WEBHOOK_SECRET"),
        )
        
        # Handle INITIAL_CAPITAL with proper default for empty strings
        initial_capital_str = os.getenv("INITIAL_CAPITAL", "10000.0")
        initial_capital = float(initial_capital_str) if initial_capital_str and initial_capital_str.strip() else 10000.0
        
        config = cls(
            leaderboard_api_url=os.getenv("LEADERBOARD_API_URL", ""),
            leaderboard_api_token=os.getenv("LEADERBOARD_API_TOKEN", ""),
            initial_capital=initial_capital,
            broker=broker_config,
            email=email_config,
            scheduler=scheduler_config,
        )
        
        # Validate required fields
        if not config.leaderboard_api_url:
            raise ValueError("LEADERBOARD_API_URL is required")
        if not config.leaderboard_api_token:
            raise ValueError("LEADERBOARD_API_TOKEN is required")
        
        # Validate broker and email credentials
        config.broker.validate_broker_credentials()
        config.email.validate_email_credentials()
        
        return config


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config
