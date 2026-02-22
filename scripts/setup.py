#!/usr/bin/env python3
"""Interactive setup wizard for QMS Trading Bot.

Usage:
    python scripts/setup.py                        # Interactive setup
    python scripts/setup.py --env                  # Generate .env file only
    python scripts/setup.py --github               # Push to GitHub Actions only
    python scripts/setup.py --github --env         # Both

    # Environment management (requires gh CLI)
    python scripts/setup.py --github --list
    python scripts/setup.py --github --disable live
    python scripts/setup.py --github --enable live

    # Update only specific sections (loads existing .env, runs chosen sections, writes back)
    python scripts/setup.py --update broker
    python scripts/setup.py --update              # Prompts for sections (and for GitHub env if pushing)
    python scripts/setup.py --update email,scheduler --env
    # Update specific sections in a GitHub environment (only those vars are pushed)
    python scripts/setup.py --update broker --github --environment paper
    python scripts/setup.py --update --github     # Prompts for sections, then for target environment
"""

import argparse
import getpass
import json
import os
import shutil
import stat
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROGRESS_FILE = PROJECT_ROOT / ".setup-progress.json"

SECTIONS = ["leaderboard", "broker", "trading", "email", "persistence", "scheduler"]

# Keys per section (for partial push to GitHub environments). INITIAL_CAPITAL_* handled separately.
SECTION_KEYS = {
    "leaderboard": {"LEADERBOARD_API_URL", "LEADERBOARD_API_TOKEN"},
    "broker": {
        "BROKER_TYPE",
        "ALPACA_API_KEY", "ALPACA_API_SECRET", "ALPACA_BASE_URL",
        "ROBINHOOD_USERNAME", "ROBINHOOD_PASSWORD", "ROBINHOOD_MFA_CODE",
        "WEBULL_APP_KEY", "WEBULL_APP_SECRET", "WEBULL_ACCOUNT_ID", "WEBULL_REGION",
        "TRADIER_ACCESS_TOKEN", "TRADIER_ACCOUNT_ID", "TRADIER_BASE_URL",
    },
    "trading": {"INITIAL_CAPITAL", "TRADE_INDICES"},  # plus any INITIAL_CAPITAL_*
    "email": {
        "EMAIL_ENABLED", "EMAIL_RECIPIENT", "EMAIL_PROVIDER",
        "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL",
        "SENDGRID_API_KEY", "SENDGRID_FROM_EMAIL",
        "AWS_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "SES_FROM_EMAIL",
    },
    "persistence": {
        "PERSISTENCE_ENABLED", "FIREBASE_PROJECT_ID", "FIREBASE_CREDENTIALS_JSON",
        "FIRESTORE_DATABASE_ID", "PERSISTENCE_COLLECTION_PREFIX",
    },
    "scheduler": {"SCHEDULER_MODE", "CRON_SCHEDULE", "SCHEDULER_TIMEZONE", "WEBHOOK_PORT", "WEBHOOK_SECRET"},
}

SECRETS = {
    "LEADERBOARD_API_URL", "LEADERBOARD_API_TOKEN",
    "ALPACA_API_KEY", "ALPACA_API_SECRET",
    "ROBINHOOD_USERNAME", "ROBINHOOD_PASSWORD", "ROBINHOOD_MFA_CODE",
    "WEBULL_APP_KEY", "WEBULL_APP_SECRET",
    "TRADIER_ACCESS_TOKEN", "TRADIER_ACCOUNT_ID",
    "EMAIL_RECIPIENT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL",
    "SENDGRID_API_KEY", "SENDGRID_FROM_EMAIL",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "SES_FROM_EMAIL",
    "FIREBASE_PROJECT_ID", "FIREBASE_CREDENTIALS_JSON",
}

BROKER_INFO = {
    "alpaca": {
        "name": "Alpaca",
        "url": "https://app.alpaca.markets/paper/dashboard/overview",
        "instructions": "Go to your Alpaca dashboard > Paper Trading > API Keys to generate a key pair.",
    },
    "robinhood": {
        "name": "Robinhood",
        "url": None,
        "instructions": "Uses your existing Robinhood account credentials.",
    },
    "webull": {
        "name": "Webull",
        "url": "https://developer.webull.com",
        "instructions": "Sign in to the Webull Developer Portal and create an app to get your App Key and App Secret.",
    },
    "tradier": {
        "name": "Tradier",
        "url": "https://web.tradier.com/user/api",
        "instructions": "Go to your Tradier account > API Access to find your API key and account number.",
    },
}

EMAIL_INFO = {
    "smtp": {
        "name": "SMTP (Gmail, Outlook, etc.)",
        "url": "https://myaccount.google.com/apppasswords",
        "instructions": "For Gmail: generate an App Password (requires 2-Step Verification).\n"
                        "  See docs/GMAIL_APP_PASSWORD_SETUP.md for detailed steps.",
    },
    "sendgrid": {
        "name": "SendGrid",
        "url": "https://app.sendgrid.com/settings/api_keys",
        "instructions": "Create an API key with Mail Send permissions.",
    },
    "ses": {
        "name": "AWS SES",
        "url": "https://console.aws.amazon.com/ses/",
        "instructions": "Verify your sender email and create IAM credentials with SES permissions.",
    },
}

INDEX_OPTIONS = {
    "SP400": {"id": "13", "name": "S&P 400 MidCap"},
    "SP500": {"id": "9", "name": "S&P 500 LargeCap"},
    "SP600": {"id": "12", "name": "S&P 600 SmallCap"},
    "NDX": {"id": "8", "name": "NASDAQ-100"},
}

# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_step(msg):
    print(f"\n--- {msg} ---\n")


def print_success(msg):
    print(f"  [OK] {msg}")


def print_warning(msg):
    print(f"  [!] {msg}")


def print_error(msg):
    print(f"  [ERROR] {msg}")


def prompt(label, default=None, allow_empty=False):
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"  {label}{suffix}: ").strip()
        if not value and default is not None:
            return default
        if value or allow_empty:
            return value
        print("    Value required.")


def prompt_secret(label, existing=None):
    hint = " [****set****]" if existing else ""
    while True:
        value = getpass.getpass(f"  {label}{hint}: ").strip()
        if not value and existing:
            return existing
        if value:
            return value
        if existing:
            return existing
        print("    Value required.")


