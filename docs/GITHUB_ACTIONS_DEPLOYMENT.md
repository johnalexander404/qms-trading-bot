# Deploying Trading Bot with GitHub Actions

This guide shows how to run your trading bot on a schedule using GitHub Actions.

## Overview

GitHub Actions can trigger your bot on a schedule (e.g., weekly) using the **external scheduler mode**. The bot runs as a one-time job, executes the rebalancing, and then exits.

## Prerequisites

- GitHub repository (already set up ✅)
- GitHub Actions enabled (enabled by default)
- All required secrets configured (see below)

## Setup Instructions

### Step 1: Configure Secrets

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **"New repository secret"**
4. Add the following secrets (one at a time):

**Required Secrets:**
- `LEADERBOARD_API_URL` - Your leaderboard API endpoint
- `LEADERBOARD_API_TOKEN` - Your leaderboard API token
- `BROKER_TYPE` - Either `alpaca`, `robinhood`, or `webull`

**Broker Secrets (Alpaca):**
- `ALPACA_API_KEY`
- `ALPACA_API_SECRET`
- `ALPACA_BASE_URL` - e.g., `https://paper-api.alpaca.markets`

**Broker Secrets (Robinhood):**
- `ROBINHOOD_USERNAME`
- `ROBINHOOD_PASSWORD`
- `ROBINHOOD_MFA_CODE` (if using 2FA)

**Broker Secrets (Webull):**
- Uses official Webull OpenAPI SDK - requires App Key/Secret from developer.webull.com
- `WEBULL_APP_KEY`: Your Webull App Key
- `WEBULL_APP_SECRET`: Your Webull App Secret
- `WEBULL_ACCOUNT_ID` (optional)
- `WEBULL_REGION` (optional, default: US)

**Email Secrets (if enabled):**
- `EMAIL_ENABLED` - Set to `true` or `false`
- `EMAIL_RECIPIENT` - Where to send notifications
- `EMAIL_PROVIDER` - `smtp`, `sendgrid`, or `ses`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` (for SMTP)
- Or SendGrid/SES credentials as needed

**Trading Configuration:**
- `INITIAL_CAPITAL` - e.g., `10000.0`
- `SCHEDULER_MODE` - Set to `external` (required for GitHub Actions)

### Step 2: Create GitHub Actions Workflow

Create the file `.github/workflows/trading-bot.yml`:

```yaml
name: Trading Bot Rebalancing

on:
  schedule:
    # Run every Monday at 00:00 UTC (adjust timezone as needed)
    # Format: minute hour day month day-of-week
    - cron: '0 0 * * 1'
  workflow_dispatch:  # Allows manual triggering

jobs:
  rebalance:
    runs-on: ubuntu-latest
    timeout-minutes: 10  # Adjust based on your needs
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      
      - name: Run trading bot
        env:
          LEADERBOARD_API_URL: ${{ secrets.LEADERBOARD_API_URL }}
          LEADERBOARD_API_TOKEN: ${{ secrets.LEADERBOARD_API_TOKEN }}
          BROKER_TYPE: ${{ secrets.BROKER_TYPE }}
          ALPACA_API_KEY: ${{ secrets.ALPACA_API_KEY }}
          ALPACA_API_SECRET: ${{ secrets.ALPACA_API_SECRET }}
          ALPACA_BASE_URL: ${{ secrets.ALPACA_BASE_URL }}
          INITIAL_CAPITAL: ${{ secrets.INITIAL_CAPITAL }}
          SCHEDULER_MODE: external
          EMAIL_ENABLED: ${{ secrets.EMAIL_ENABLED }}
          EMAIL_RECIPIENT: ${{ secrets.EMAIL_RECIPIENT }}
          EMAIL_PROVIDER: ${{ secrets.EMAIL_PROVIDER }}
          SMTP_HOST: ${{ secrets.SMTP_HOST }}
          SMTP_PORT: ${{ secrets.SMTP_PORT }}
          SMTP_USERNAME: ${{ secrets.SMTP_USERNAME }}
          SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
          SMTP_FROM_EMAIL: ${{ secrets.SMTP_FROM_EMAIL }}
        run: |
          # Run bot in one-shot mode (external scheduler)
          python -c "
          from src.main import TradingBot
          bot = TradingBot()
          bot.initialize()
          bot._execute_rebalancing()
          "
      
      - name: Upload logs (if job fails)
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: error-logs
          path: |
            *.log
            logs/
          if-no-files-found: ignore
