#!/usr/bin/env python3
"""Validate configuration before running the trading bot."""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config


def validate_config():
    """Validate configuration and print results."""
    print("Validating configuration...")
    print("-" * 60)
    
    errors = []
    warnings = []
    
    try:
        config = Config.from_env()
        print("✓ Configuration loaded successfully")
        
        # Validate broker
        print(f"\nBroker: {config.broker.broker_type}")
        if config.broker.broker_type == "alpaca":
            if config.broker.alpaca_api_key and config.broker.alpaca_api_secret:
                print("  ✓ Alpaca credentials configured")
            else:
                errors.append("Alpaca API key and secret are required")
        elif config.broker.broker_type == "robinhood":
            if config.broker.robinhood_username and config.broker.robinhood_password:
                print("  ✓ Robinhood credentials configured")
            else:
                errors.append("Robinhood username and password are required")
        elif config.broker.broker_type == "tradier":
            if config.broker.tradier_access_token and config.broker.tradier_account_id:
                print("  ✓ Tradier credentials configured")
            else:
                errors.append("Tradier access token and account ID are required")
        
        # Validate leaderboard
        print(f"\nLeaderboard API: {config.leaderboard_api_url}")
        if config.leaderboard_api_url and config.leaderboard_api_token:
            print("  ✓ Leaderboard API configured")
        else:
            errors.append("Leaderboard API URL and token are required")
        
        # Validate email
        print(f"\nEmail: {'Enabled' if config.email.enabled else 'Disabled'}")
        if config.email.enabled:
            if config.email.recipient:
                print(f"  Recipient: {config.email.recipient}")
                print(f"  Provider: {config.email.provider}")
                
                if config.email.provider == "smtp":
                    if all([config.email.smtp_host, config.email.smtp_username, 
                           config.email.smtp_password, config.email.smtp_from_email]):
                        print("  ✓ SMTP configured")
                    else:
                        errors.append("SMTP credentials incomplete")
                elif config.email.provider == "sendgrid":
                    if config.email.sendgrid_api_key and config.email.sendgrid_from_email:
                        print("  ✓ SendGrid configured")
                    else:
                        errors.append("SendGrid credentials incomplete")
                elif config.email.provider == "ses":
                    if all([config.email.aws_region, config.email.aws_access_key_id,
                           config.email.aws_secret_access_key, config.email.ses_from_email]):
                        print("  ✓ AWS SES configured")
                    else:
                        errors.append("AWS SES credentials incomplete")
            else:
                warnings.append("Email enabled but no recipient specified")
        
        # Validate scheduler
        print(f"\nScheduler: {config.scheduler.mode}")
        if config.scheduler.mode == "internal":
            print(f"  Cron: {config.scheduler.cron_schedule}")
        else:
            print(f"  Webhook port: {config.scheduler.webhook_port}")
            if not config.scheduler.webhook_secret:
                warnings.append("No webhook secret configured (recommended for production)")
        
        # Trading config
        print(f"\nInitial Capital: ${config.initial_capital:,.2f}")
        
    except ValueError as e:
        errors.append(str(e))
    except Exception as e:
        errors.append(f"Unexpected error: {e}")
    
    # Print results
    print("\n" + "=" * 60)
    if errors:
        print("❌ Configuration Errors:")
        for error in errors:
            print(f"  - {error}")
        print("\nPlease fix the errors above before running the bot.")
        return 1
    
    if warnings:
        print("⚠️  Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
    
    print("✓ Configuration is valid!")
    return 0


if __name__ == "__main__":
    sys.exit(validate_config())
