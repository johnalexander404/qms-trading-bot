# How to Generate a Google App Password for Gmail SMTP

This guide will walk you through creating a Google App Password, which is required to use Gmail SMTP with this trading bot.

## Prerequisites

- A Google account (Gmail)
- Access to your Google Account settings

## Step-by-Step Instructions

### Step 1: Enable 2-Step Verification

1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Sign in with your Google account if prompted
3. Scroll down to the **"How you sign in to Google"** section
4. Find **"2-Step Verification"** and click on it
5. If 2-Step Verification is **not enabled**:
   - Click **"Get Started"**
   - Follow the prompts to set up 2-Step Verification
   - You'll need to verify your phone number
   - Complete the setup process
6. If 2-Step Verification is **already enabled**, proceed to Step 2

> **Note:** App Passwords are only available for accounts with 2-Step Verification enabled. This is a Google security requirement.

### Step 2: Generate an App Password

1. While still in your Google Account settings, go to the **Security** page
2. Under **"How you sign in to Google"**, find **"2-Step Verification"**
3. Click on **"2-Step Verification"** (not the toggle, but the text/link)
4. Scroll down to the bottom of the 2-Step Verification page
5. Look for the **"App passwords"** section [https://myaccount.google.com/apppasswords]
6. Click on **"App passwords"**

   > **Note:** If you don't see "App passwords", make sure:
   > - 2-Step Verification is fully enabled
   > - You're using a personal Google account (not a Workspace account with admin restrictions)
   > - You're signed in to the correct account

7. You may be prompted to sign in again for security
8. In the **"Select app"** dropdown, choose **"Mail"**
9. In the **"Select device"** dropdown, choose **"Other (Custom name)"**
10. Type a descriptive name like **"Trading Bot"** or **"QMS Trading Bot"**
11. Click **"Generate"**

### Step 3: Copy Your App Password

1. Google will display a **16-character password** (it will look like: `abcd efgh ijkl mnop`)
2. **Copy this password immediately** - you won't be able to see it again!
3. The password will be shown with spaces, but you can copy it with or without spaces (both work)
4. Click **"Done"** to close the dialog

### Step 4: Configure Your .env File

1. Open your `.env` file in the project root
2. Set the following values:

```env
EMAIL_ENABLED=true
EMAIL_RECIPIENT=your_email@example.com
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_gmail@gmail.com
SMTP_PASSWORD=abcd efgh ijkl mnop
SMTP_FROM_EMAIL=your_gmail@gmail.com
```

**Important:**
- Replace `your_gmail@gmail.com` with your actual Gmail address
- Replace `abcd efgh ijkl mnop` with the 16-character app password you just generated
- Replace `your_email@example.com` with the email address where you want to receive notifications
- The `SMTP_USERNAME` and `SMTP_FROM_EMAIL` should be the same Gmail address
- The `EMAIL_RECIPIENT` can be any email address (doesn't have to be Gmail)

### Step 5: Test Your Configuration

Run the validation script to test your email setup:

```bash
python scripts/validate-config.py
```

Or test the connection:

```bash
python scripts/test-connection.py
```

## Troubleshooting

### "App passwords" option is not visible

**Possible causes:**
- 2-Step Verification is not fully enabled
- You're using a Google Workspace account with admin restrictions
- Your account type doesn't support app passwords

**Solutions:**
- Verify 2-Step Verification is completely set up
- Contact your Google Workspace administrator if using a work account
- Consider using a personal Gmail account or an alternative SMTP provider

### "Invalid credentials" error

**Possible causes:**
- App password was copied incorrectly
- Using your regular Gmail password instead of app password
- Extra spaces in the password

**Solutions:**
- Generate a new app password and copy it carefully
- Make sure you're using the app password, not your regular password
- Remove any extra spaces when pasting into `.env`

### "Less secure app access" error

**Note:** Google no longer supports "Less secure app access". You **must** use an App Password with 2-Step Verification enabled.

### Email not sending

**Check:**
1. Verify `EMAIL_ENABLED=true` in your `.env`
2. Check that `EMAIL_RECIPIENT` is set
3. Review application logs for specific error messages
4. Test with the connection test script

## Security Best Practices

1. **Never share your app password** - treat it like your regular password
2. **Use descriptive names** when creating app passwords (e.g., "Trading Bot - Production")
3. **Revoke unused app passwords** - if you regenerate, delete the old one
4. **Rotate app passwords periodically** - generate new ones every 6-12 months
5. **Never commit `.env` to version control** - it's already in `.gitignore`

## Alternative: Using Other Email Providers

If you prefer not to use Gmail, you can use:

- **Outlook/Hotmail**: Similar process, create app password in Microsoft Account settings
- **Brevo (Sendinblue)**: Free tier with 300 emails/day, uses API key instead
- **SendGrid**: Free tier available, uses API key
- **AWS SES**: Pay-as-you-go, very affordable for low volume

See the main README.md for configuration details for other providers.

## Need Help?

If you encounter issues:
1. Check the application logs for specific error messages
2. Verify all environment variables are set correctly
3. Test with the provided validation scripts
4. Open an issue on GitHub with error details