def prompt_choice(label, options):
    print(f"  {label}")
    for i, opt in enumerate(options, 1):
        print(f"    [{i}] {opt}")
    while True:
        try:
            choice = int(input("  Choice: ").strip())
            if 1 <= choice <= len(options):
                return choice - 1
        except (ValueError, EOFError):
            pass
        print(f"    Enter a number between 1 and {len(options)}.")


def prompt_yes_no(label, default=True):
    hint = "Y/n" if default else "y/N"
    value = input(f"  {label} [{hint}]: ").strip().lower()
    if not value:
        return default
    return value in ("y", "yes")


def prompt_multi_choice(label, options):
    """Returns list of selected indices."""
    print(f"  {label}")
    for i, opt in enumerate(options, 1):
        print(f"    [{i}] {opt}")
    print("  Enter numbers separated by commas (e.g. 1,3):")
    while True:
        try:
            raw = input("  Choices: ").strip()
            indices = [int(x.strip()) - 1 for x in raw.split(",")]
            if all(0 <= i < len(options) for i in indices) and indices:
                return indices
        except (ValueError, EOFError):
            pass
        print(f"    Enter comma-separated numbers between 1 and {len(options)}.")


def offer_url(url, instructions):
    if not url:
        print(f"  {instructions}")
        return
    print(f"  {instructions}")
    print(f"  URL: {url}")
    if prompt_yes_no("Open in browser?"):
        try:
            webbrowser.open(url)
        except Exception:
            print_warning("Could not open browser. Please visit the URL manually.")
    print()


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def check_cli(name):
    return shutil.which(name) is not None


def run_cmd(cmd, capture=True, check=False):
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=capture, text=True, timeout=120,
        )
        if check and result.returncode != 0:
            return None
        return result
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out: {cmd}")
        return None
    except Exception as e:
        print_error(f"Command failed: {e}")
        return None


def get_gh_repo():
    result = run_cmd("gh repo view --json nameWithOwner -q .nameWithOwner")
    if result and result.returncode == 0:
        return result.stdout.strip()
    return None


# ---------------------------------------------------------------------------
# Load config from .env
# ---------------------------------------------------------------------------

def load_config_from_env(env_path=None):
    """Load KEY=VALUE pairs from .env into a dict. Skips comments and empty lines."""
    path = env_path or PROJECT_ROOT / ".env"
    config = {}
    if not path.exists():
        return config
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1].replace('\\"', '"')
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            config[key] = value
    return config


# ---------------------------------------------------------------------------
# Progress management
# ---------------------------------------------------------------------------

def save_progress(config, completed_index):
    data = {"completed_section": completed_index, "config": config}
    PROGRESS_FILE.write_text(json.dumps(data, indent=2))
    os.chmod(PROGRESS_FILE, stat.S_IRUSR | stat.S_IWUSR)


def load_progress():
    try:
        data = json.loads(PROGRESS_FILE.read_text())
        return data.get("config", {}), data.get("completed_section", 0)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}, 0


def cleanup_progress():
    if PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()


# ---------------------------------------------------------------------------
# Section handlers
# ---------------------------------------------------------------------------

def setup_leaderboard(config):
    print_header("Leaderboard API")
    offer_url(
        "https://quantmystocks.com/?tab=tokens",
        "Sign in to QuantMyStocks and go to the Tokens tab to get your API URL and token.",
    )
    config["LEADERBOARD_API_URL"] = prompt(
        "Leaderboard API URL", default=config.get("LEADERBOARD_API_URL"))
    config["LEADERBOARD_API_TOKEN"] = prompt_secret(
        "Leaderboard API Token", existing=config.get("LEADERBOARD_API_TOKEN"))
    return config


def setup_broker(config):
    print_header("Broker Configuration")
    broker_types = list(BROKER_INFO.keys())
    broker_names = [BROKER_INFO[b]["name"] for b in broker_types]
    choice = prompt_choice("Which broker do you use?", broker_names)
    broker_type = broker_types[choice]
    config["BROKER_TYPE"] = broker_type

    info = BROKER_INFO[broker_type]

    if broker_type == "alpaca":
        offer_url(info["url"], info["instructions"])
        config["ALPACA_API_KEY"] = prompt_secret(
            "Alpaca API Key", existing=config.get("ALPACA_API_KEY"))
        config["ALPACA_API_SECRET"] = prompt_secret(
            "Alpaca API Secret", existing=config.get("ALPACA_API_SECRET"))
        mode = prompt_choice("Trading mode?", ["Paper trading", "Live trading"])
        config["ALPACA_BASE_URL"] = (
            "https://paper-api.alpaca.markets" if mode == 0
            else "https://api.alpaca.markets"
        )

    elif broker_type == "robinhood":
        config["ROBINHOOD_USERNAME"] = prompt_secret(
            "Robinhood Username/Email", existing=config.get("ROBINHOOD_USERNAME"))
        config["ROBINHOOD_PASSWORD"] = prompt_secret(
            "Robinhood Password", existing=config.get("ROBINHOOD_PASSWORD"))
        if prompt_yes_no("Do you have 2FA enabled?", default=False):
            config["ROBINHOOD_MFA_CODE"] = prompt_secret(
                "MFA Code", existing=config.get("ROBINHOOD_MFA_CODE"))

    elif broker_type == "webull":
        offer_url(info["url"], info["instructions"])
        config["WEBULL_APP_KEY"] = prompt_secret(
            "Webull App Key", existing=config.get("WEBULL_APP_KEY"))
        config["WEBULL_APP_SECRET"] = prompt_secret(
            "Webull App Secret", existing=config.get("WEBULL_APP_SECRET"))
        if prompt_yes_no("Specify account ID? (optional, uses first account if not set)", default=False):
            config["WEBULL_ACCOUNT_ID"] = prompt(
                "Webull Account ID", default=config.get("WEBULL_ACCOUNT_ID"))
        region = prompt_choice("Region?", ["US", "HK", "JP"])
        config["WEBULL_REGION"] = ["US", "HK", "JP"][region]

    elif broker_type == "tradier":
        offer_url(info["url"], info["instructions"])
        config["TRADIER_ACCESS_TOKEN"] = prompt_secret(
            "Tradier API Key", existing=config.get("TRADIER_ACCESS_TOKEN"))
        config["TRADIER_ACCOUNT_ID"] = prompt_secret(
            "Tradier Account Number", existing=config.get("TRADIER_ACCOUNT_ID"))
        mode = prompt_choice("Trading mode?", ["Sandbox (paper)", "Production (live)"])
        config["TRADIER_BASE_URL"] = (
            "https://sandbox.tradier.com/v1" if mode == 0
            else "https://api.tradier.com/v1"
        )

    return config


