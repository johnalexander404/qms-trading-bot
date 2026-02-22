# Local Setup Guide

Complete guide for setting up and running the QMS Trading Bot locally or with Docker.

## Prerequisites

- Python 3.11+ or Docker
- Broker account (Alpaca, Robinhood, or Webull)
- Leaderboard API access

## Quick Start

### Setup Wizard (Fastest)

The interactive setup wizard generates your `.env` file automatically, with guided prompts and browser links for API key generation:

```bash
python scripts/setup.py
```

The wizard only asks about the broker and services you actually use. It can also auto-create Firebase resources via `gcloud` CLI. Run it and skip to Step 4 below.

### Option 1: Docker (Recommended)

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd qms-trading-bot
   ```

2. **Copy environment file**
   ```bash
   cp .env.example .env
   ```

3. **Configure your settings**
   Edit `.env` with your API keys and credentials (see Configuration section below)

4. **Run with Docker**
   ```bash
   docker-compose up
   ```

### Option 2: Local Python

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd qms-trading-bot
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Copy environment file**
   ```bash
   cp .env.example .env
   ```

5. **Configure your settings**
   Edit `.env` with your API keys and credentials

6. **Run the bot**
   ```bash
   python -m src.main
   ```

## Configuration

All configuration is done via environment variables in your `.env` file.

### Complete Environment Variables Reference

#### Required Variables

**Leaderboard API:**
```bash
LEADERBOARD_API_URL=https://api.example.com/leaderboard
LEADERBOARD_API_TOKEN=your_leaderboard_api_token_here
```

**Broker Type:**
```bash
BROKER_TYPE=alpaca  # Options: alpaca, robinhood, webull
```

#### Broker-Specific Variables

**Alpaca (required if BROKER_TYPE=alpaca):**
```bash
ALPACA_API_KEY=your_alpaca_api_key_here
ALPACA_API_SECRET=your_alpaca_api_secret_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets  # or https://api.alpaca.markets for live
```

**Robinhood (required if BROKER_TYPE=robinhood):**
```bash
ROBINHOOD_USERNAME=your_robinhood_username_here
ROBINHOOD_PASSWORD=your_robinhood_password_here
ROBINHOOD_MFA_CODE=123456  # Optional: Only if 2FA is enabled
```

**Webull (required if BROKER_TYPE=webull):**
```bash
WEBULL_APP_KEY=your_webull_app_key_here
WEBULL_APP_SECRET=your_webull_app_secret_here
WEBULL_ACCOUNT_ID=your_account_id_here  # Optional: Will use first account if not provided
WEBULL_REGION=US  # Optional: US, HK, or JP (default: US)
```

#### Trading Configuration

```bash
INITIAL_CAPITAL=10000.0  # Initial capital amount for portfolio allocation (in USD)
```

#### Scheduler Configuration

```bash
SCHEDULER_MODE=internal  # Options: internal (default) or external
CRON_SCHEDULE=0 0 * * 1  # Cron expression (default: Mondays at midnight)
WEBHOOK_PORT=8080  # Only used if SCHEDULER_MODE=external
WEBHOOK_SECRET=your_webhook_secret_here  # Optional: For webhook authentication
```

#### Email Configuration

**Basic Email Settings:**
```bash
EMAIL_ENABLED=true  # Enable/disable email notifications
EMAIL_RECIPIENT=your_email@example.com  # Recipient email address
EMAIL_PROVIDER=smtp  # Options: smtp, sendgrid, ses
```

**SMTP Configuration (required if EMAIL_PROVIDER=smtp):**
```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password_here
SMTP_FROM_EMAIL=your_email@gmail.com
```

**SendGrid Configuration (required if EMAIL_PROVIDER=sendgrid):**
```bash
SENDGRID_API_KEY=your_sendgrid_api_key_here
SENDGRID_FROM_EMAIL=your_verified_email@example.com
```

**AWS SES Configuration (required if EMAIL_PROVIDER=ses):**
```bash
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_aws_access_key_here
AWS_SECRET_ACCESS_KEY=your_aws_secret_key_here
SES_FROM_EMAIL=your_verified_email@example.com
```

#### Persistence Configuration (Optional)

```bash
PERSISTENCE_ENABLED=true  # Optional: Auto-enabled if Firebase credentials are configured
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_CREDENTIALS_PATH=/path/to/firebase-service-account.json  # For local development
# OR
FIREBASE_CREDENTIALS_JSON={"type":"service_account","project_id":"...","private_key":"..."}  # JSON string
```

#### Multiple Portfolio Configuration (Optional)

**Default Behavior:**
If no portfolio configuration is provided, the bot **defaults to trading SP400** (S&P 400 MidCap) with the `INITIAL_CAPITAL` amount.

**Method 1: Environment Variables**
```bash
TRADE_INDICES=SP400,SP500,SP600  # Comma-separated list of index names
INITIAL_CAPITAL_SP400=50000
INITIAL_CAPITAL_SP500=100000
INITIAL_CAPITAL_SP600=30000
```

**Initial Capital Behavior:**
- If `INITIAL_CAPITAL_{INDEX_NAME}` is provided (e.g., `INITIAL_CAPITAL_SP400`), that portfolio uses that specific amount
- If `INITIAL_CAPITAL_{INDEX_NAME}` is **not** provided, the portfolio uses the `INITIAL_CAPITAL` value (defaults to `10000.0`)
- Example: If `TRADE_INDICES=SP400,SP500` is set but only `INITIAL_CAPITAL_SP400=50000` is provided, then:
  - SP400 portfolio uses `50000`
  - SP500 portfolio uses `INITIAL_CAPITAL` value (or `10000.0` if not set)

**Method 2: JSON Configuration**
```bash
PORTFOLIO_CONFIG='[{"portfolio_name":"SP400","index_id":"13","initial_capital":50000,"enabled":true}]'
```

**Note:** To explicitly configure a single SP400 portfolio, you can either:
- Leave `TRADE_INDICES` unset (defaults to SP400)
- Set `TRADE_INDICES=SP400`

#### Security Configuration

```bash
MASK_FINANCIAL_AMOUNTS=true  # Optional: Mask financial amounts in logs (default: true)
```

### Quick Configuration Example

Here's a minimal `.env` file example:

```bash
# Required
LEADERBOARD_API_URL=https://api.example.com/leaderboard
LEADERBOARD_API_TOKEN=your_token
BROKER_TYPE=alpaca
ALPACA_API_KEY=your_key
ALPACA_API_SECRET=your_secret