```

### Step 3: Adjust Schedule

Edit the cron expression in the workflow file to match your needs:

```yaml
- cron: '0 0 * * 1'  # Every Monday at midnight UTC
```

**Common schedules:**
- `'0 0 * * 1'` - Every Monday at 00:00 UTC
- `'0 9 * * 1'` - Every Monday at 09:00 UTC (9 AM)
- `'0 0 * * 0'` - Every Sunday at 00:00 UTC
- `'0 0 1 * *'` - First day of every month at 00:00 UTC

**Cron format:** `minute hour day month day-of-week`
- Minutes: 0-59
- Hours: 0-23 (UTC timezone)
- Day of month: 1-31
- Month: 1-12
- Day of week: 0-7 (0 and 7 = Sunday)

### Step 4: Test the Workflow

1. Commit and push the workflow file
2. Go to **Actions** tab in your GitHub repository
3. Click **"Trading Bot Rebalancing"** workflow
4. Click **"Run workflow"** → **"Run workflow"** to test manually
5. Monitor the run to ensure it completes successfully

## Limitations of GitHub Actions

### ⚠️ Important Considerations:

1. **Free Tier Limits:**
   - 2,000 minutes/month for private repos
   - 500 minutes/month for free public repos
   - Your bot should complete in < 5 minutes per run

2. **Reliability:**
   - Jobs can be queued during high load
   - No guarantee of exact execution time
   - Not suitable for time-critical trading

3. **Security:**
   - Secrets are encrypted, but consider if you're comfortable with cloud-hosted secrets
   - GitHub has access to your workflow logs

4. **No Always-On Service:**
   - Can't run continuous processes
   - Only suitable for scheduled, one-time executions

## Better Alternatives for Production

For production use, consider:

1. **AWS Lambda + EventBridge** - Serverless, pay-per-execution
2. **Google Cloud Run + Cloud Scheduler** - Container-based, very affordable
3. **Railway/Render** - Simple PaaS, good for small projects
4. **DigitalOcean App Platform** - Simple deployment
5. **Your own VPS** - Full control, runs 24/7

See the main README.md for deployment options.

## Monitoring

- Check the **Actions** tab regularly to ensure runs complete
- Set up email notifications for failed workflow runs (GitHub Settings → Notifications)
- Review logs in the Actions tab if something goes wrong

## Troubleshooting

### Workflow fails immediately
- Check that all required secrets are set
- Verify secret names match exactly (case-sensitive)
- Review workflow logs for specific error messages

### Bot runs but doesn't execute trades
- Verify broker credentials are correct
- Check that `SCHEDULER_MODE=external` is set
- Review application logs in the Actions output

### Schedule not running
- GitHub Actions schedules can be delayed during high load
- Verify cron syntax is correct
- Check Actions tab to see if workflow is queued

## Cost

- **Free** for public repositories
- **Free** for private repositories (within 2,000 minutes/month limit)
- If you exceed limits, GitHub Pro is $4/month (includes 3,000 minutes)

## Security Best Practices

1. **Never commit secrets** - Always use GitHub Secrets
2. **Use least privilege** - Only grant necessary permissions
3. **Rotate secrets regularly** - Update API keys periodically
4. **Review workflow logs** - Check for any exposed information
5. **Enable branch protection** - Prevent accidental secret exposure