def setup_trading(config):
    print_header("Trading Configuration")

    capital = prompt("Initial capital (USD)", default=config.get("INITIAL_CAPITAL", "10000.0"))
    try:
        float(capital)
    except ValueError:
        print_warning("Invalid number, using 10000.0")
        capital = "10000.0"
    config["INITIAL_CAPITAL"] = capital

    index_names = list(INDEX_OPTIONS.keys())
    index_labels = [f"{k} - {v['name']}" for k, v in INDEX_OPTIONS.items()]
    selected = prompt_multi_choice("Which indices do you want to trade?", index_labels)
    chosen_indices = [index_names[i] for i in selected]
    config["TRADE_INDICES"] = ",".join(chosen_indices)

    if len(chosen_indices) > 1:
        print("\n  Set capital per index (press Enter to use the default above):")
        for idx in chosen_indices:
            val = prompt(
                f"  Capital for {idx}",
                default=config.get(f"INITIAL_CAPITAL_{idx}", capital),
            )
            if val != capital:
                config[f"INITIAL_CAPITAL_{idx}"] = val

    return config


def setup_email(config):
    print_header("Email Notifications")

    if not prompt_yes_no("Enable email notifications?", default=True):
        config["EMAIL_ENABLED"] = "false"
        return config

    config["EMAIL_ENABLED"] = "true"
    config["EMAIL_RECIPIENT"] = prompt_secret(
        "Recipient email address", existing=config.get("EMAIL_RECIPIENT"))

    providers = list(EMAIL_INFO.keys())
    provider_names = [EMAIL_INFO[p]["name"] for p in providers]
    choice = prompt_choice("Email provider?", provider_names)
    provider = providers[choice]
    config["EMAIL_PROVIDER"] = provider

    info = EMAIL_INFO[provider]

    if provider == "smtp":
        config["SMTP_HOST"] = prompt("SMTP Host", default=config.get("SMTP_HOST", "smtp.gmail.com"))
        config["SMTP_PORT"] = prompt("SMTP Port", default=config.get("SMTP_PORT", "587"))
        config["SMTP_USERNAME"] = prompt_secret(
            "SMTP Username", existing=config.get("SMTP_USERNAME"))
        offer_url(info["url"], info["instructions"])
        config["SMTP_PASSWORD"] = prompt_secret(
            "SMTP Password (app password for Gmail)", existing=config.get("SMTP_PASSWORD"))
        config["SMTP_FROM_EMAIL"] = prompt_secret(
            "From email address", existing=config.get("SMTP_FROM_EMAIL"))

    elif provider == "sendgrid":
        offer_url(info["url"], info["instructions"])
        config["SENDGRID_API_KEY"] = prompt_secret(
            "SendGrid API Key", existing=config.get("SENDGRID_API_KEY"))
        config["SENDGRID_FROM_EMAIL"] = prompt_secret(
            "Verified sender email", existing=config.get("SENDGRID_FROM_EMAIL"))

    elif provider == "ses":
        config["AWS_REGION"] = prompt("AWS Region", default=config.get("AWS_REGION", "us-east-1"))
        offer_url(info["url"], info["instructions"])
        config["AWS_ACCESS_KEY_ID"] = prompt_secret(
            "AWS Access Key ID", existing=config.get("AWS_ACCESS_KEY_ID"))
        config["AWS_SECRET_ACCESS_KEY"] = prompt_secret(
            "AWS Secret Access Key", existing=config.get("AWS_SECRET_ACCESS_KEY"))
        config["SES_FROM_EMAIL"] = prompt_secret(
            "Verified sender email", existing=config.get("SES_FROM_EMAIL"))

    return config


def setup_persistence(config):
    print_header("Persistence (Firebase Firestore)")

    indices = config.get("TRADE_INDICES", "SP400").split(",")
    if len(indices) > 1:
        print("  Multiple portfolios require persistence to be enabled.")
        enable = True
    else:
        enable = prompt_yes_no("Enable Firebase persistence? (tracks trades, detects external sales)")

    if not enable:
        config["PERSISTENCE_ENABLED"] = "false"
        return config

    config["PERSISTENCE_ENABLED"] = "true"

    method = prompt_choice("How would you like to set up Firebase?", [
        "Auto-create via gcloud CLI (recommended)",
        "Manual setup with guided URLs",
        "I already have Firebase credentials",
    ])

    if method == 0:
        config = setup_firebase_gcloud(config)
    elif method == 1:
        config = setup_firebase_manual(config)
    else:
        config = setup_firebase_existing(config)

    # Optional: isolate data per environment (same project)
    if config.get("PERSISTENCE_ENABLED") == "true":
        if prompt_yes_no("Use a collection prefix for this environment? (recommended if you'll run paper + live with same Firebase project)", default=False):
            prefix = prompt("Collection prefix (e.g. paper_ or live_)", default=config.get("PERSISTENCE_COLLECTION_PREFIX", "paper_"))
            if prefix and not prefix.endswith("_"):
                prefix = f"{prefix}_"
            config["PERSISTENCE_COLLECTION_PREFIX"] = prefix or ""
        if prompt_yes_no("Use a different Firestore database for this environment? (e.g. database 'live' in same project)", default=False):
            config["FIRESTORE_DATABASE_ID"] = prompt("Firestore database ID", default=config.get("FIRESTORE_DATABASE_ID", "live"))

    return config


def _validate_gcp_project_id(project_id):
    """Returns an error message if invalid, or None if valid."""
    import re
    if len(project_id) < 6 or len(project_id) > 30:
        return f"Project ID must be 6-30 characters (got {len(project_id)})."
    if not re.match(r'^[a-z][a-z0-9-]*$', project_id):
        return "Project ID must start with a lowercase letter and contain only lowercase letters, digits, or hyphens."
    if project_id.endswith('-'):
        return "Project ID must not end with a hyphen."
    return None


