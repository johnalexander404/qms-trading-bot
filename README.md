# QMS Trading Bot

Automated portfolio rebalancing bot that tracks a leaderboard and automatically rebalances your portfolio to match the top 5 stocks every Monday.

## Features

- **Automated Rebalancing**: Automatically rebalances portfolio to match leaderboard top 5 stocks
- **Multiple Portfolio Support**: Trade multiple indices simultaneously (SP400, SP500, SP600, NDX) with independent capital and tracking
- **Multiple Broker Support**: Works with Alpaca, Robinhood, and Webull
- **Flexible Scheduling**: Internal scheduler or external webhook triggers
- **Email Notifications**: Get notified when trades complete (SMTP, SendGrid, or AWS SES)
- **Trade Persistence**: Optional Firebase Firestore integration to track bot trades and detect external sales
- **Docker Ready**: Containerized for easy deployment
- **Cloud Deployable**: Works with AWS, GCP, and Azure

## Quick Start

Choose your deployment method:

- 🖥️ **[Local Setup Guide](docs/LOCAL_SETUP.md)** - Run locally or with Docker
- ☁️ **[GitHub Actions Setup](docs/GITHUB_ACTIONS_DEPLOYMENT.md)** - Free scheduled runs (recommended for most users)
- 🌐 **[Web Hosting Setup](docs/WEB_HOSTING_SETUP.md)** - Deploy to AWS, GCP, or Azure

### Prerequisites

- Python 3.11+ or Docker
- Broker account (Alpaca, Robinhood, or Webull)
- Leaderboard API access

### Automated Setup (Recommended)

The interactive setup wizard walks you through configuration step-by-step, opens the right URLs for API key generation, and can auto-create Firebase resources:

```bash
python scripts/setup.py
```

It generates your `.env` file with only the settings you need, and can push secrets/variables directly to GitHub Actions (including multi-environment support for paper/live trading):

```bash
python scripts/setup.py --github          # push to GitHub Actions
python scripts/setup.py --github --env    # both .env and GitHub
python scripts/setup.py --github --list   # manage environments
```

📖 See [GitHub Actions Setup](docs/GITHUB_ACTIONS_DEPLOYMENT.md) for environment details.

### Manual Setup

1. **Clone and setup:**
   ```bash
   git clone <repository-url>
   cd qms-trading-bot
   cp .env.example .env
   ```

2. **Configure `.env`** with your API keys and credentials

3. **Run with Docker:**
   ```bash
   docker-compose up
   ```

   **Or run locally:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   python -m src.main
   ```

📖 **For detailed setup instructions, see the [Local Setup Guide](docs/LOCAL_SETUP.md)**

## Configuration

All configuration is done via environment variables. See `.env.example` for all available options.

### Required Configuration

- `LEADERBOARD_API_URL`: Your leaderboard API endpoint
- `LEADERBOARD_API_TOKEN`: Authentication token for leaderboard API
- `BROKER_TYPE`: `alpaca`, `robinhood`, or `webull`

### Broker Configuration

**Alpaca:**
- `ALPACA_API_KEY`: Your Alpaca API key
- `ALPACA_API_SECRET`: Your Alpaca API secret
- `ALPACA_BASE_URL`: `https://paper-api.alpaca.markets` (paper) or `https://api.alpaca.markets` (live)

**Robinhood:**
- `ROBINHOOD_USERNAME`: Your Robinhood username/email
- `ROBINHOOD_PASSWORD`: Your Robinhood password
- `ROBINHOOD_MFA_CODE`: Optional MFA code if 2FA is enabled

