"""Momentum strategy for paper_medium (top-10 S&P 500)."""
import config
from strategies.base import BaseMomentumStrategy


class PaperMediumStrategy(BaseMomentumStrategy):
    """Momentum-based trading strategy for paper_medium account.

    Configuration:
    - Universe: S&P 500 stocks only
    - Top stocks: 10
    - Account: Paper trading (MEDIUM)
    """

    # Strategy configuration
    API_KEY = config.ALPACA_API_KEY_MEDIUM
    SECRET_KEY = config.ALPACA_SECRET_KEY_MEDIUM
    PAPER = True
    TOP_COUNT = 10
    ENABLED = True
    TICKERS = 'snp500_only'  # SNP500 + CUSTOM tickers