def setup_firebase_gcloud(config):
    print_step("Firebase Auto-Setup via gcloud")

    if not check_cli("gcloud"):
        print_warning("gcloud CLI is not installed.")
        offer_url(
            "https://docs.cloud.google.com/sdk/docs/downloads-interactive",
            "Install the Google Cloud CLI using the interactive installer.",
        )
        if prompt_yes_no("Fall back to manual setup?"):
            return setup_firebase_manual(config)
        config["PERSISTENCE_ENABLED"] = "false"
        return config

    # Check authentication
    result = run_cmd('gcloud auth list --filter="status:ACTIVE" --format="value(account)"')
    if not result or not result.stdout.strip():
        print("  Authenticating with Google Cloud (opening browser)...")
        run_cmd("gcloud auth login", capture=False)

    # Create or select project
    default_id = f"trading-bot-{int(time.time())}"
    while True:
        project_id = prompt("Firebase/GCP Project ID", default=config.get("FIREBASE_PROJECT_ID", default_id))
        error = _validate_gcp_project_id(project_id)
        if error:
            print_warning(error)
            continue
        break

    print(f"\n  Creating project '{project_id}'...")
    result = run_cmd(f'gcloud projects create {project_id} --name="Trading Bot"')
    if result and result.returncode != 0:
        stderr = result.stderr or ""
        if "already exists" in stderr or "already in use" in stderr:
            choice = prompt_choice(f"Project '{project_id}' already exists.", [
                "Use this existing project (it's mine)",
                "Enter a different project ID",
                "Fall back to manual setup",
            ])
            if choice == 0:
                print_success(f"Using existing project '{project_id}'.")
            elif choice == 1:
                while True:
                    project_id = prompt("Firebase/GCP Project ID")
                    error = _validate_gcp_project_id(project_id)
                    if error:
                        print_warning(error)
                        continue
                    break
                print(f"\n  Creating project '{project_id}'...")
                retry = run_cmd(f'gcloud projects create {project_id} --name="Trading Bot"')
                if retry and retry.returncode != 0:
                    print_error(f"Failed to create project: {retry.stderr}")
                    if prompt_yes_no("Use it as an existing project anyway?"):
                        print_success(f"Using project '{project_id}'.")
                    elif prompt_yes_no("Fall back to manual setup?"):
                        return setup_firebase_manual(config)
                    else:
                        config["PERSISTENCE_ENABLED"] = "false"
                        return config
            else:
                return setup_firebase_manual(config)
        else:
            print_error(f"Failed to create project: {stderr}")
            if prompt_yes_no("Fall back to manual setup?"):
                return setup_firebase_manual(config)
            config["PERSISTENCE_ENABLED"] = "false"
            return config

    config["FIREBASE_PROJECT_ID"] = project_id

    # Enable Firestore API
    print("  Enabling Firestore API...")
    result = run_cmd(f"gcloud services enable firestore.googleapis.com --project={project_id}")
    if result and result.returncode != 0:
        print_error(f"Failed to enable Firestore API: {result.stderr}")
        print_warning("You may need to enable billing on the project first.")
        if prompt_yes_no("Fall back to manual setup?"):
            return setup_firebase_manual(config)
        config["PERSISTENCE_ENABLED"] = "false"
        return config

    # Create Firestore database
    print("  Creating Firestore database...")
    result = run_cmd(
        f"gcloud firestore databases create --location=us-central1 --project={project_id}"
    )
    if result and result.returncode != 0:
        stderr = result.stderr or ""
        if "already exists" in stderr:
            print_success("Firestore database already exists.")
        elif "billing" in stderr.lower() or "does not have permission" in stderr:
            billing_url = f"https://console.developers.google.com/billing/enable?project={project_id}"
            print_error("Firestore requires billing to be enabled on the project.")
            print(f"  Enable billing: {billing_url}")
            if prompt_yes_no("Open billing page in browser?"):
                try:
                    webbrowser.open(billing_url)
                except Exception:
                    pass
            if prompt_yes_no("After enabling billing, continue with setup? (database will be created; say No to use manual setup instead)"):
                retry = run_cmd(
                    f"gcloud firestore databases create --location=us-central1 --project={project_id}"
                )
                if retry and retry.returncode != 0 and "already exists" not in (retry.stderr or ""):
                    print_error(f"Still failed: {retry.stderr}")
                    if prompt_yes_no("Fall back to manual setup?"):
                        return setup_firebase_manual(config)
                    config["PERSISTENCE_ENABLED"] = "false"
                    return config
            elif prompt_yes_no("Fall back to manual setup?"):
                return setup_firebase_manual(config)
            else:
                config["PERSISTENCE_ENABLED"] = "false"
                return config
        else:
            print_error(f"Failed to create database: {stderr}")
            if prompt_yes_no("Continue anyway? (database may already exist)"):
                pass
            elif prompt_yes_no("Fall back to manual setup?"):
                return setup_firebase_manual(config)
            else:
                config["PERSISTENCE_ENABLED"] = "false"
                return config

    # Create service account
    sa_name = "trading-bot-sa"
    sa_email = f"{sa_name}@{project_id}.iam.gserviceaccount.com"
    print(f"  Creating service account '{sa_name}'...")
    run_cmd(
        f'gcloud iam service-accounts create {sa_name} '
        f'--display-name="Trading Bot" --project={project_id}'
    )

    # Grant Firestore access (owner role for full read/write to all collections)
    print("  Granting Firestore access...")
    run_cmd(
        f"gcloud projects add-iam-policy-binding {project_id} "
        f'--member="serviceAccount:{sa_email}" '
        f'--role="roles/datastore.owner" --quiet'
    )
    print("  Waiting for IAM to propagate (15s)...")
    time.sleep(15)

    # Generate key
    key_path = PROJECT_ROOT / "firebase-service-account.json"
    print(f"  Generating service account key -> {key_path.name}...")
    result = run_cmd(
        f"gcloud iam service-accounts keys create {key_path} "
        f"--iam-account={sa_email}"
    )
    if result and result.returncode != 0:
        print_error(f"Failed to generate key: {result.stderr}")
        if prompt_yes_no("Fall back to manual setup?"):
            return setup_firebase_manual(config)
        config["PERSISTENCE_ENABLED"] = "false"
        return config

    # Validate the key file
    if key_path.exists():
        try:
            creds = json.loads(key_path.read_text())
            if creds.get("type") == "service_account":
                print_success("Service account key validated.")
                config["FIREBASE_CREDENTIALS_PATH"] = str(key_path)
                config["FIREBASE_CREDENTIALS_JSON"] = key_path.read_text()
            else:
                print_warning("Key file doesn't look like a service account key.")
        except json.JSONDecodeError:
            print_warning("Key file is not valid JSON.")

    # Add to .gitignore
    gitignore = PROJECT_ROOT / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if "firebase-service-account.json" not in content:
            with open(gitignore, "a") as f:
                f.write("\nfirebase-service-account.json\n")
            print_success("Added firebase-service-account.json to .gitignore")

    # Optionally verify
    verify_ok = True
    if prompt_yes_no("Run Firebase verification script?", default=False):
        python = sys.executable
        print("  This requires project dependencies. Installing now...")
        run_cmd(f'"{python}" -m pip install -r "{PROJECT_ROOT / "scripts" / "requirements.txt"}"', capture=False)
        os.environ["FIREBASE_PROJECT_ID"] = project_id
        os.environ["FIREBASE_CREDENTIALS_PATH"] = str(key_path)
        result = run_cmd(f'"{python}" "{PROJECT_ROOT / "scripts" / "verify-firebase.py"}"')
        verify_ok = result is not None and result.returncode == 0
        if not verify_ok:
            print_warning("Verification had errors. IAM can take 1–2 minutes to propagate—run scripts/verify-firebase.py again shortly.")

    if verify_ok:
        print_success("Firebase setup complete!")
    return config


