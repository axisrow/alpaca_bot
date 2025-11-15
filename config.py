"""Application configuration and constants."""
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Environment (local, prod)
ENVIRONMENT = os.getenv("ENVIRONMENT", "prod")

# Market data & cache configuration (fixed, not env-driven)
CACHE_DIR = Path("data")
CACHE_FILE = CACHE_DIR / "cache.pkl"
CACHE_VALIDITY_HOURS = 24
MARKET_DATA_PERIOD = "1y"
MARKET_DATA_MAX_RETRIES = 3
MARKET_DATA_RETRY_DELAY_SECONDS = 2
MARKET_DATA_ENABLE_RETRY = True

# Telegram bot token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set in .env file")

# List of admin IDs for notifications
# NOTE: These should be in config, not .env, as they don't depend on environment
ADMIN_IDS = [169675602, 7035744629]

# Rebalancing interval in trading days
REBALANCE_INTERVAL_DAYS = 22

# Load tickers from JSON file
_TICKERS_FILE = Path(__file__).parent / "tickers.json"
with open(_TICKERS_FILE, "r", encoding="utf-8") as f:
    _TICKERS = json.load(f)

# Custom tickers to add to S&P 500 list
CUSTOM_TICKERS = _TICKERS["custom"]

# Medium risk tickers (reserved for future strategy extensions)
MEDIUM_TICKERS = _TICKERS["medium"]

# S&P 500 tickers list
SNP500_TICKERS = _TICKERS["snp500"]

# High volatility tickers for aggressive strategies
HIGH_TICKERS = _TICKERS["high"]

# Alpaca API keys for paper_medium account
ALPACA_API_KEY_MEDIUM = os.getenv("ALPACA_API_KEY_MEDIUM", "")
ALPACA_SECRET_KEY_MEDIUM = os.getenv("ALPACA_SECRET_KEY_MEDIUM", "")

# Alpaca API keys for primary account
ALPACA_API_KEY_LOW = os.getenv("ALPACA_API_KEY_LOW", "")
ALPACA_SECRET_KEY_LOW = os.getenv("ALPACA_SECRET_KEY_LOW", "")

# Alpaca API keys for live account
ALPACA_API_KEY_LIVE = os.getenv("ALPACA_API_KEY_LIVE", "")
ALPACA_SECRET_KEY_LIVE = os.getenv("ALPACA_SECRET_KEY_LIVE", "")

# Alpaca API keys for paper_high account
ALPACA_API_KEY_HIGH = os.getenv("ALPACA_API_KEY_HIGH", "")
ALPACA_SECRET_KEY_HIGH = os.getenv("ALPACA_SECRET_KEY_HIGH", "")
