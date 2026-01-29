# QMS Trading Bot

Automated portfolio rebalancing bot that tracks a leaderboard and automatically rebalances your portfolio to match the top 5 stocks every Monday.

## Features

- **Automated Rebalancing**: Automatically rebalances portfolio to match leaderboard top 5 stocks
- **Multiple Broker Support**: Works with Alpaca, Robinhood, and Webull
- **Flexible Scheduling**: Internal scheduler or external webhook triggers
- **Email Notifications**: Get notified when trades complete (SMTP, SendGrid, or AWS SES)
- **Docker Ready**: Containerized for easy deployment
- **Cloud Deployable**: Works with AWS, GCP, and Azure

## Quick Start

### Prerequisites

- Python 3.11+ or Docker
- Broker account (Alpaca, Robinhood, or Webull)
- Leaderboard API access

### Installation

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
   Edit `.env` with your API keys and credentials (see Configuration section)

4. **Run with Docker (Recommended)**
   ```bash
   docker-compose up
   ```

5. **Or run locally**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   python -m src.main
   ```

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

### Scheduler Configuration

**Internal Scheduler (Default):**
- `SCHEDULER_MODE=internal`
- `CRON_SCHEDULE=0 0 * * 1` (Mondays at midnight)

**External Scheduler (for cloud deployments):**
- `SCHEDULER_MODE=external`
- `WEBHOOK_PORT=8080`
- `WEBHOOK_SECRET=optional_secret_token`

## How It Works

1. **Scheduler triggers** every Monday (or as configured)
2. **Fetches leaderboard** top 5 stocks from your API
3. **Checks current portfolio** allocation
4. **Rebalances if needed**:
   - If portfolio is empty: Divides initial capital into 5 equal parts and buys top 5
   - If allocations don't match: Sells positions not in top 5, buys missing positions
   - If allocations match: Does nothing
5. **Sends email notification** with trade summary (if enabled)

## Deployment

📖 **Not sure which hosting option to choose?** See [Hosting Comparison Guide](docs/HOSTING_COMPARISON.md)

### Local/Docker

See Quick Start section above.

### GitHub Actions (Free for Scheduled Runs)

Run your bot on a schedule using GitHub Actions - perfect for weekly rebalancing!

**Pros:**
- ✅ Free for public repos (500 min/month) or private repos (2,000 min/month)
- ✅ No infrastructure to manage
- ✅ Built-in scheduling
- ✅ Secure secret management

**Cons:**
- ⚠️ Jobs can be delayed during high load
- ⚠️ Not suitable for time-critical trading
- ⚠️ Limited to scheduled runs (not always-on)

📖 **Quick Start:** See [GitHub Actions Quick Start Guide](docs/GITHUB_ACTIONS_QUICKSTART.md) (5-minute setup!)

📖 **Full Guide:** See [GitHub Actions Deployment Guide](docs/GITHUB_ACTIONS_DEPLOYMENT.md)

**Quick Steps:**
1. Add secrets to GitHub repository (Settings → Secrets and variables → Actions)
2. The workflow file is already created at `.github/workflows/trading-bot.yml`
3. Test it manually (Actions → Run workflow)
4. It will run automatically on schedule!

### AWS (ECS/Fargate with EventBridge)

1. Build and push Docker image to ECR
2. Deploy to ECS/Fargate
3. Set `SCHEDULER_MODE=external`
4. Create EventBridge rule: `cron(0 0 ? * MON *)`
5. Configure EventBridge to POST to your container endpoint

### GCP (Cloud Run with Cloud Scheduler)

1. Build and push Docker image to GCR
2. Deploy to Cloud Run
3. Set `SCHEDULER_MODE=external`
4. Create Cloud Scheduler job: `0 0 * * 1`
5. Configure job to POST to Cloud Run service URL

### Azure (Container Instances with Logic Apps)

1. Build and push Docker image to ACR
2. Deploy to Container Instances
3. Set `SCHEDULER_MODE=external`
4. Create Logic App with weekly recurrence trigger
5. Configure Logic App to POST to container endpoint

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
