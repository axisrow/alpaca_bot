"""Rebalance flag management module."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytz

# New York timezone constant
NY_TIMEZONE = pytz.timezone('America/New_York')


@dataclass
class RebalanceFlag:
    """Class for managing rebalance flag."""

    flag_path: Path = Path("data/last_rebalance.txt")

    def get_last_rebalance_date(self) -> datetime | None:
        """Get the date of last rebalance.

        Returns:
            datetime | None: Last rebalance date or None
        """
        if not self.flag_path.exists():
            return None
        try:
            date_str = self.flag_path.read_text(encoding='utf-8').strip()
            return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=NY_TIMEZONE)
        except ValueError:
            import logging
            logging.error("Invalid date format in rebalance file")
            return None

    def has_rebalanced_today(self) -> bool:
        """Check if rebalancing has occurred today."""
        if not self.flag_path.exists():
            return False
        today_ny = datetime.now(NY_TIMEZONE).strftime("%Y-%m-%d")
        return self.flag_path.read_text(encoding='utf-8').strip() == today_ny

    def write_flag(self) -> None:
        """Write rebalance flag."""
        self.flag_path.parent.mkdir(parents=True, exist_ok=True)
        today_ny = datetime.now(NY_TIMEZONE).strftime("%Y-%m-%d")
        self.flag_path.write_text(today_ny, encoding='utf-8')

    def get_countdown_message(self, days_until: int,
                              next_date: datetime) -> str:
        """Get formatted countdown message for rebalancing.

        Args:
            days_until: Number of trading days until rebalancing
            next_date: Next rebalance date

        Returns:
            str: Formatted HTML message
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
