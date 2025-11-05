"""Module with trading strategies."""
import logging
import time
from typing import List, cast, Any, Optional

import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from data_loader import DataLoader
from utils import retry_on_exception, get_positions


class MomentumStrategy:
    """Class implementing momentum-based trading strategy."""

    def __init__(self, trading_client: TradingClient, tickers: List[str],
                 telegram_bot: Optional[Any] = None):
        """Initialize strategy.

        Args:
            trading_client: Alpaca API client
            tickers: List of tickers for trading
            telegram_bot: Optional TelegramBot instance for error notifications
        """
        self.trading_client = trading_client
        self.tickers = tickers
        self.telegram_bot = telegram_bot

    @retry_on_exception()
    def get_signals(self) -> List[str]:
        """Get trading signals - top 10 stocks by momentum.

        Returns:
            List[str]: List of tickers with highest momentum
        """
        try:
            data = DataLoader.load_market_data(self.tickers, period="1y", telegram_bot=self.telegram_bot)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Send notification on data loading error
            if self.telegram_bot:
                error_str = str(exc)
                self.telegram_bot.send_error_notification_sync(
                    "Data Loading Failed",
                    f"Error loading market data from yfinance:\n<code>{error_str}</code>"
                )
            raise

        if data is None:
            raise KeyError("'Close' column not found in data")
        if data.empty or 'Close' not in data.columns:  # type: ignore[union-attr]
            raise KeyError("'Close' column not found in data")

        data = cast(pd.DataFrame, data)  # type: ignore[assignment]
        return (data['Close']  # type: ignore[index]
                .dropna(axis='columns')  # type: ignore[call-overload]
                .pct_change(periods=len(data)-1)  # type: ignore[no-untyped-call]
                .iloc[-1]  # type: ignore[attr-defined]
                .nlargest(10)  # type: ignore[attr-defined]
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
            error_details = "\n".join([
                f"  • {ticker}: {error.split(chr(10))[0]}"
                for ticker, error in failed_closures
            ])
            logging.warning(
                "Failed to close %d position(s): %s",
                len(failed_closures),
                [(t, e.split('\n')[0]) for t, e in failed_closures]
            )
            if self.telegram_bot:
                self.telegram_bot.send_error_notification_sync(
                    "Failed to Close Positions",
                    f"Failed to close {len(failed_closures)} position(s):\n{error_details}",
                    is_warning=True
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
            error_details = "\n".join([
                f"  • {ticker}: {error.split(chr(10))[0]}"
                for ticker, error in failed_opens
            ])
            logging.warning(
                "Failed to open %d position(s): %s",
                len(failed_opens),
                [(t, e.split('\n')[0]) for t, e in failed_opens]
            )
            if self.telegram_bot:
                self.telegram_bot.send_error_notification_sync(
                    "Failed to Open Positions",
                    f"Failed to open {len(failed_opens)} position(s):\n{error_details}",
                    is_warning=True
                )

    def rebalance(self) -> None:
        """Rebalance portfolio."""
        try:
            logging.info("Starting portfolio rebalancing")

            # Get trading strategy signals
            top_tickers = self.get_signals()
            logging.info("Top 10 stocks by momentum: %s", ', '.join(top_tickers))

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
                account = self.trading_client.get_account()  # type: ignore[no-untyped-call]
                cash_value = getattr(account, 'cash', 0.0)  # type: ignore[attr-defined]
                available_cash = float(cast(float, cash_value))  # type: ignore[arg-type]
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
