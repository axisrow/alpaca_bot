"""Market schedule management module with functional programming approach."""
import logging
from datetime import datetime, time as dt_time, timedelta
from typing import Tuple, Dict, Any

from alpaca.trading.client import TradingClient
import pytz

# Constants
NY_TIMEZONE = pytz.timezone('America/New_York')
MARKET_OPEN = dt_time(9, 30)
MARKET_CLOSE = dt_time(16, 0)


def create_market_schedule_state(trading_client: TradingClient) -> Dict[str, Any]:
    """Create market schedule state dictionary.

    Args:
        trading_client: Alpaca API client

    Returns:
        Market schedule state dictionary
    """
    return {
        'trading_client': trading_client
    }


def get_current_ny_time() -> datetime:
    """Get current time in New York timezone.

    Returns:
        Current datetime in NY timezone
    """
    return datetime.now(NY_TIMEZONE)


def check_market_status(state: Dict[str, Any]) -> Tuple[bool, str]:
    """Check market status.

    Args:
        state: Market schedule state dictionary

    Returns:
        Tuple of (market_open_status, reason)
    """
    now = get_current_ny_time()
    current_time = now.time()

    if now.weekday() > 4:
        return False, "weekend (Saturday/Sunday)"

    try:
        clock = state['trading_client'].get_clock()
        if clock.is_open:  # type: ignore
            return True, "market is open"

        if MARKET_OPEN <= current_time <= MARKET_CLOSE:
            return False, "holiday"
        return (False,
                f"outside trading hours {MARKET_OPEN}-{MARKET_CLOSE}")

    except Exception as exc:
        logging.error("Error checking market status: %s", exc)
        return False, str(exc)


def is_open(state: Dict[str, Any]) -> bool:
    """Check if market is open.

    Args:
        state: Market schedule state dictionary

    Returns:
        True if market is open, False otherwise
    """
    status, reason = check_market_status(state)
    if not status:
        logging.info("Market is closed: %s", reason)
    return status


def count_trading_days(start_date: datetime, end_date: datetime) -> int:
    """Count trading days between two dates.

    Args:
        start_date: Start date (not inclusive)
        end_date: End date (inclusive)

    Returns:
        Number of trading days (weekdays only)
    """
    # Add NY timezone if dates don't have one
    start_date = start_date if start_date.tzinfo else NY_TIMEZONE.localize(start_date)
    end_date = end_date if end_date.tzinfo else NY_TIMEZONE.localize(end_date)

    start, end = start_date.date(), end_date.date()
    return sum(
        1 for day_offset in range(1, (end - start).days + 1)
        if (start + timedelta(days=day_offset)).weekday() < 5
    )