**Webull:**
- Uses official Webull OpenAPI SDK - requires App Key/Secret from [developer.webull.com](https://developer.webull.com)
- `WEBULL_APP_KEY`: Your Webull App Key (obtained from developer portal)
- `WEBULL_APP_SECRET`: Your Webull App Secret (obtained from developer portal)
- `WEBULL_ACCOUNT_ID`: Optional account ID (will use first account if not provided)
- `WEBULL_REGION`: Region code (US, HK, or JP) - default: US

📖 **For hosting-specific broker configuration, see:**
- [Local Setup Guide](docs/LOCAL_SETUP.md#broker-configuration)
- [GitHub Actions Setup](docs/GITHUB_ACTIONS_DEPLOYMENT.md#step-1-configure-secrets)
- [Web Hosting Setup](docs/WEB_HOSTING_SETUP.md#configuration)

### Email Configuration

Set `EMAIL_ENABLED=true` and choose a provider:

**SMTP (Gmail, Outlook, etc.):**
- `EMAIL_PROVIDER=smtp`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`
- 📖 **Gmail Setup:** See [Gmail App Password Setup Guide](docs/GMAIL_APP_PASSWORD_SETUP.md) for detailed instructions

**SendGrid:**
- `EMAIL_PROVIDER=sendgrid`
- `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`

**AWS SES:**
- `EMAIL_PROVIDER=ses`
- `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `SES_FROM_EMAIL`

📖 **For hosting-specific email configuration, see:**
- [Local Setup Guide](docs/LOCAL_SETUP.md#email-configuration)
- [GitHub Actions Setup](docs/GITHUB_ACTIONS_DEPLOYMENT.md#email-configuration)
- [Web Hosting Setup](docs/WEB_HOSTING_SETUP.md#email-providers)

### Scheduler Configuration

**Internal Scheduler (Default for local/GitHub Actions):**
- `SCHEDULER_MODE=internal`
- `CRON_SCHEDULE=0 0 * * 1` (Mondays at midnight)

**External Scheduler (Required for cloud deployments):**
- `SCHEDULER_MODE=external`
- `WEBHOOK_PORT=8080`
- `WEBHOOK_SECRET=optional_secret_token` (strongly recommended)

📖 **For hosting-specific scheduler configuration, see:**
- [Local Setup Guide](docs/LOCAL_SETUP.md#scheduler-configuration)
- [GitHub Actions Setup](docs/GITHUB_ACTIONS_DEPLOYMENT.md) (uses internal scheduler)
- [Web Hosting Setup](docs/WEB_HOSTING_SETUP.md) (uses external scheduler with EventBridge/Cloud Scheduler/Logic Apps)

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

📖 **For hosting-specific persistence configuration, see:**
- [Local Setup Guide](docs/LOCAL_SETUP.md#persistence-configuration-optional) - Includes verification script
- [GitHub Actions Setup](docs/GITHUB_ACTIONS_DEPLOYMENT.md#persistence-configuration) - Uses secrets
- [Web Hosting Setup](docs/WEB_HOSTING_SETUP.md#persistence-firebase) - Uses secret management services

**⚠️ Security Note:** 
- **Never commit** the Firebase JSON file to git
- Use `FIREBASE_CREDENTIALS_PATH` for local development (file path)
- Use `FIREBASE_CREDENTIALS_JSON` for CI/CD and cloud hosting (JSON string)
- Add `firebase-service-account.json` to `.gitignore` if storing locally

**Features:**
- ✅ Tracks all bot trades (BUY/SELL) in Firestore
- ✅ Maintains ownership records for each symbol
- ✅ Prevents selling stocks not purchased by the bot
- ✅ Detects external sales (stocks sold outside the bot)
- ✅ Uses external sale proceeds for reinvestment
- ✅ Falls back to current logic if persistence is disabled or unavailable

**How External Sales Detection Works:**
- Compares DB ownership records against broker positions
- Compares broker transaction history with DB records
- Automatically updates ownership when external sales are detected
- Marks external sale proceeds as available for reinvestment

📖 **Detailed Scenarios:** See [Persistence Scenarios Guide](docs/PERSISTENCE_SCENARIOS.md) for examples of:
- First run behavior
- Normal rebalancing
- External sales (stock in/out of top 5)
- Multiple stocks moving in/out
- Manually purchased stocks entering top 5

### Multiple Portfolio Trading

The bot supports trading multiple portfolios simultaneously, each tracking different leaderboard indices independently.

**Default Behavior:**
If no portfolio configuration is provided, the bot **defaults to trading SP400** (S&P 400 MidCap) with the `INITIAL_CAPITAL` amount. This means you can start using the bot immediately without any portfolio configuration - it will automatically trade SP400.

**Available Indices:**
- **SP400** (indexId: 13) - S&P 400 MidCap (default)
- **SP500** (indexId: 9) - S&P 500 LargeCap
- **SP600** (indexId: 12) - S&P 600 SmallCap
- **NDX** (indexId: 8) - NASDAQ-100

**⚠️ Important:** Persistence **must** be enabled when using multiple portfolios. The bot will raise an error if multiple portfolios are configured without persistence.

#### Features

- ✅ **Independent Trading**: Each portfolio trades the top 5 stocks from its respective index
- ✅ **Separate Capital**: Each portfolio maintains its own initial capital and tracks performance independently
- ✅ **Overlapping Stocks**: Handles cases where the same stock appears in multiple portfolios using virtual portfolio tracking
- ✅ **Proportional Selling**: When selling overlapping stocks, calculates sellable quantity based on portfolio's fraction of total ownership
- ✅ **Performance Tracking**: Individual and aggregate performance metrics for each portfolio
- ✅ **Email Reports**: Multi-portfolio email summaries with per-portfolio and overall performance

#### Configuration Methods

**Method 1: Environment Variables (Recommended)**
```bash
TRADE_INDICES=SP400,SP500,SP600
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

**Method 3: Configuration File**
Create `portfolio_config.json` with portfolio definitions.

📖 **For hosting-specific multiple portfolio configuration, see:**
- [Local Setup Guide](docs/LOCAL_SETUP.md#multiple-portfolio-trading)
- [GitHub Actions Setup](docs/GITHUB_ACTIONS_DEPLOYMENT.md#multiple-portfolio-trading)
- [Web Hosting Setup](docs/WEB_HOSTING_SETUP.md#multiple-portfolios)

#### How Overlapping Stocks Work

When the same stock appears in multiple portfolios:
- Each portfolio tracks its own purchases separately
- When selling, the bot calculates the portfolio's fraction of total tracked ownership
- Sellable quantity is proportional to the portfolio's ownership fraction
- External sales are proportionally applied across all portfolios owning the stock

## How It Works

### Single Portfolio Mode

1. **Scheduler triggers** every Monday (or as configured)
2. **Fetches leaderboard** top 5 stocks from your API
3. **Checks current portfolio** allocation
4. **Detects external sales** (if persistence enabled) and adds proceeds to available capital
5. **Rebalances if needed**:
   - If portfolio is empty: Divides initial capital (+ external sale proceeds) into 5 equal parts and buys top 5
   - If allocations don't match: Sells positions not in top 5 (only bot-owned stocks if persistence enabled), buys missing positions using sale proceeds + external sale proceeds
   - If allocations match: Does nothing
6. **Records trades** in Firestore (if persistence enabled)
7. **Sends email notification** with trade summary (if enabled)

### Multiple Portfolio Mode

When multiple portfolios are configured:

1. **Scheduler triggers** every Monday (or as configured)
2. **For each portfolio**:
   - Fetches leaderboard top 5 stocks for that portfolio's index (SP400, SP500, etc.)
   - Checks current portfolio allocation
   - Detects external sales (if persistence enabled) and adds proceeds to available capital
   - Rebalances independently using the portfolio's own capital
   - Records trades in Firestore with portfolio name
3. **Handles overlapping stocks**:
   - Calculates proportional ownership when the same stock appears in multiple portfolios
   - Applies proportional selling logic for shared positions
4. **Calculates performance metrics** for each portfolio individually and overall aggregate
5. **Sends email notification** with multi-portfolio summary including per-portfolio and aggregate performance

## Deployment

Choose your deployment method:

- 🖥️ **[Local Setup Guide](docs/LOCAL_SETUP.md)** - Run locally or with Docker
- ☁️ **[GitHub Actions Setup](docs/GITHUB_ACTIONS_DEPLOYMENT.md)** - Free scheduled runs (recommended for most users)
  - 📖 **Quick Start:** [GitHub Actions Quick Start Guide](docs/GITHUB_ACTIONS_QUICKSTART.md) (5-minute setup!)
- 🌐 **[Web Hosting Setup](docs/WEB_HOSTING_SETUP.md)** - Deploy to AWS, GCP, or Azure

📖 **Not sure which hosting option to choose?** See [Hosting Comparison Guide](docs/HOSTING_COMPARISON.md)

### Quick Comparison

| Method | Cost | Setup Complexity | Best For |
|--------|------|------------------|----------|
| **Local/Docker** | Free | Easy | Development, testing |
| **GitHub Actions** | Free (with limits) | Easy | Most users, scheduled runs |
| **AWS/GCP/Azure** | Pay-per-use | Moderate | Production, always-on, high availability |

## API Endpoints (External Scheduler Mode)

### Health Check
```
GET /health
```
Returns: `{"status": "healthy"}`

### Trigger Rebalancing
```
POST /rebalance
Headers: Authorization: Bearer <WEBHOOK_SECRET> (if configured)
```
Returns: Trade summary JSON

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

## Security

- Never commit `.env` file to version control
- Use environment variables in production
- Rotate API keys regularly
- Use webhook secrets for external scheduler mode
- Review SECURITY.md for best practices

## Dependencies

This project uses the following third-party libraries:

### Core Dependencies

| Library | Version | License | Purpose |
|---------|---------|---------|---------|
| [alpaca-py](https://github.com/alpacahq/alpaca-py) | >=0.28.0 | Apache-2.0 | Alpaca broker integration |
| [robin-stocks](https://github.com/jmfernandes/robin_stocks) | >=3.4.0 | MIT | Robinhood broker integration |
| [webull-python-sdk-core](https://github.com/webull-inc/openapi-python-sdk) | >=0.1.18 | Apache-2.0 | Webull broker integration (core) |
| [webull-python-sdk-trade](https://github.com/webull-inc/openapi-python-sdk) | >=0.1.14 | Apache-2.0 | Webull broker integration (trading) |
| [APScheduler](https://github.com/agronholm/apscheduler) | >=3.10.0 | MIT | Task scheduling |
| [Flask](https://github.com/pallets/flask) | >=3.0.0 | BSD-3-Clause | Web framework for webhook endpoints |
| [requests](https://github.com/psf/requests) | >=2.31.0 | Apache-2.0 | HTTP library |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | >=1.0.0 | BSD | Environment variable management |
| [pydantic](https://github.com/pydantic/pydantic) | >=2.0.0 | MIT | Data validation |
| [pytz](https://github.com/stub42/pytz) | >=2024.1 | MIT | Timezone handling |

### Optional Dependencies

| Library | Version | License | Purpose |
|---------|---------|---------|---------|
| [sendgrid](https://github.com/sendgrid/sendgrid-python) | >=6.10.0 | MIT | SendGrid email provider |
| [boto3](https://github.com/boto/boto3) | >=1.34.0 | Apache-2.0 | AWS SES email provider |
| [firebase-admin](https://github.com/firebase/firebase-admin-python) | >=6.5.0 | Apache-2.0 | Firebase Firestore persistence |

### Development Dependencies

| Library | Version | License | Purpose |
|---------|---------|---------|---------|
| [pytest](https://github.com/pytest-dev/pytest) | >=7.4.0 | MIT | Testing framework |
| [pytest-cov](https://github.com/pytest-dev/pytest-cov) | >=4.1.0 | MIT | Coverage plugin |
| [pytest-mock](https://github.com/pytest-dev/pytest-mock) | >=3.12.0 | MIT | Mocking plugin |
| [responses](https://github.com/getsentry/responses) | >=0.24.0 | Apache-2.0 | HTTP mocking |
| [freezegun](https://github.com/spulec/freezegun) | >=1.2.0 | Apache-2.0 | Time mocking |

### License Notes

- All dependencies are open-source and permissively licensed
- This project is licensed under MIT License
- Third-party library licenses are compatible with MIT
- See individual library repositories for full license details

## License

MIT License - see LICENSE file

### Third-Party Licenses

This project includes third-party libraries with their own licenses. All dependencies are listed above with their respective licenses. The use of these libraries is governed by their individual license terms, which are compatible with this project's MIT License.

## Contributing

See CONTRIBUTING.md for guidelines.

## Support

For issues and questions, please open an issue on GitHub.
