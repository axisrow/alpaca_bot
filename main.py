"""Main module for trading bot with Telegram interface."""
import asyncio
import logging
import os
import signal
import sys
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Dict, Tuple

import pytz
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce, QueryOrderStatus
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

from config import snp500_tickers, TELEGRAM_BOT_TOKEN, ADMIN_IDS
from handlers import setup_router
from strategy import MomentumStrategy
from utils import retry_on_exception, get_positions

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('data/trading_bot.log')
    ]
)

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
            if clock.is_open:  # type: ignore[attr-defined]
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
            if (current_day := start + timedelta(days=day_offset)).weekday() < 5
        )


class PortfolioManager:
    """Class for managing portfolio."""

    def __init__(self, trading_client: TradingClient):
        """Initialize portfolio manager.

        Args:
            trading_client: Alpaca API client
        """
        self.trading_client = trading_client
        self.strategy = MomentumStrategy(self.trading_client, snp500_tickers)

    def get_current_positions(self) -> Dict[str, float]:
        """Get current positions.

        Returns:
            Dict[str, float]: Dictionary of positions {ticker: quantity}
        """
        return get_positions(self.trading_client)


class TradingBot:
    """Main trading bot class."""

    def __init__(self):
        """Initialize trading bot."""
        self._load_environment()
        self.trading_client = self._setup_trading_client()
        self.market_schedule = MarketSchedule(self.trading_client)
        self.portfolio_manager = PortfolioManager(self.trading_client)
        self.rebalance_flag = RebalanceFlag()
        self.scheduler = BackgroundScheduler()
        self.telegram_bot = None  # Will be set after TelegramBot creation

    def set_telegram_bot(self, telegram_bot: object) -> None:
        """Set reference to Telegram bot for notifications.

        Args:
            telegram_bot: TelegramBot instance
        """
        self.telegram_bot = telegram_bot

    def _load_environment(self) -> None:
        """Load environment variables."""
        load_dotenv()
        self.api_key = os.getenv("ALPACA_API_KEY")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY")
        self.base_url = "https://paper-api.alpaca.markets"

        if not all([self.api_key, self.secret_key]):
            logging.error("Missing API keys!")
            sys.exit(1)

    def _setup_trading_client(self) -> TradingClient:
        """Create trading client.

        Returns:
            TradingClient: Configured Alpaca client
        """
        return TradingClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=True,
            url_override=self.base_url
        )

    def perform_rebalance(self) -> None:
        """Perform portfolio rebalancing."""
        from config import REBALANCE_INTERVAL_DAYS

        if self.rebalance_flag.has_rebalanced_today():
            logging.info("Rebalancing already performed today.")
            return

        is_open, reason = self.market_schedule.check_market_status()
        if not is_open:
            logging.info("Rebalancing postponed: %s", reason)
            return

        # Check if 22 trading days have passed since last rebalance
        days_until = self.calculate_days_until_rebalance()
        if days_until > 0:
            logging.info("Rebalancing not required. Days remaining: %d", days_until)
            return

        # Call rebalancing through strategy
        logging.info("Performing portfolio rebalancing...")
        self.portfolio_manager.strategy.rebalance()
        self.rebalance_flag.write_flag()
        logging.info("Rebalancing completed.")

    def start(self) -> None:
        """Start the bot."""
        logging.info("=== Starting trading bot ===")
        is_open, reason = self.market_schedule.check_market_status()
        now_ny = datetime.now(NY_TIMEZONE)
        logging.info("Current time (NY): %s", now_ny.strftime('%Y-%m-%d %H:%M:%S %Z'))
        logging.info("Market status: %s%s",
                     'open' if is_open else 'closed',
                     f" (Reason: {reason})" if not is_open else "")
        if not self.scheduler.running:
            self.scheduler.add_job(
                self.perform_rebalance,
                'cron',
                day_of_week='mon-fri',
                hour=10,
                minute=0,
                timezone=NY_TIMEZONE
            )
            # Add task for daily countdown
            if self.telegram_bot:
                self.scheduler.add_job(
                    self.telegram_bot.send_daily_countdown_sync,
                    'cron',
                    day_of_week='mon-fri',
                    hour=10,
                    minute=0,
                    timezone=NY_TIMEZONE
                )
                logging.info("Countdown task added to schedule")
            self.scheduler.start()
            logging.info("Scheduler started")
        else:
            logging.info("Scheduler already running")
        if is_open:
            logging.info("Starting initial rebalancing...")
            self.perform_rebalance()

    def stop(self) -> None:
        """Stop scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logging.info("Scheduler stopped")

    def get_portfolio_status(self) -> Tuple[Dict[str, float], object, float]:
        """Get detailed portfolio data.

        Returns:
            Tuple: (positions, account, P&L)
        """
        try:
            positions = self.portfolio_manager.get_current_positions()
            account = self.trading_client.get_account()
            all_positions = self.trading_client.get_all_positions()
            account_pnl = sum(float(getattr(pos, 'unrealized_pl', 0)) for pos in all_positions)

            return positions, account, account_pnl

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error retrieving portfolio data: %s", exc)
            return {}, None, 0

    def get_trading_stats(self) -> Dict[str, float]:
        """Get real trading statistics.

        Returns:
            Dict[str, float]: Trading statistics
        """
        try:
            # Get all trades for today
            today = datetime.now(NY_TIMEZONE).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            # Use GetOrdersRequest for filtering
            request = GetOrdersRequest(
                status=QueryOrderStatus.CLOSED,
                after=today
            )
            trades = self.trading_client.get_orders(filter=request)
            trades_today = len(trades)

            # Calculate real P&L
            positions = self.trading_client.get_all_positions()
            total_pnl = sum(float(getattr(pos, 'unrealized_pl', 0)) for pos in positions)

            return {
                "trades_today": trades_today,
                "pnl": total_pnl,
                "win_rate": 0.0  # Simplified version, win_rate requires history analysis
            }
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error retrieving trading statistics: %s", exc)
            return {"trades_today": 0, "pnl": 0.0, "win_rate": 0.0}

    def get_settings(self) -> Dict[str, object]:
        """Get bot settings.

        Returns:
            Dict[str, object]: Settings dictionary
        """
        return {
            "rebalance_time": "10:00 NY",
            "positions_count": 10,
            "mode": "Paper Trading"
        }

    def calculate_days_until_rebalance(self) -> int:
        """Calculate trading days until rebalancing.

        Returns:
            int: Remaining trading days (0 if time to rebalance)
        """
        from config import REBALANCE_INTERVAL_DAYS

        last_date = self.rebalance_flag.get_last_rebalance_date()
        if last_date is None:
            return 0  # Time to rebalance if never done before

        today = datetime.now(NY_TIMEZONE)
        trading_days_passed = self.market_schedule.count_trading_days(last_date, today)

        return max(0, REBALANCE_INTERVAL_DAYS - trading_days_passed)

    def get_next_rebalance_date(self) -> datetime:
        """Get the exact date of next rebalancing.

        Returns:
            datetime: Next rebalance date in NY timezone
        """
        from config import REBALANCE_INTERVAL_DAYS

        last_date = self.rebalance_flag.get_last_rebalance_date()
        if last_date is None:
            # If never rebalanced, next rebalance is today
            return datetime.now(NY_TIMEZONE)

        # Start from the last rebalance date and count forward 22 trading days
        current = last_date.date()
        trading_days = (
            current + timedelta(days=i)
            for i in range(1, 365)
            if (current + timedelta(days=i)).weekday() < 5
        )
        next_date = next(
            d for idx, d in enumerate(trading_days)
            if idx == REBALANCE_INTERVAL_DAYS - 1
        )

        return NY_TIMEZONE.localize(datetime.combine(next_date, dt_time(10, 0)))


class TelegramBot:
    """Class for Telegram bot."""

    def __init__(self, trading_bot: TradingBot):
        """Initialize Telegram bot.

        Args:
            trading_bot: Trading bot instance
        """
        assert TELEGRAM_BOT_TOKEN is not None, "TELEGRAM_BOT_TOKEN must be set"
        self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
        self.dp = Dispatcher()
        self.trading_bot = trading_bot
        self.router = setup_router(self.trading_bot)
        self.setup_handlers()

    async def stop(self) -> None:
        """Stop Telegram bot."""
        logging.info("Stopping Telegram bot...")
        await self.dp.stop_polling()
        await self.bot.session.close()
        logging.info("Telegram bot stopped")

    def setup_handlers(self) -> None:
        """Setup command handlers."""
        self.dp.include_router(self.router)

    async def _send_to_admins(self, message: str) -> None:
        """Send message to all admin IDs.

        Args:
            message: Message text to send
        """
        for admin_id in ADMIN_IDS:
            try:
                await self.bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode="HTML"
                )
                logging.info("Message sent to admin %s", admin_id)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.error(
                    "Error sending message to admin %s: %s",
                    admin_id,
                    exc
                )

    async def send_startup_message(self) -> None:
        """Send startup message to admins."""
        if not ADMIN_IDS:
            logging.info("Admin list is empty, notifications not sent")
            return

        # Get bot state information
        now_ny = datetime.now(NY_TIMEZONE)
        is_open, reason = self.trading_bot.market_schedule.check_market_status()

        message = (
            "🤖 <b>Bot started</b>\n\n"
            f"⏰ Time (NY): {now_ny.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"📊 Market status: {'🟢 Open' if is_open else '🔴 Closed'}\n"
        )

        if not is_open:
            message += f"💬 Reason: {reason}\n"

        message += (
            f"\n⚙️ Mode: {self.trading_bot.get_settings()['mode']}\n"
            f"📅 Rebalance: {self.trading_bot.get_settings()['rebalance_time']}\n"
            f"📈 Positions: {self.trading_bot.get_settings()['positions_count']}\n"
        )

        await self._send_to_admins(message)

    async def send_daily_countdown(self) -> None:
        """Send daily countdown to rebalancing to admins."""
        if not ADMIN_IDS:
            logging.info("Admin list is empty, countdown not sent")
            return

        days_until = self.trading_bot.calculate_days_until_rebalance()
        next_date = self.trading_bot.get_next_rebalance_date()
        message = self.trading_bot.rebalance_flag.get_countdown_message(
            days_until, next_date
        )

        await self._send_to_admins(message)

    def send_daily_countdown_sync(self) -> None:
        """Sync wrapper for sending countdown (for scheduler)."""
        try:
            try:
                loop = asyncio.get_running_loop()
                asyncio.run_coroutine_threadsafe(
                    self.send_daily_countdown(), loop
                ).result(timeout=30)
            except RuntimeError:
                asyncio.run(self.send_daily_countdown())
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error sending countdown: %s", exc)

    async def start(self) -> None:
        """Start Telegram bot."""
        logging.info("=== Starting Telegram bot ===")
        await self.bot.set_my_commands([
            BotCommand(command="start", description="Start"),
            BotCommand(command="help", description="Help"),
            BotCommand(command="info", description="Bot information"),
            BotCommand(command="portfolio", description="Portfolio status"),
            BotCommand(command="stats", description="Trading statistics"),
            BotCommand(command="settings", description="Bot settings"),
            BotCommand(command="check_rebalance", description="Days until rebalancing"),
        ])
        await self.dp.start_polling(self.bot)


async def main() -> None:
    """Main program function."""
    trading_bot = TradingBot()
    telegram_bot = TelegramBot(trading_bot)

    # Set reference to Telegram bot in trading bot
    trading_bot.set_telegram_bot(telegram_bot)

    # Start trading bot (starts scheduler)
    trading_bot.start()

    # Send startup message to admins
    await telegram_bot.send_startup_message()

    # Start Telegram bot in async task
    telegram_task = asyncio.create_task(telegram_bot.start())

    # Setup signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(shutdown(trading_bot, telegram_bot))
        )

    try:
        await telegram_task
    except asyncio.CancelledError:
        logging.info("Telegram task cancelled")


async def shutdown(trading_bot: TradingBot,
                   telegram_bot: TelegramBot) -> None:
    """Graceful shutdown of all components.

    Args:
        trading_bot: Trading bot instance
        telegram_bot: Telegram bot instance
    """
    logging.info("Shutting down...")
    trading_bot.stop()
    await telegram_bot.stop()
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    logging.info("Shutdown complete")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Shutdown signal received (KeyboardInterrupt)")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logging.error("Critical error: %s", exc, exc_info=True)
    finally:
        logging.info("Program finished")
