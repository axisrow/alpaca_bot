"""Momentum strategy for paper_low (top-50 S&P 500)."""
import config
from strategies.base import BaseMomentumStrategy


class PaperLowStrategy(BaseMomentumStrategy):
    """Momentum-based trading strategy for paper_low account.

    Configuration:
    - Universe: S&P 500 stocks only
    - Top stocks: 50
    - Account: Paper trading (LOW)
    """

    # Strategy configuration
    API_KEY = config.ALPACA_API_KEY_LOW
    SECRET_KEY = config.ALPACA_SECRET_KEY_LOW
    PAPER = True
    TOP_COUNT = 50
    ENABLED = True
    TICKERS = 'snp500_only'  # SNP500 + CUSTOM tickers
