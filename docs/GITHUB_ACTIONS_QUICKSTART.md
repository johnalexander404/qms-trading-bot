# GitHub Actions Quick Start Guide

Get your QMS Trading Bot running on GitHub Actions in 5 minutes!

## ✅ Prerequisites

- Your code is pushed to GitHub (already done ✅) - Fork this repo to  your own space
- You have your API keys and credentials ready
- The workflow file is already created at `.github/workflows/trading-bot.yml`

## 🚀 Step-by-Step Setup

### Step 1: Add Secrets to GitHub

1. **Go to your GitHub repository**
   - Navigate to your repo on GitHub.com

2. **Open Secrets Settings**
   - Click **Settings** (top menu)
   - In the left sidebar, click **Secrets and variables** → **Actions**

3. **Add Required Secrets and Variables**

   **Important:** GitHub has two types:
   - **Secrets** 🔒 - For sensitive data (API keys, passwords)
   - **Variables** 📝 - For configuration (non-sensitive settings)

   **Add as SECRETS (Settings → Secrets tab):**
   ```
   Name: LEADERBOARD_API_TOKEN
   Value: your_token_here
   
   Name: ALPACA_API_KEY
   Value: your_alpaca_key
   
   Name: ALPACA_API_SECRET
   Value: your_alpaca_secret

   ```
   **Fill following variables if you need to maintain history of trades separate from the trading partner.**
   ```
   
   Name: FIREBASE_PROJECT_ID (optional - for persistence but needed for trading multiple portfolios)
   Value: your-firebase-project-id
   
   Name: FIREBASE_CREDENTIALS_JSON (optional - for persistence but needed for trading multiple portfolios)
   Value: {"type":"service_account","project_id":"...","private_key":"..."}
   ```
      > 💡 **For FIREBASE_CREDENTIALS_JSON:** Copy the entire content of your Firebase service account JSON file. GitHub handles multi-line secrets automatically.
   **If you want summary emails sent to you after trades execute add the following to secrets.**
   ```
   Name: EMAIL_RECIPIENT (optional)
   Value: your_email@example.com
   
   Name: SMTP_USERNAME (optional)
   Value: your_gmail@gmail.com
   
   Name: SMTP_PASSWORD (optional) See [Gmail App Password Guide](GMAIL_APP_PASSWORD_SETUP.md)
   Value: your_app_password
   
   Name: SMTP_FROM_EMAIL (optional)
   Value: your_gmail@gmail.com
   ```
   

   **Add as VARIABLES (Settings → Variables tab):**
   ```
   Name: LEADERBOARD_API_URL
   Value: https://your-api.com/leaderboard
   
   Name: BROKER_TYPE
   Value: alpaca
   
   Name: ALPACA_BASE_URL
   Value: https://paper-api.alpaca.markets
   
   Name: INITIAL_CAPITAL
   Value: 10000.0
   
   Name: EMAIL_ENABLED (optional)
   Value: true
   
   Name: EMAIL_PROVIDER (optional)
   Value: smtp
   
   Name: SMTP_HOST (optional)
   Value: smtp.gmail.com
   
   Name: SMTP_PORT (optional)
   Value: 587
   
   Name: PERSISTENCE_ENABLED (optional - for Firebase persistence)
   Value: true
   ```

   > 💡 **Tip:** See [Secrets vs Variables Guide](GITHUB_SECRETS_VS_VARIABLES.md) for details
   > 💡 **Persistence:** See [Persistence Configuration](../README.md#persistence-configuration-optional) in README for Firebase setup instructions
   > 💡 **Tip:** Copy each name exactly as shown (case-sensitive!)

### Step 2: Test the Workflow Manually

1. **Go to Actions Tab**
   - Click **Actions** in your repository's top menu

2. **Find Your Workflow**
   - You should see "Trading Bot Rebalancing" in the left sidebar
   - Click on it

3. **Run It Manually**
   - Click **"Run workflow"** button (top right)
   - Select your branch (usually `main` or `master`)
   - Click the green **"Run workflow"** button

4. **Watch It Run**
   - You'll see a new workflow run appear
   - Click on it to see the progress
   - Each step will show a checkmark ✅ when complete

### Step 3: Verify It Works

1. **Check the Logs**
   - Click on the workflow run
   - Click on the **"Run trading bot"** step
   - Look for success messages or errors

2. **Expected Output**
   - ✅ "Initialized broker: alpaca"
   - ✅ "Initialized leaderboard client"
   - ✅ "Executing rebalancing..."
   - ✅ "Rebalancing completed"

3. **If It Fails**
   - Check which step failed
   - Common issues:
     - Missing secret → Add the missing secret
     - Wrong secret name → Check spelling (case-sensitive!)
     - Invalid API key → Verify your credentials

### Step 4: Adjust the Schedule (Optional)

The bot is set to run **every Monday at midnight UTC** by default.

**To change the schedule:**

1. Edit `.github/workflows/trading-bot.yml`
2. Find this line:
   ```yaml
   - cron: '0 0 * * 1'
   ```
3. Change it to your preferred time

**Common schedules:**
```yaml
'0 0 * * 1'    # Every Monday at 00:00 UTC
'0 9 * * 1'    # Every Monday at 09:00 UTC (9 AM)
'0 0 * * 0'    # Every Sunday at 00:00 UTC
'0 0 1 * *'    # First day of every month
'0 */6 * * *' # Every 6 hours
```

**Cron format:** `minute hour day month day-of-week`
- Times are in **UTC** (convert your local time)

4. Commit and push:
   ```bash
   git add .github/workflows/trading-bot.yml
   git commit -m "Update trading bot schedule"
   git push
   ```

## 📊 Monitoring Your Bot

### View Workflow Runs

1. Go to **Actions** tab
2. Click **"Trading Bot Rebalancing"**
3. See all past runs with their status:
   - ✅ Green checkmark = Success
   - ❌ Red X = Failed
   - 🟡 Yellow circle = In progress

### Check Logs

1. Click on any workflow run
2. Click on **"Run trading bot"** step
3. See detailed output and any errors

### Set Up Email Notifications

GitHub can email you when workflows fail:

1. Go to **Settings** → **Notifications**
2. Enable **"Actions"** notifications
3. Choose when to be notified (failures, all runs, etc.)

## 🔧 Troubleshooting

### ❌ "Secret not found" error

**Problem:** A secret is missing or misspelled

**Solution:**
1. Go to Settings → Secrets and variables → Actions
2. Check that all required secrets are added
3. Verify secret names match exactly (case-sensitive!)

### ❌ "Invalid credentials" error

**Problem:** API keys or credentials are wrong

**Solution:**
1. Double-check your API keys
2. For Alpaca, make sure you're using the correct base URL:
   - Paper: `https://paper-api.alpaca.markets`
   - Live: `https://api.alpaca.markets`

### ❌ Workflow not running on schedule

**Problem:** Scheduled runs might be delayed

**Solution:**
- GitHub Actions schedules can be delayed during high load
- This is normal and expected
- Runs usually happen within 15-30 minutes of scheduled time

### ❌ "Module not found" error

**Problem:** Dependencies aren't installing correctly

**Solution:**
1. Check that `requirements.txt` is in your repo
2. Verify all dependencies are listed
3. Check the "Install dependencies" step logs

## 💰 Cost

- **Free** for public repositories
- **Free** for private repositories (2,000 minutes/month)
- If you exceed limits, GitHub Pro is $4/month (includes 3,000 minutes)

**Your bot uses:** ~2-5 minutes per run
- Weekly runs = ~20 minutes/month
- Well within free tier! ✅

## 🎯 Next Steps

1. ✅ **Test it works** - Run manually first
2. ✅ **Verify schedule** - Wait for first scheduled run
3. ✅ **Monitor results** - Check Actions tab weekly
4. ✅ **Set up email alerts** - Get notified of failures

## 📚 More Information

- **Full Guide:** See [GitHub Actions Deployment Guide](GITHUB_ACTIONS_DEPLOYMENT.md)
- **Hosting Options:** See [Hosting Comparison](HOSTING_COMPARISON.md)
- **Email Setup:** See [Gmail App Password Guide](GMAIL_APP_PASSWORD_SETUP.md)

## 🆘 Need Help?

1. Check the workflow logs for specific error messages
2. Review the troubleshooting section above
3. Open an issue on GitHub with error details

---

**That's it!** Your bot will now run automatically on schedule. 🎉
