"""Configuration management for the trading bot."""

import os
import json
from typing import Optional, List
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

# Load environment variables from .env file
load_dotenv()

# Index name to ID mapping
INDEX_NAME_TO_ID = {
    "SP400": "13",
    "SP500": "9",
    "SP600": "12",
    "NDX": "8"
}


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


class PersistenceConfig(BaseModel):
    """Firebase Firestore persistence configuration."""

    enabled: bool = Field(default=False, description="Enable persistence tracking")
    project_id: Optional[str] = Field(default=None, description="Firebase project ID")
    credentials_path: Optional[str] = Field(default=None, description="Path to Firebase service account JSON file")
    credentials_json: Optional[str] = Field(default=None, description="Firebase service account JSON as string (alternative to credentials_path)")

    def is_configured(self) -> bool:
        """Check if Firebase credentials are configured."""
        return bool(self.project_id and (self.credentials_path or self.credentials_json))


class PortfolioConfig(BaseModel):
    """Portfolio configuration for multi-portfolio support."""

    portfolio_name: str = Field(description="Portfolio name (e.g., 'SP400', 'SP500')")
    index_id: str = Field(description="Internal API index ID (e.g., '13', '9')")
    initial_capital: float = Field(description="Initial capital for this portfolio")
    enabled: bool = Field(default=True, description="Whether this portfolio is enabled")
    stockcount: int = Field(default=5, description="Number of stocks to hold in portfolio")
    slack: int = Field(default=0, description="Position buffer - sell when rank > stockcount + slack")


