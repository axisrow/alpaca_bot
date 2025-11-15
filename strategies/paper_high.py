"""Momentum strategy for paper_high (top-50 all tickers)."""
import config
from strategies.base import create_strategy_config

# Strategy configuration
API_KEY = config.ALPACA_API_KEY_HIGH
SECRET_KEY = config.ALPACA_SECRET_KEY_HIGH
PAPER = True
TOP_COUNT = 50
ENABLED = True
TICKERS = 'all'  # SNP500 + MEDIUM + CUSTOM tickers


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
