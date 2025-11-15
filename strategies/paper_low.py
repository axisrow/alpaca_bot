"""Momentum strategy for paper_low (top-50 S&P 500)."""
import config
from strategies.base import create_strategy_config

# Strategy configuration
API_KEY = config.ALPACA_API_KEY_LOW
SECRET_KEY = config.ALPACA_SECRET_KEY_LOW
PAPER = True
TOP_COUNT = 50
ENABLED = True
TICKERS = 'snp500_only'  # SNP500 + CUSTOM tickers


def get_config():
    """Get strategy configuration.

    Returns:
        dict: Strategy configuration
    """
    return create_strategy_config(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        paper=PAPER,
        top_count=TOP_COUNT,
        enabled=ENABLED,
        tickers_mode=TICKERS
    )
