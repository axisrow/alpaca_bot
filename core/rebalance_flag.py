"""Rebalance flag management module with functional programming approach."""
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import pytz

# New York timezone constant
NY_TIMEZONE = pytz.timezone('America/New_York')

# Default flag path
DEFAULT_FLAG_PATH = Path("data/last_rebalance.txt")


def create_rebalance_flag_state(flag_path: Path = DEFAULT_FLAG_PATH) -> Dict[str, Any]:
    """Create rebalance flag state dictionary.

    Args:
        flag_path: Path to rebalance flag file

    Returns:
        Rebalance flag state dictionary
    """
    return {
        'flag_path': flag_path
    }


def get_last_rebalance_date(state: Dict[str, Any]) -> Optional[datetime]:
    """Get the date of last rebalance.

    Args:
        state: Rebalance flag state

    Returns:
        Last rebalance date or None
    """
    flag_path = state['flag_path']
    if not flag_path.exists():
        return None
    try:
        date_str = flag_path.read_text(encoding='utf-8').strip()
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=NY_TIMEZONE)
    except ValueError:
        import logging
        logging.error("Invalid date format in rebalance file")
        return None


def has_rebalanced_today(state: Dict[str, Any]) -> bool:
    """Check if rebalancing has occurred today.

    Args:
        state: Rebalance flag state

    Returns:
        True if rebalanced today, False otherwise
    """
    flag_path = state['flag_path']
    if not flag_path.exists():
        return False
    today_ny = datetime.now(NY_TIMEZONE).strftime("%Y-%m-%d")
    return flag_path.read_text(encoding='utf-8').strip() == today_ny


def write_flag(state: Dict[str, Any]) -> None:
    """Write rebalance flag.

    Args:
        state: Rebalance flag state
    """
    flag_path = state['flag_path']
    flag_path.parent.mkdir(parents=True, exist_ok=True)
    today_ny = datetime.now(NY_TIMEZONE).strftime("%Y-%m-%d")
    flag_path.write_text(today_ny, encoding='utf-8')


def get_countdown_message(days_until: int, next_date: datetime) -> str:
    """Get formatted countdown message for rebalancing.

    Args:
        days_until: Number of trading days until rebalancing
        next_date: Next rebalance date

    Returns:
        Formatted HTML message
    """
    now_ny = datetime.now(NY_TIMEZONE)

    if days_until == 0:
        return (
            "⏰ <b>Rebalancing today!</b>\n\n"
            f"🕐 Time (NY): {now_ny.strftime('%H:%M:%S')}\n"
            "🔄 Portfolio will be rebalanced to top 10 S&P 500 stocks\n"
        )

    formatted_date = next_date.strftime("%Y-%m-%d")
    return (
        f"📊 <b>Rebalancing countdown</b>\n\n"
        f"📅 Days remaining: <b>{days_until}</b> trading days\n"
        f"⏱️ Next rebalance: <b>{formatted_date}</b> at 10:00 AM (NY)\n"
        f"🕐 Current time (NY): {now_ny.strftime('%H:%M:%S')}\n"
    )