def setup_firebase_manual(config):
    print_step("Firebase Manual Setup")

    # Step 1: Create project
    offer_url(
        "https://console.firebase.google.com/",
        "Create a new Firebase project (or select an existing one).",
    )
    project_id = prompt("Firebase Project ID", default=config.get("FIREBASE_PROJECT_ID"))
    config["FIREBASE_PROJECT_ID"] = project_id

    # Step 2: Create Firestore database
    offer_url(
        f"https://console.firebase.google.com/project/{project_id}/firestore",
        "Click 'Create database', choose 'Start in test mode', pick a region, and click 'Enable'.",
    )
    input("  Press Enter once the Firestore database is created...")

    # Step 3: Generate service account key
    offer_url(
        f"https://console.firebase.google.com/project/{project_id}/settings/serviceaccounts/adminsdk",
        "Click 'Generate new private key' and download the JSON file.",
    )
    path = prompt("Path to the downloaded JSON file")
    path = os.path.expanduser(path)

    if os.path.exists(path):
        try:
            creds = json.loads(Path(path).read_text())
            if creds.get("type") == "service_account":
                print_success("Credentials validated.")
                config["FIREBASE_CREDENTIALS_PATH"] = path
                config["FIREBASE_CREDENTIALS_JSON"] = Path(path).read_text()
            else:
                print_warning("File doesn't look like a service account key, saving path anyway.")
                config["FIREBASE_CREDENTIALS_PATH"] = path
        except json.JSONDecodeError:
            print_warning("File is not valid JSON, saving path anyway.")
            config["FIREBASE_CREDENTIALS_PATH"] = path
    else:
        print_warning(f"File not found: {path}. Saving path anyway.")
        config["FIREBASE_CREDENTIALS_PATH"] = path

    return config


def setup_firebase_existing(config):
    print_step("Existing Firebase Credentials")

    config["FIREBASE_PROJECT_ID"] = prompt(
        "Firebase Project ID", default=config.get("FIREBASE_PROJECT_ID"))

    method = prompt_choice("How do you want to provide credentials?", [
        "Path to service account JSON file",
        "Paste JSON content directly",
    ])

    if method == 0:
        path = prompt("Path to JSON file", default=config.get("FIREBASE_CREDENTIALS_PATH"))
        path = os.path.expanduser(path)
        config["FIREBASE_CREDENTIALS_PATH"] = path
        if os.path.exists(path):
            config["FIREBASE_CREDENTIALS_JSON"] = Path(path).read_text()
            print_success("Credentials loaded.")
    else:
        print("  Paste the entire JSON content (then press Enter on a blank line):")
        lines = []
        while True:
            line = input()
            if not line.strip():
                break
            lines.append(line)
        json_str = "\n".join(lines)
        try:
            json.loads(json_str)
            config["FIREBASE_CREDENTIALS_JSON"] = json_str
            print_success("Credentials validated.")
        except json.JSONDecodeError:
            print_warning("Invalid JSON, saving anyway.")
            config["FIREBASE_CREDENTIALS_JSON"] = json_str

    return config


def setup_scheduler(config):
    print_header("Scheduler Configuration")

    mode = prompt_choice("How will the bot be triggered?", [
        "Run on this machine (local or Docker)",
        "Triggered from outside (e.g. GitHub Actions, cloud)",
    ])
    config["SCHEDULER_MODE"] = "internal" if mode == 0 else "external"

    if mode == 0:
        when = prompt_choice("When should rebalancing run?", [
            "Monday 9:30 AM New York (market open) — recommended",
            "Custom (enter cron expression)",
        ])
        if when == 0:
            config["CRON_SCHEDULE"] = "30 9 * * 1"
            config["SCHEDULER_TIMEZONE"] = "America/New_York"
        else:
            config["CRON_SCHEDULE"] = prompt(
                "Cron schedule (minute hour day month day_of_week)",
                default=config.get("CRON_SCHEDULE", "30 9 * * 1"),
            )
            config["SCHEDULER_TIMEZONE"] = prompt(
                "Timezone for schedule (e.g. America/New_York)",
                default=config.get("SCHEDULER_TIMEZONE", "America/New_York"),
            )
    else:
        print("  Run time is set where you trigger the bot (e.g. GitHub Actions workflow).")
        print("  This repo's workflow runs at Monday 9:30 AM New York (market open).\n")
        config["WEBHOOK_PORT"] = prompt(
            "Webhook port", default=config.get("WEBHOOK_PORT", "8080"))
        if prompt_yes_no("Set a webhook secret? (recommended)", default=True):
            config["WEBHOOK_SECRET"] = prompt_secret(
                "Webhook secret", existing=config.get("WEBHOOK_SECRET"))

    return config


# ---------------------------------------------------------------------------
# .env file output
# ---------------------------------------------------------------------------