class Config(BaseModel):
    """Main configuration class."""

    # Leaderboard API
    leaderboard_api_url: str = Field(description="Leaderboard API endpoint")
    leaderboard_api_token: str = Field(description="Leaderboard API authentication token")

    # Trading
    initial_capital: float = Field(default=10000.0, description="Initial capital for portfolio allocation")

    # Multi-portfolio configuration
    portfolios: List[PortfolioConfig] = Field(default_factory=list, description="List of portfolio configurations")

    # Default portfolio parameters (used when not specified per-portfolio)
    default_stockcount: int = Field(default=5, description="Default number of stocks per portfolio")
    default_slack: int = Field(default=0, description="Default position slack for all portfolios")

    # Broker configuration
    broker: BrokerConfig = Field(default_factory=BrokerConfig)

    # Email configuration
    email: EmailConfig = Field(default_factory=EmailConfig)

    # Scheduler configuration
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)

    # Persistence configuration
    persistence: PersistenceConfig = Field(default_factory=PersistenceConfig)

    # Security
    mask_financial_amounts: bool = Field(default=True, description="Mask financial amounts in logs")

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
        
        # Persistence configuration - auto-enable if credentials are present
        persistence_enabled_env = os.getenv("PERSISTENCE_ENABLED", "").lower()
        persistence_enabled = persistence_enabled_env == "true"
        persistence_project_id = os.getenv("FIREBASE_PROJECT_ID")
        persistence_credentials_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
        persistence_credentials_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
        
        # Auto-enable if credentials are configured (even if PERSISTENCE_ENABLED is not explicitly true)
        if persistence_project_id and (persistence_credentials_path or persistence_credentials_json):
            persistence_enabled = True
        
        persistence_config = PersistenceConfig(
            enabled=persistence_enabled,
            project_id=persistence_project_id,
            credentials_path=persistence_credentials_path,
            credentials_json=persistence_credentials_json,
        )
        
        # Handle INITIAL_CAPITAL with proper default for empty strings
        initial_capital_str = os.getenv("INITIAL_CAPITAL", "10000.0")
        initial_capital = float(initial_capital_str) if initial_capital_str and initial_capital_str.strip() else 10000.0

        # Handle DEFAULT_STOCKCOUNT and DEFAULT_SLACK
        default_stockcount_str = os.getenv("DEFAULT_STOCKCOUNT", "5")
        default_stockcount = int(default_stockcount_str) if default_stockcount_str and default_stockcount_str.strip() else 5

        default_slack_str = os.getenv("DEFAULT_SLACK", "0")
        default_slack = int(default_slack_str) if default_slack_str and default_slack_str.strip() else 0

        # Parse portfolio configuration
        portfolios = cls._parse_portfolio_config(initial_capital)
        
        # Handle MASK_FINANCIAL_AMOUNTS
        mask_financial_amounts_env = os.getenv("MASK_FINANCIAL_AMOUNTS", "true").lower()
        mask_financial_amounts = mask_financial_amounts_env == "true"
        
        config = cls(
            leaderboard_api_url=os.getenv("LEADERBOARD_API_URL", ""),
            leaderboard_api_token=os.getenv("LEADERBOARD_API_TOKEN", ""),
            initial_capital=initial_capital,
            portfolios=portfolios,
            default_stockcount=default_stockcount,
            default_slack=default_slack,
            broker=broker_config,
            email=email_config,
            scheduler=scheduler_config,
            persistence=persistence_config,
            mask_financial_amounts=mask_financial_amounts,
        )
        
        # Validate required fields
        if not config.leaderboard_api_url:
            raise ValueError("LEADERBOARD_API_URL is required")
        if not config.leaderboard_api_token:
            raise ValueError("LEADERBOARD_API_TOKEN is required")
        
        # Validate multiple portfolios require persistence
        if len(config.portfolios) > 1 and not config.persistence.enabled:
            raise ValueError(
                "Multiple portfolios require persistence to be enabled. "
                "Please set PERSISTENCE_ENABLED=true and configure Firebase credentials, "
                "or use a single portfolio (TRADE_INDICES=SP400)."
            )
        
        # Validate broker and email credentials
        config.broker.validate_broker_credentials()
        config.email.validate_email_credentials()
        
        return config
    
    @classmethod
    def _parse_portfolio_config(cls, default_initial_capital: float) -> List[PortfolioConfig]:
        """Parse portfolio configuration from environment variables."""
        portfolios = []
        
        # Check for PORTFOLIO_CONFIG JSON string first
        portfolio_config_json = os.getenv("PORTFOLIO_CONFIG")
        if portfolio_config_json:
            try:
                config_data = json.loads(portfolio_config_json)
                if isinstance(config_data, list):
                    for portfolio_data in config_data:
                        portfolio_name = portfolio_data.get("portfolio_name")
                        index_id = portfolio_data.get("index_id")
                        initial_capital = portfolio_data.get("initial_capital", default_initial_capital)
                        enabled = portfolio_data.get("enabled", True)
                        stockcount = portfolio_data.get("stockcount", 5)
                        slack = portfolio_data.get("slack", 0)

                        if portfolio_name and index_id:
                            if portfolio_name not in INDEX_NAME_TO_ID:
                                raise ValueError(f"Invalid portfolio name: {portfolio_name}. Must be one of: {', '.join(INDEX_NAME_TO_ID.keys())}")
                            portfolios.append(PortfolioConfig(
                                portfolio_name=portfolio_name,
                                index_id=index_id,
                                initial_capital=float(initial_capital),
                                enabled=enabled,
                                stockcount=int(stockcount),
                                slack=int(slack)
                            ))
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid PORTFOLIO_CONFIG JSON: {e}")
        
        # Otherwise, parse from TRADE_INDICES
        if not portfolios:
            trade_indices = os.getenv("TRADE_INDICES", "").strip()
            if trade_indices:
                index_names = [name.strip() for name in trade_indices.split(",") if name.strip()]
            else:
                # Default to single portfolio SP400
                index_names = ["SP400"]
            
            for index_name in index_names:
                if index_name not in INDEX_NAME_TO_ID:
                    raise ValueError(f"Invalid index name: {index_name}. Must be one of: {', '.join(INDEX_NAME_TO_ID.keys())}")

                index_id = INDEX_NAME_TO_ID[index_name]

                # Get initial capital for this portfolio
                capital_env_var = f"INITIAL_CAPITAL_{index_name}"
                capital_str = os.getenv(capital_env_var)
                if capital_str and capital_str.strip():
                    initial_capital = float(capital_str)
                else:
                    initial_capital = default_initial_capital

                # Get per-portfolio stockcount
                stockcount_env_var = f"STOCKCOUNT_{index_name}"
                stockcount_str = os.getenv(stockcount_env_var)
                stockcount = int(stockcount_str) if stockcount_str and stockcount_str.strip() else 5

                # Get per-portfolio slack
                slack_env_var = f"SLACK_{index_name}"
                slack_str = os.getenv(slack_env_var)
                slack = int(slack_str) if slack_str and slack_str.strip() else 0

                portfolios.append(PortfolioConfig(
                    portfolio_name=index_name,
                    index_id=index_id,
                    initial_capital=initial_capital,
                    enabled=True,
                    stockcount=stockcount,
                    slack=slack
                ))
        
        return portfolios


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config
