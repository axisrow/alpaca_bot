"""Base momentum strategy class."""
import logging
import time
from typing import List, cast

import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from core.data_loader import load_market_data
from core.utils import retry_on_exception, get_positions


class BaseMomentumStrategy:
    """Base class implementing momentum-based trading strategy.

    Subclasses should define:
    - API_KEY: Alpaca API key
    - SECRET_KEY: Alpaca secret key
    - PAPER: Paper trading flag (True/False)
    - TOP_COUNT: Number of top stocks to hold
    - ENABLED: Strategy enabled flag
    - TICKERS: Ticker universe ('snp500_only', 'all', etc.)
    """

    # Default configuration (should be overridden in subclasses)
    API_KEY = ""
    SECRET_KEY = ""
    PAPER = True
    TOP_COUNT = 50
    ENABLED = True
    TICKERS = 'snp500_only'

    def __init__(self, trading_client: TradingClient, tickers: List[str], top_count: int = 50):
        """Initialize strategy.

        Args:
            trading_client: Alpaca API client
            tickers: List of tickers to analyze
            top_count: Number of top stocks to select
        """
        self.trading_client = trading_client
        self.tickers = tickers
        self.top_count = top_count

    @retry_on_exception()
    def get_signals(self) -> List[str]:
        """Get trading signals - top N stocks by momentum from self.tickers only.

        Returns:
            List[str]: List of tickers with highest momentum
        """
        data = load_market_data()

        if data is None or data.empty:
            raise KeyError("'Close' column not found in data")
        if 'Close' not in data.columns.get_level_values(0):
            raise KeyError("'Close' column not found in data")

        data = cast(pd.DataFrame, data)
        # Calculate momentum for all tickers: (last_price / first_price - 1)
        close_prices = data.xs('Close', level=0, axis=1)
        momentum = close_prices.iloc[-1] / close_prices.iloc[0] - 1

        # Cast to Series for type safety
        momentum = cast(pd.Series, momentum)

        # Filter to only tickers in self.tickers, then get top_count
        momentum_filtered = momentum[momentum.index.isin(self.tickers)]
        return (momentum_filtered
                .nlargest(self.top_count)
                .index
                .tolist())

    def close_positions(self, positions: List[str]) -> None:
        """Close specified positions.

        Args:
            positions: List of tickers to close
        """
        failed_closures = []
        for ticker in positions:
            try:
                self.trading_client.close_position(ticker)
                logging.info("Position %s closed", ticker)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.error(
                    "Error closing position %s: %s",
                    ticker,
                    exc,
                    exc_info=True
                )
                failed_closures.append((ticker, str(exc)))

        if failed_closures:
            logging.warning(
                "Failed to close %d position(s): %s",
                len(failed_closures),
                [(t, e.split('\n')[0]) for t, e in failed_closures]
            )

    def open_positions(self, tickers: List[str],
                       cash_per_position: float) -> None:
        """Open new positions.

        Args:
            tickers: List of tickers to open
            cash_per_position: Position size in dollars
        """
        failed_opens = []
        for ticker in tickers:
            try:
                order = MarketOrderRequest(
                    symbol=ticker,
                    notional=round(cash_per_position, 2),
                    side=OrderSide.BUY,
                    type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY
                )
                self.trading_client.submit_order(order)
                logging.info(
                    "Opened position %s for $%.2f",
                    ticker,
                    cash_per_position
                )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.error(
                    "Error opening position %s: %s",
                    ticker,
                    exc,
                    exc_info=True
                )
                failed_opens.append((ticker, str(exc)))

        if failed_opens:
            logging.warning(
                "Failed to open %d position(s): %s",
                len(failed_opens),
                [(t, e.split('\n')[0]) for t, e in failed_opens]
            )

    def rebalance(self) -> None:
        """Rebalance portfolio."""
        try:
            logging.info("Starting portfolio rebalancing")

            # Get trading strategy signals
            top_tickers = self.get_signals()
            logging.info("Top %d stocks by momentum: %s", self.top_count, ', '.join(top_tickers))

            # Get current positions
            current_positions = get_positions(self.trading_client)
            logging.info("Current positions: %s", current_positions)

            # Determine positions to close and open
            top_tickers_set = set(top_tickers)
            current_positions_set = set(current_positions)

            positions_to_close = list(current_positions_set - top_tickers_set)
            positions_to_open = list(top_tickers_set - current_positions_set)

            logging.info("Positions to close: %s", positions_to_close)
            logging.info("Positions to open: %s", positions_to_open)

            # Close unneeded positions
            if positions_to_close:
                self.close_positions(positions_to_close)
                time.sleep(5)

            # Open new positions
            if positions_to_open:
                account = self.trading_client.get_account()
                cash_value = getattr(account, 'cash', 0.0)
                available_cash = float(cast(float, cash_value))
                if available_cash <= 0:
                    logging.warning("Insufficient funds: $%.2f", available_cash)
                    return

                position_size = available_cash / len(positions_to_open)
                if position_size < 1:
                    logging.warning(
                        "Position size too small: $%.2f",
                        position_size
                    )
                    return

                self.open_positions(positions_to_open, position_size)

            logging.info("Portfolio rebalancing completed successfully")

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error during rebalancing: %s", exc, exc_info=True)