def write_env_file(config, overwrite=False):
    env_path = PROJECT_ROOT / ".env"

    if env_path.exists() and not overwrite:
        if not prompt_yes_no(f"{env_path} already exists. Overwrite?", default=False):
            alt = PROJECT_ROOT / ".env.generated"
            env_path = alt
            print(f"  Writing to {alt} instead.")

    lines = [
        "# =============================================================================",
        "# QMS Trading Bot Configuration",
        f"# Generated by setup wizard on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "# =============================================================================",
        "",
    ]

    def add_section(title, keys):
        lines.append(f"# {title}")
        for k in keys:
            if k in config:
                lines.append(f"{k}={config[k]}")
        lines.append("")

    add_section("Leaderboard API", ["LEADERBOARD_API_URL", "LEADERBOARD_API_TOKEN"])

    broker = config.get("BROKER_TYPE", "alpaca")
    broker_keys = {
        "alpaca": ["BROKER_TYPE", "ALPACA_API_KEY", "ALPACA_API_SECRET", "ALPACA_BASE_URL"],
        "robinhood": ["BROKER_TYPE", "ROBINHOOD_USERNAME", "ROBINHOOD_PASSWORD", "ROBINHOOD_MFA_CODE"],
        "webull": ["BROKER_TYPE", "WEBULL_APP_KEY", "WEBULL_APP_SECRET", "WEBULL_ACCOUNT_ID", "WEBULL_REGION"],
        "tradier": ["BROKER_TYPE", "TRADIER_ACCESS_TOKEN", "TRADIER_ACCOUNT_ID", "TRADIER_BASE_URL"],
    }
    add_section(f"Broker Configuration ({BROKER_INFO[broker]['name']})", broker_keys.get(broker, []))

    trading_keys = ["INITIAL_CAPITAL", "TRADE_INDICES"]
    for idx in INDEX_OPTIONS:
        k = f"INITIAL_CAPITAL_{idx}"
        if k in config:
            trading_keys.append(k)
    add_section("Trading Configuration", trading_keys)

    add_section("Scheduler", [
        "SCHEDULER_MODE", "CRON_SCHEDULE", "SCHEDULER_TIMEZONE", "WEBHOOK_PORT", "WEBHOOK_SECRET",
    ])

    email_keys = ["EMAIL_ENABLED"]
    if config.get("EMAIL_ENABLED") == "true":
        email_keys.extend(["EMAIL_RECIPIENT", "EMAIL_PROVIDER"])
        provider = config.get("EMAIL_PROVIDER", "smtp")
        if provider == "smtp":
            email_keys.extend(["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL"])
        elif provider == "sendgrid":
            email_keys.extend(["SENDGRID_API_KEY", "SENDGRID_FROM_EMAIL"])
        elif provider == "ses":
            email_keys.extend(["AWS_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "SES_FROM_EMAIL"])
    add_section("Email Notifications", email_keys)

    persistence_keys = ["PERSISTENCE_ENABLED"]
    if config.get("PERSISTENCE_ENABLED") == "true":
        persistence_keys.extend(["FIREBASE_PROJECT_ID", "FIREBASE_CREDENTIALS_PATH"])
        if config.get("FIRESTORE_DATABASE_ID"):
            persistence_keys.append("FIRESTORE_DATABASE_ID")
        if config.get("PERSISTENCE_COLLECTION_PREFIX"):
            persistence_keys.append("PERSISTENCE_COLLECTION_PREFIX")
    add_section("Persistence", persistence_keys)

    env_path.write_text("\n".join(lines) + "\n")
    os.chmod(env_path, stat.S_IRUSR | stat.S_IWUSR)
    print_success(f"Configuration written to {env_path}")


# ---------------------------------------------------------------------------
# GitHub Actions output
# ---------------------------------------------------------------------------

def _keys_for_sections(section_names):
    """Return set of env var names that belong to the given sections (for partial push)."""
    out = set()
    for name in section_names:
        out.update(SECTION_KEYS.get(name, set()))
    # INITIAL_CAPITAL_* from config are included in push_vars when "INITIAL_CAPITAL" is in only_keys
    return out


def push_to_github(config, env_name_override=None, only_keys=None):
    if not check_cli("gh"):
        print_error("GitHub CLI (gh) is not installed.")
        offer_url(
            "https://cli.github.com/",
            "Install gh CLI to push secrets and variables to GitHub.",
        )
        return False

    result = run_cmd("gh auth status")
    if result and result.returncode != 0:
        print_error("Not authenticated with gh CLI.")
        print("  Run: gh auth login")
        if prompt_yes_no("Authenticate now? (opens browser)", default=True):
            run_cmd("gh auth login", capture=False)
            result = run_cmd("gh auth status")
            if not result or result.returncode != 0:
                print_error("Authentication failed or incomplete.")
                return False
            print_success("Authenticated.")
        else:
            return False

    repo = get_gh_repo()
    if not repo:
        print_error("Could not detect GitHub repository. Run this from within a git repo.")
        return False
    print(f"  Repository: {repo}")

    # Environment selection (skip if override provided)
    if env_name_override is not None:
        env_names = [env_name_override]
        print(f"  Target environment: {env_name_override}")
    else:
        env_names = prompt_github_environments(repo)
        if not env_names:
            print_warning("No environment selected. Skipping push.")
            return False
        print(f"  Target environment(s): {', '.join(e or 'repo-level' for e in env_names)}")

    ALL_PUSH_KEYS = {
        "LEADERBOARD_API_URL", "LEADERBOARD_API_TOKEN",
        "BROKER_TYPE",
        "ALPACA_API_KEY", "ALPACA_API_SECRET", "ALPACA_BASE_URL",
        "ROBINHOOD_USERNAME", "ROBINHOOD_PASSWORD", "ROBINHOOD_MFA_CODE",
        "WEBULL_APP_KEY", "WEBULL_APP_SECRET", "WEBULL_ACCOUNT_ID", "WEBULL_REGION",
        "TRADIER_ACCESS_TOKEN", "TRADIER_ACCOUNT_ID", "TRADIER_BASE_URL",
        "INITIAL_CAPITAL", "TRADE_INDICES",
        "EMAIL_ENABLED", "EMAIL_RECIPIENT", "EMAIL_PROVIDER",
        "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL",
        "SENDGRID_API_KEY", "SENDGRID_FROM_EMAIL",
        "AWS_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "SES_FROM_EMAIL",
        "FIREBASE_PROJECT_ID", "FIREBASE_CREDENTIALS_JSON",
        "PERSISTENCE_ENABLED", "FIRESTORE_DATABASE_ID", "PERSISTENCE_COLLECTION_PREFIX",
        "SCHEDULER_MODE", "CRON_SCHEDULE", "SCHEDULER_TIMEZONE", "WEBHOOK_PORT", "WEBHOOK_SECRET",
    }

    # Build the set of vars to push (optionally restricted to only_keys for partial update)
    push_vars = {}
    for k, v in config.items():
        if k == "FIREBASE_CREDENTIALS_PATH":
            continue
        if only_keys is not None:
            if k not in only_keys and not (k.startswith("INITIAL_CAPITAL_") and "INITIAL_CAPITAL" in only_keys):
                continue
        if k.startswith("INITIAL_CAPITAL_") or k in ALL_PUSH_KEYS:
            push_vars[k] = v

    errors = 0
    for env_name in env_names:
        env_flag = f" --env {env_name}" if env_name else ""
        label = (env_name or "repo-level")
        print(f"\n  Pushing {len(push_vars)} settings to GitHub → {label}...")

        for key, value in push_vars.items():
            is_secret = key in SECRETS
            cmd_type = "secret" if is_secret else "variable"
            result = run_cmd(f'gh {cmd_type} set {key}{env_flag} --body "{_shell_escape(value)}"')
            if result and result.returncode == 0:
                lbl = "secret" if is_secret else "var"
                print(f"    {lbl:>6}  {key}")
            else:
                print_error(f"Failed to set {key}")
                errors += 1

        # Set FORCE_RUN default only when doing full push (not partial update)
        if only_keys is None:
            run_cmd(f'gh variable set FORCE_RUN{env_flag} --body "false"')

        if env_name and only_keys is None:
            _update_active_environments(env_name, add=True)

    # Offer to disable the original workflow once, after all pushes
    if only_keys is None and any(env_names) and not errors:
        result = run_cmd('gh workflow list --json name,state -q ".[] | select(.name==\\"Trading Bot Rebalancing\\") | .state"')
        if result and result.stdout.strip() == "active":
            if prompt_yes_no("Disable the original 'Trading Bot Rebalancing' workflow? (environments workflow replaces it)"):
                run_cmd('gh workflow disable "Trading Bot Rebalancing"')
                print_success("Original workflow disabled.")

    if errors:
        print_warning(f"{errors} setting(s) failed. Check gh CLI authentication and permissions.")
        return False
    print_success("All settings pushed to GitHub!")
    return True


def _shell_escape(value):
    return value.replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")


def prompt_github_environment(repo):
    """Single environment (backward compatibility). Returns env name or None for repo-level."""
    envs = prompt_github_environments(repo)
    return envs[0] if envs else None


def prompt_github_environments(repo):
    """Multi-select: returns list of env names (str) or None for repo-level. Creates missing envs."""
    result = run_cmd(f'gh api repos/{repo}/environments --jq ".environments[].name"')
    existing = result.stdout.strip().split("\n") if result and result.stdout.strip() else []
    existing = [n.strip() for n in existing if n.strip()]

    # List all existing repo environments, then Custom + repo-level
    options = [f"{name} (existing)" for name in existing]
    options.append("Custom name...")
    options.append("No environment (repo-level)")

    choice_indices = prompt_multi_choice("Which GitHub Environment(s) should these settings go to?", options)
    env_names = []
    n_existing = len(existing)
    custom_idx = n_existing
    repo_level_idx = n_existing + 1

    for idx in choice_indices:
        if idx < n_existing:
            env_names.append(existing[idx])
        elif idx == custom_idx:
            raw = prompt("Environment name(s), comma-separated:").strip()
            for name in (n.strip() for n in raw.split(",") if n.strip()):
                if name and name not in env_names:
                    env_names.append(name)
        else:
            # No environment (repo-level)
            env_names.append(None)

    # Dedupe and create any new environments
    seen = set()
    unique = []
    for name in env_names:
        if name in seen:
            continue
        seen.add(name)
        unique.append(name)
        if name is not None and name not in existing:
            print(f"  Creating environment '{name}'...")
            run_cmd(f"gh api repos/{repo}/environments/{name} -X PUT --silent")
            print_success(f"Environment '{name}' created.")

    return unique


# ---------------------------------------------------------------------------
# Environment management
# ---------------------------------------------------------------------------

def _get_active_environments():
    result = run_cmd("gh variable get ACTIVE_ENVIRONMENTS 2>/dev/null")
    if result and result.returncode == 0 and result.stdout.strip():
        return [e.strip() for e in result.stdout.strip().split(",") if e.strip()]
    return []


def _set_active_environments(envs):
    value = ",".join(envs)
    run_cmd(f'gh variable set ACTIVE_ENVIRONMENTS --body "{value}"')


def _update_active_environments(env_name, add=True):
    active = _get_active_environments()
    if add and env_name not in active:
        active.append(env_name)
        _set_active_environments(active)
        print_success(f"Added '{env_name}' to ACTIVE_ENVIRONMENTS: {','.join(active)}")
    elif not add and env_name in active:
        active.remove(env_name)
        _set_active_environments(active)
        print_success(f"Removed '{env_name}' from ACTIVE_ENVIRONMENTS: {','.join(active) or '(none)'}")


def github_list_environments():
    if not check_cli("gh"):
        print_error("GitHub CLI (gh) is not installed.")
        return

    repo = get_gh_repo()
    if not repo:
        print_error("Could not detect GitHub repository.")
        return

    result = run_cmd(f'gh api repos/{repo}/environments --jq ".environments[].name"')
    all_envs = result.stdout.strip().split("\n") if result and result.stdout.strip() else []
    active = _get_active_environments()

    print_header("GitHub Environments")
    if not all_envs:
        print("  No environments configured.")
        print("  Run: python scripts/setup.py --github")
        return

    for env in all_envs:
        status = "active" if env in active else "disabled"
        print(f"  {env:<20} [{status}]")

    print(f"\n  ACTIVE_ENVIRONMENTS = {','.join(active) or '(not set)'}")


def github_disable_environment(env_name):
    if not check_cli("gh"):
        print_error("GitHub CLI (gh) is not installed.")
        return
    _update_active_environments(env_name, add=False)
    print(f"  '{env_name}' will no longer run on schedule.")
    print(f"  Secrets and variables are preserved. Re-enable with: --enable {env_name}")


def github_enable_environment(env_name):
    if not check_cli("gh"):
        print_error("GitHub CLI (gh) is not installed.")
        return
    _update_active_environments(env_name, add=True)
    print(f"  '{env_name}' will now run on schedule.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SECTION_HANDLERS = {
    "leaderboard": setup_leaderboard,
    "broker": setup_broker,
    "trading": setup_trading,
    "email": setup_email,
    "persistence": setup_persistence,
    "scheduler": setup_scheduler,
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="QMS Trading Bot Setup Wizard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python scripts/setup.py                        Interactive setup
  python scripts/setup.py --env                  Generate .env file
  python scripts/setup.py --github               Push to GitHub Actions
  python scripts/setup.py --github --env         Both
  python scripts/setup.py --update broker        Update only broker section (from .env)
  python scripts/setup.py --update               Prompt for sections (and GitHub env if pushing)
  python scripts/setup.py --update email,scheduler --env
  python scripts/setup.py --update broker --github -e paper   Update broker in 'paper' env only
  python scripts/setup.py --github --list        List environments
  python scripts/setup.py --github --disable live
  python scripts/setup.py --github --enable live
        """,
    )
    parser.add_argument("--env", action="store_true", help="Generate .env file")
    parser.add_argument("--github", action="store_true", help="Push to GitHub Actions")
    parser.add_argument("--update", nargs="?", const="", metavar="SECTIONS", help="Update only certain sections. If SECTIONS omitted, prompts for sections (and env if --github). Use comma-separated: leaderboard, broker, trading, email, persistence, scheduler.")
    parser.add_argument("--environment", "-e", metavar="ENV", dest="target_environment", help="Target GitHub environment (e.g. paper, live). Use with --update --github to update that environment without prompting.")
    parser.add_argument("--list", action="store_true", help="List GitHub environments")
    parser.add_argument("--disable", metavar="ENV", help="Disable a GitHub environment from scheduled runs")
    parser.add_argument("--enable", metavar="ENV", help="Enable a GitHub environment for scheduled runs")
    return parser.parse_args()


def main():
    print_header("QMS Trading Bot Setup Wizard")
    args = parse_args()

    # Quick commands that don't need full setup
    if args.list:
        return github_list_environments()
    if args.disable:
        return github_disable_environment(args.disable)
    if args.enable:
        return github_enable_environment(args.enable)

    # Update-only mode: load .env, run selected sections, write back
    if args.update is not None:
        config = load_config_from_env()
        if not config:
            print_warning("No .env found; you'll be prompted for all values in the chosen sections.")
        if args.update.strip():
            sections_to_run = [s.strip().lower() for s in args.update.split(",") if s.strip()]
            unknown = [s for s in sections_to_run if s not in SECTION_HANDLERS]
            if unknown:
                print_error(f"Unknown section(s): {unknown}. Valid: {list(SECTION_HANDLERS.keys())}")
                sys.exit(1)
        else:
            # Prompt for which sections to update
            section_indices = prompt_multi_choice("Which section(s) to update?", SECTIONS)
            sections_to_run = [SECTIONS[i] for i in section_indices]
        for section in sections_to_run:
            config = SECTION_HANDLERS[section](config)
        write_env_file(config, overwrite=True)
        if args.github:
            only_keys = _keys_for_sections(sections_to_run)
            push_to_github(
                config,
                env_name_override=args.target_environment,
                only_keys=only_keys,
            )
        elif prompt_yes_no("Push updates to GitHub?", default=False):
            only_keys = _keys_for_sections(sections_to_run)
            push_to_github(
                config,
                env_name_override=args.target_environment,
                only_keys=only_keys,
            )
        else:
            print_success("Updated .env. Use --github to push these changes to GitHub.")
        return

    config = {}
    start_section = 0

    # Check for resume
    if PROGRESS_FILE.exists():
        completed_sections = []
        saved_config, saved_index = load_progress()
        for i, s in enumerate(SECTIONS):
            if i < saved_index:
                completed_sections.append(s)

        next_section = SECTIONS[saved_index] if saved_index < len(SECTIONS) else "output"
        print(f"  Found saved progress ({len(completed_sections)}/{len(SECTIONS)} sections complete).")
        print(f"  Completed: {', '.join(completed_sections) or 'none'}")
        print(f"  Next: {next_section}\n")

        choice = prompt_choice("What would you like to do?", [
            f"Resume from '{next_section}'",
            "Start over",
            "Edit a specific section",
        ])

        if choice == 0:
            config = saved_config
            start_section = saved_index
        elif choice == 1:
            cleanup_progress()
        elif choice == 2:
            config = saved_config
            section_idx = prompt_choice("Which section?", SECTIONS)
            config = SECTION_HANDLERS[SECTIONS[section_idx]](config)
            save_progress(config, saved_index)
            if prompt_yes_no("Continue to output?"):
                start_section = len(SECTIONS)
            else:
                start_section = saved_index
    elif (PROJECT_ROOT / ".env").exists():
        # No progress file but .env exists: offer full setup or update specific sections
        choice = prompt_choice("What would you like to do?", [
            "Full setup (run all sections)",
            "Update specific section(s) only",
        ])
        if choice == 1:
            config = load_config_from_env()
            section_indices = prompt_multi_choice("Which section(s) to update?", SECTIONS)
            for idx in section_indices:
                config = SECTION_HANDLERS[SECTIONS[idx]](config)
            write_env_file(config, overwrite=True)
            if prompt_yes_no("Push updates to GitHub?", default=False):
                push_to_github(config)
            else:
                print_success("Updated .env.")
            return

    # Run remaining sections
    for i, section in enumerate(SECTIONS):
        if i < start_section:
            continue
        config = SECTION_HANDLERS[section](config)
        save_progress(config, i + 1)

    # Output
    print_header("Output")

    if args.github or args.env:
        if args.env:
            write_env_file(config)
        if args.github:
            if not push_to_github(config) and not args.env:
                if prompt_yes_no("Save to .env file instead? (run setup again later for GitHub)"):
                    write_env_file(config)
    else:
        output = prompt_choice("Where should the configuration be saved?", [
            ".env file (for local development)",
            "GitHub Actions (secrets + variables)",
            "Both",
        ])
        if output in (0, 2):
            write_env_file(config)
        if output in (1, 2):
            if not push_to_github(config):
                if prompt_yes_no("Save to .env file instead? (you can run setup again later for GitHub)"):
                    write_env_file(config)

    cleanup_progress()
    print_header("Setup Complete!")
    python = sys.executable
    print("  Before running the bot, install dependencies:")
    print()
    print(f"    {python} -m pip install -r requirements.txt")
    print()
    print("  Or for just the scripts (validation, Firebase verification):")
    print()
    print(f"    {python} -m pip install -r scripts/requirements.txt")
    print()
    print("  Next steps:")
    print(f"    1. Validate:  {python} scripts/validate-config.py")
    print(f"    2. Test:      {python} scripts/test-connection.py")
    print(f"    3. Run:       {python} -m src.main")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Setup interrupted. Progress saved. Run again to resume.\n")
        sys.exit(1)
