"""Momentum strategy for paper_high (top-50 all tickers)."""
import config
from strategies.base import BaseMomentumStrategy


class PaperHighStrategy(BaseMomentumStrategy):
    """Momentum-based trading strategy for paper_high account.

    Configuration:
    - Universe: All tickers (S&P 500 + MEDIUM + CUSTOM)
    - Top stocks: 50
    - Account: Paper trading (HIGH)
    """

    # Strategy configuration
    API_KEY = config.ALPACA_API_KEY_HIGH
    SECRET_KEY = config.ALPACA_SECRET_KEY_HIGH
    PAPER = True
    TOP_COUNT = 50
    ENABLED = True
    TICKERS = 'all'  # SNP500 + MEDIUM + CUSTOM tickers
