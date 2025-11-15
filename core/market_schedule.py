"""Market schedule management module."""
import logging
from datetime import datetime, time as dt_time, timedelta
from typing import Tuple

from alpaca.trading.client import TradingClient

from .rebalance_flag import NY_TIMEZONE


class MarketSchedule:
    """Class for managing market schedule."""

    MARKET_OPEN = dt_time(9, 30)
    MARKET_CLOSE = dt_time(16, 0)

    def __init__(self, trading_client: TradingClient):
        """Initialize with trading client.

        Args:
            trading_client: Alpaca API client
        """
        self.trading_client = trading_client

    @property
    def current_ny_time(self) -> datetime:
        """Current time in New York."""
        return datetime.now(NY_TIMEZONE)

    def check_market_status(self) -> Tuple[bool, str]:
        """Check market status.

        Returns:
            Tuple[bool, str]: Market open status and reason
        """
        now = self.current_ny_time
        current_time = now.time()

        if now.weekday() > 4:
            return False, "weekend (Saturday/Sunday)"

        try:
            clock = self.trading_client.get_clock()
            if clock.is_open:
                return True, "market is open"

            if self.MARKET_OPEN <= current_time <= self.MARKET_CLOSE:
                return False, "holiday"
            return (False,
                    f"outside trading hours {self.MARKET_OPEN}-{self.MARKET_CLOSE}")

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error checking market status: %s", exc)
            return False, str(exc)

    @property
    def is_open(self) -> bool:
        """Check if market is open."""
        if not (status := self.check_market_status())[0]:
            logging.info("Market is closed: %s", status[1])
        return status[0]

    def count_trading_days(self, start_date: datetime, end_date: datetime) -> int:
        """Count trading days between two dates.

        Args:
            start_date: Start date (not inclusive)
            end_date: End date (inclusive)

        Returns:
            int: Number of trading days (weekdays only)
        """
        # Add NY timezone if dates don't have one
        start_date = start_date if start_date.tzinfo else NY_TIMEZONE.localize(start_date)
        end_date = end_date if end_date.tzinfo else NY_TIMEZONE.localize(end_date)

        start, end = start_date.date(), end_date.date()
        return sum(
            1 for day_offset in range(1, (end - start).days + 1)
            if (start + timedelta(days=day_offset)).weekday() < 5
        )