# Optional but recommended
EMAIL_ENABLED=true
EMAIL_RECIPIENT=your_email@example.com
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=your_email@gmail.com
```

📖 **Gmail Setup:** See [Gmail App Password Setup Guide](GMAIL_APP_PASSWORD_SETUP.md) for detailed instructions

### Broker Configuration

See the [Complete Environment Variables Reference](#complete-environment-variables-reference) above for all broker variables.

### Email Configuration

See the [Complete Environment Variables Reference](#complete-environment-variables-reference) above for all email variables.

### Scheduler Configuration

See the [Complete Environment Variables Reference](#complete-environment-variables-reference) above for all scheduler variables.

### Persistence Configuration (Optional)

Enable Firebase Firestore to track bot trades and detect external sales:

#### Step 1: Set up Firebase Project

1. **Create Firebase Project:**
   - Go to [Firebase Console](https://console.firebase.google.com/)
   - Click "Add project" or select existing project
   - Note your **Project ID** (shown in Project Settings)

2. **Create Firestore Database:**
   - In Firebase Console, click **"Firestore Database"** in the left sidebar
   - Click **"Create database"**
   - Choose **"Start in test mode"** (or production mode with your security rules)
   - Select a location (e.g., `us-central1`)
   - Click **"Enable"**

3. **Get Service Account Credentials:**
   - Go to **Project Settings** (gear icon) → **Service Accounts**
   - Click **"Generate New Private Key"**
   - Download the JSON file (e.g., `firebase-service-account.json`)

#### Step 2: Verify Setup

Run the verification script to verify Firebase connectivity:

```bash
python scripts/verify-firebase.py
```

This script will:
- Verify Firebase credentials are valid
- Test Firestore connection
- Verify collections can be created
- Test read/write operations

#### Step 3: Configure Environment Variables

Add to your `.env` file (see [Complete Environment Variables Reference](#complete-environment-variables-reference) above):
```bash
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_CREDENTIALS_PATH=/path/to/firebase-service-account.json
PERSISTENCE_ENABLED=true  # Optional - auto-enables if credentials are set
```

**⚠️ Security Note:** 
- **Never commit** the Firebase JSON file to git
- Add `firebase-service-account.json` to `.gitignore` if storing locally

📖 **Detailed Scenarios:** See [Persistence Scenarios Guide](PERSISTENCE_SCENARIOS.md) for examples

### Multiple Portfolio Trading

**Default Behavior:**
If no portfolio configuration is provided, the bot **defaults to trading SP400** (S&P 400 MidCap) with the `INITIAL_CAPITAL` amount. You can start using the bot immediately without any portfolio configuration.

**⚠️ Important:** Persistence **must** be enabled when using multiple portfolios. The bot will raise an error if multiple portfolios are configured without persistence.

See the [Complete Environment Variables Reference](#complete-environment-variables-reference) above for all multiple portfolio variables.

**Available Indices:**
- **SP400** (indexId: 13) - S&P 400 MidCap (default)
- **SP500** (indexId: 9) - S&P 500 LargeCap
- **SP600** (indexId: 12) - S&P 600 SmallCap
- **NDX** (indexId: 8) - NASDAQ-100

## Testing

Run unit tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=src --cov-report=html
```

## Troubleshooting

### Broker Connection Issues
- Verify API keys/credentials are correct
- Check broker account status
- Ensure paper trading is enabled for testing

### Email Not Sending
- Verify email provider credentials
- Check email provider service status
- Review logs for specific error messages

### Scheduler Not Running
- Check cron expression format
- Verify scheduler mode (internal vs external)
- Review application logs

### Firebase Connection Issues
- Verify `FIREBASE_CREDENTIALS_PATH` points to correct file
- Check Firebase project ID is correct
- Ensure Firestore database is created
- Run `python scripts/verify-firebase.py` to diagnose issues

## Next Steps

- 📖 See [GitHub Actions Setup](GITHUB_ACTIONS_DEPLOYMENT.md) for cloud deployment
- 📖 See [Web Hosting Setup](WEB_HOSTING_SETUP.md) for AWS/GCP/Azure deployment
- 📖 See [Persistence Scenarios](PERSISTENCE_SCENARIOS.md) for detailed persistence examples
