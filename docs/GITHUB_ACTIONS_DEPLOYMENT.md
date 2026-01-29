# Deploying Trading Bot with GitHub Actions

This guide shows how to run your trading bot on a schedule using GitHub Actions.

## Overview

GitHub Actions can trigger your bot on a schedule (e.g., weekly) using the **external scheduler mode**. The bot runs as a one-time job, executes the rebalancing, and then exits.

## Prerequisites

- GitHub repository (already set up ✅)
- GitHub Actions enabled (enabled by default)
- All required secrets configured (see below)

## Setup Instructions

### Step 1: Configure Secrets and Variables

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Add secrets (🔒) and variables (📝) as indicated below

📖 **See [GitHub Secrets vs Variables Guide](GITHUB_SECRETS_VS_VARIABLES.md) for when to use secrets vs variables**

#### Complete Environment Variables Reference

**Required Variables:**

**Leaderboard API (🔒 Secrets):**
- `LEADERBOARD_API_URL` - Your leaderboard API endpoint (can be variable if not sensitive)
- `LEADERBOARD_API_TOKEN` - Your leaderboard API token (must be secret)

**Broker Type (📝 Variable):**
- `BROKER_TYPE` - Either `alpaca`, `robinhood`, or `webull`

**Broker-Specific Variables:**

  **Alpaca (🔒 Secrets - required if BROKER_TYPE=alpaca):**
  - `ALPACA_API_KEY` - Your Alpaca API key
  - `ALPACA_API_SECRET` - Your Alpaca API secret
  - `ALPACA_BASE_URL` - `https://paper-api.alpaca.markets` (paper) or `https://api.alpaca.markets` (live) - can be variable
  
  **Robinhood (🔒 Secrets - required if BROKER_TYPE=robinhood):**
  - `ROBINHOOD_USERNAME` - Your Robinhood username/email
  - `ROBINHOOD_PASSWORD` - Your Robinhood password
  - `ROBINHOOD_MFA_CODE` - Optional: MFA code if 2FA is enabled
  
  **Webull (🔒 Secrets - required if BROKER_TYPE=webull):**
  - `WEBULL_APP_KEY` - Your Webull App Key (get from [developer.webull.com](https://developer.webull.com))
  - `WEBULL_APP_SECRET` - Your Webull App Secret
  - `WEBULL_ACCOUNT_ID` - Optional: Account ID (will use first account if not provided) - can be variable
  - `WEBULL_REGION` - Optional: `US`, `HK`, or `JP` (default: `US`) - can be variable

**Trading Configuration (📝 Variables):**
- `INITIAL_CAPITAL` - Initial capital amount (e.g., `10000.0`)

**Scheduler Configuration (📝 Variables):**
- `SCHEDULER_MODE` - Set to `internal` (default) for GitHub Actions
- `CRON_SCHEDULE` - Cron expression (default: `0 0 * * 1` for Mondays) - handled by workflow file
- `WEBHOOK_PORT` - Not used for GitHub Actions (can be omitted)
- `WEBHOOK_SECRET` - Not used for GitHub Actions (can be omitted)

**Email Configuration:**

  **Basic Email Settings (📝 Variables):**
  - `EMAIL_ENABLED` - Set to `true` or `false`
  - `EMAIL_RECIPIENT` - Recipient email address (🔒 Secret for privacy)
  - `EMAIL_PROVIDER` - `smtp`, `sendgrid`, or `ses`
  
  **SMTP Configuration (🔒 Secrets - required if EMAIL_PROVIDER=smtp):**
  - `SMTP_HOST` - e.g., `smtp.gmail.com` (can be variable)
  - `SMTP_PORT` - e.g., `587` (can be variable)
  - `SMTP_USERNAME` - Your email username
  - `SMTP_PASSWORD` - Your email app password
  - `SMTP_FROM_EMAIL` - From email address
  
  **SendGrid Configuration (🔒 Secrets - required if EMAIL_PROVIDER=sendgrid):**
  - `SENDGRID_API_KEY` - Your SendGrid API key
  - `SENDGRID_FROM_EMAIL` - Your verified SendGrid email (can be variable)
  
  **AWS SES Configuration (🔒 Secrets - required if EMAIL_PROVIDER=ses):**
  - `AWS_REGION` - e.g., `us-east-1` (can be variable)
  - `AWS_ACCESS_KEY_ID` - Your AWS access key
  - `AWS_SECRET_ACCESS_KEY` - Your AWS secret key
  - `SES_FROM_EMAIL` - Your verified SES email (can be variable)

**Persistence Configuration (Optional - 🔒 Secrets):**
- `PERSISTENCE_ENABLED` - Set to `true` (optional - auto-enables if credentials are set) - can be variable
- `FIREBASE_PROJECT_ID` - Your Firebase project ID (can be variable)
- `FIREBASE_CREDENTIALS_JSON` - **Entire content of Firebase service account JSON file**
  - Download JSON from Firebase Console → Project Settings → Service Accounts
  - Copy the entire file content (including all braces, quotes, etc.)
  - Paste as a secret (GitHub handles multi-line secrets)

**Multiple Portfolio Configuration (Optional):**

  **Default Behavior:**
  If no portfolio configuration is provided, the bot **defaults to trading SP400** (S&P 400 MidCap) with the `INITIAL_CAPITAL` amount.
  
  **Method 1: Environment Variables (📝 Variables):**
  - `TRADE_INDICES` - Comma-separated list (e.g., `SP400,SP500,SP600`)
    - If not set, defaults to `SP400`
  - `INITIAL_CAPITAL_SP400` - Capital for SP400 portfolio
  - `INITIAL_CAPITAL_SP500` - Capital for SP500 portfolio
  - `INITIAL_CAPITAL_SP600` - Capital for SP600 portfolio
  - `INITIAL_CAPITAL_NDX` - Capital for NDX portfolio
  
  **Method 2: JSON Configuration (📝 Variable):**
  - `PORTFOLIO_CONFIG` - JSON string: `[{"portfolio_name":"SP400","index_id":"13","initial_capital":50000,"enabled":true}]`

**Note:** To explicitly configure a single SP400 portfolio, you can either:
- Leave `TRADE_INDICES` unset (defaults to SP400)
- Set `TRADE_INDICES=SP400`

**Security Configuration (📝 Variable):**
- `MASK_FINANCIAL_AMOUNTS` - Set to `true` or `false` (default: `true`)

**⚠️ Important:** 
- Never commit sensitive values to git
- Use secrets (🔒) for API keys, passwords, tokens, and sensitive data
- Use variables (📝) for non-sensitive configuration values
- See [GitHub Secrets vs Variables Guide](GITHUB_SECRETS_VS_VARIABLES.md) for details

### Step 2: Create GitHub Actions Workflow (already present)

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
