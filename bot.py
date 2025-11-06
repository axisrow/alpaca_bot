"""Main module for trading bot with Telegram interface."""
import asyncio
import logging
import os
import signal
import sys
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any, Dict, Tuple

import pytz
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

from config import TELEGRAM_BOT_TOKEN, ADMIN_IDS, ENVIRONMENT, STRATEGIES, SNP500_TICKERS, CUSTOM_TICKERS, MEDIUM_TICKERS
from data_loader import DataLoader
from handlers import setup_router
from strategies.paper_low import PaperLowStrategy
from strategies.paper_medium import PaperMediumStrategy
from strategies.paper_high import PaperHighStrategy
from strategies.live import LiveStrategy
from utils import get_positions

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


class TelegramLoggingHandler(logging.Handler):
    """Custom logging handler that sends ERROR logs to Telegram admins."""

    def __init__(self, bot: Bot, loop: asyncio.AbstractEventLoop):
        """Initialize handler.

        Args:
            bot: Aiogram Bot instance
            loop: Main event loop
        """
        super().__init__()
        self.bot = bot
        self.loop = loop
        self.setLevel(logging.ERROR)

    def emit(self, record: logging.LogRecord) -> None:
        """Send ERROR log record to admins via Telegram.

        Args:
            record: Log record
        """
        if not ADMIN_IDS:
            return

        try:
            log_message = self.format(record)
            message = f"🚨 <b>Error</b>\n\n<code>{log_message}</code>"

            # Schedule sending on main event loop
            future = asyncio.run_coroutine_threadsafe(
                self._send_to_admins(message),
                self.loop
            )
            # Add callback to handle any exceptions from the coroutine
            future.add_done_callback(self._handle_send_result)
        except Exception:  # pylint: disable=broad-exception-caught
            # Silently ignore errors to prevent infinite loops
            pass

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
            except Exception:  # pylint: disable=broad-exception-caught
                # Silently ignore - don't log to prevent infinite loops
                pass

    @staticmethod
    def _handle_send_result(future: Any) -> None:
        """Handle result of sending admin message.

        Args:
            future: The future object from run_coroutine_threadsafe
        """
        try:
            future.result()
        except Exception:  # pylint: disable=broad-exception-caught
            # Silently ignore - don't log to prevent infinite loops
            pass


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
            if (start + timedelta(days=day_offset)).weekday() < 5
        )


class PortfolioManager:
    """Class for managing portfolio."""

    def __init__(self, trading_client: TradingClient, telegram_bot: Any = None):
        """Initialize portfolio manager.

        Args:
            trading_client: Alpaca API client
            telegram_bot: Optional TelegramBot instance for notifications
        """
        self.trading_client = trading_client
        self.telegram_bot = telegram_bot
        self.strategy = MomentumStrategy(self.trading_client)

    def set_telegram_bot(self, telegram_bot: Any) -> None:
        """Set telegram bot instance for notifications.

        Args:
            telegram_bot: TelegramBot instance
        """
        self.telegram_bot = telegram_bot

    def get_current_positions(self) -> Dict[str, float]:
        """Get current positions.

        Returns:
            Dict[str, float]: Dictionary of positions {ticker: quantity}
        """
        return get_positions(self.trading_client)


class TradingBot:
    """Main trading bot class."""

    def __init__(self):
        """Initialize trading bot with multiple strategies."""
        load_dotenv()
        self.strategies = {}  # Dict[str, Dict[str, Any]]
        self._initialize_strategies()
        # Use first enabled strategy's trading_client for market schedule
        first_client = next(
            (data['client'] for data in self.strategies.values() if data.get('enabled')),
            None
        )
        if not first_client:
            logging.error("No enabled strategies configured!")
            sys.exit(1)
        self.market_schedule = MarketSchedule(first_client)
        self.rebalance_flag = RebalanceFlag()
        self.scheduler = BackgroundScheduler()
        self.telegram_bot = None  # Will be set after TelegramBot creation
        self.awaiting_rebalance_confirmation = False  # Flag for pending confirmation

    def _initialize_strategies(self) -> None:
        """Initialize all enabled strategies from config."""
        for strategy_name, config in STRATEGIES.items():
            if not config.get('enabled', False):
                logging.info("Strategy %s is disabled, skipping", strategy_name)
                continue

            try:
                # Create trading client
                api_key = config.get('api_key')
                secret_key = config.get('secret_key')
                paper = config.get('paper', True)

                if not all([api_key, secret_key]):
                    logging.error("Missing API keys for strategy %s", strategy_name)
                    continue

                url_override = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
                trading_client = TradingClient(
                    api_key=api_key,
                    secret_key=secret_key,
                    paper=paper,
                    url_override=url_override
                )

                # Load tickers for this strategy
                tickers = self._get_tickers_for_strategy(strategy_name)

                # Create strategy instance
                if strategy_name == 'paper_low':
                    strategy = PaperLowStrategy(
                        trading_client,
                        tickers,
                        config.get('top_count', 10)
                    )
                elif strategy_name == 'paper_medium':
                    strategy = PaperMediumStrategy(
                        trading_client,
                        tickers,
                        config.get('top_count', 50)
                    )
                elif strategy_name == 'paper_high':
                    strategy = PaperHighStrategy(
                        trading_client,
                        tickers,
                        config.get('top_count', 50)
                    )
                elif strategy_name == 'live':
                    strategy = LiveStrategy(
                        trading_client,
                        tickers,
                        config.get('top_count', 10)
                    )
                else:
                    logging.warning("Unknown strategy type: %s", strategy_name)
                    continue

                self.strategies[strategy_name] = {
                    'client': trading_client,
                    'strategy': strategy,
                    'config': config,
                    'enabled': True
                }
                logging.info("Strategy %s initialized successfully", strategy_name)

            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.error(
                    "Error initializing strategy %s: %s",
                    strategy_name,
                    exc,
                    exc_info=True
                )

    def _get_tickers_for_strategy(self, strategy_name: str) -> list:
        """Get ticker list for specific strategy.

        Args:
            strategy_name: Name of the strategy

        Returns:
            list: List of tickers
        """
        # All data is loaded once (SNP500 + MEDIUM + CUSTOM)
        all_tickers = DataLoader.get_snp500_tickers()

        # Filter tickers per strategy
        if strategy_name == 'paper_low':
            # paper_low uses only SNP500 + CUSTOM
            tickers = list(set(SNP500_TICKERS + CUSTOM_TICKERS))
        else:
            # paper_medium and live use all available tickers (SNP500 + MEDIUM + CUSTOM)
            tickers = all_tickers

        return tickers

    def set_telegram_bot(self, telegram_bot: 'TelegramBot') -> None:
        """Set reference to Telegram bot for notifications.

        Args:
            telegram_bot: TelegramBot instance
        """
        self.telegram_bot = telegram_bot

    def _check_rebalance_conditions(self) -> bool:
        """Check if rebalance conditions are met.

        Returns:
            bool: True if all conditions are met, False otherwise
        """
        if self.rebalance_flag.has_rebalanced_today():
            logging.info("Rebalancing already performed today.")
            return False

        is_open, reason = self.market_schedule.check_market_status()
        if not is_open:
            logging.info("Rebalancing postponed: %s", reason)
            return False

        # Check if 22 trading days have passed since last rebalance
        days_until = self.calculate_days_until_rebalance()
        if days_until > 0:
            logging.info("Rebalancing not required. Days remaining: %d", days_until)
            return False

        return True

    def execute_rebalance(self) -> None:
        """Execute portfolio rebalancing for all strategies."""
        try:
            logging.info("Performing portfolio rebalancing for all strategies...")

            for strategy_name, strategy_data in self.strategies.items():
                if not strategy_data.get('enabled'):
                    continue

                try:
                    logging.info("Rebalancing strategy: %s", strategy_name)
                    strategy_data['strategy'].rebalance()
                    logging.info("Strategy %s rebalanced successfully", strategy_name)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logging.error(
                        "Error rebalancing %s: %s",
                        strategy_name,
                        exc,
                        exc_info=True
                    )

            self.rebalance_flag.write_flag()
            logging.info("All strategies rebalanced successfully")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Rebalance failed: %s", exc, exc_info=True)
            if self.telegram_bot:
                self.telegram_bot.send_error_notification_sync(
                    "Rebalancing Failed",
                    f"Error during portfolio rebalancing:\n<code>{str(exc)}</code>"
                )
            raise

    def request_rebalance_confirmation_sync(self) -> None:
        """Request rebalance confirmation from admins (sync wrapper)."""
        if not self.telegram_bot:
            logging.warning("Telegram bot not available, executing rebalance directly")
            self.execute_rebalance()
            return

        try:
            try:
                loop = asyncio.get_running_loop()
                asyncio.run_coroutine_threadsafe(
                    self.telegram_bot.send_rebalance_request(), loop
                ).result(timeout=30)
            except RuntimeError:
                asyncio.run(self.telegram_bot.send_rebalance_request())
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error requesting rebalance confirmation: %s", exc)
            # Fallback: execute rebalance anyway
            logging.info("Executing rebalance as fallback")
            self.execute_rebalance()

    def perform_rebalance(self) -> None:
        """Perform portfolio rebalancing."""
        if not self._check_rebalance_conditions():
            return

        # In local environment, request confirmation; otherwise execute directly
        if ENVIRONMENT == "local":
            self.request_rebalance_confirmation_sync()
        else:
            self.execute_rebalance()

    def perform_daily_task(self) -> None:
        """Perform daily task: send countdown and rebalance if needed."""
        if self.telegram_bot:
            self.telegram_bot.send_daily_countdown_sync()
        self.perform_rebalance()

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
            self.scheduler.start()
            self.scheduler.add_job(
                self.perform_daily_task,
                'cron',
                day_of_week='mon-fri',
                hour=10,
                minute=0,
                timezone=NY_TIMEZONE
            )
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

    def get_portfolio_status(self) -> Tuple[Dict[str, Dict[str, Any]], float, float]:
        """Get detailed portfolio data from all strategies.

        Returns:
            Tuple: (positions_by_strategy, total_portfolio_value, total_pnl)
        """
        try:
            positions_by_strategy = {}
            total_portfolio_value = 0.0
            total_pnl = 0.0

            for strategy_name, strategy_data in self.strategies.items():
                if not strategy_data.get('enabled'):
                    continue

                try:
                    client = strategy_data['client']

                    # Get positions
                    all_positions = client.get_all_positions()
                    positions = {pos.symbol: float(pos.qty) for pos in all_positions}

                    # Get account
                    account = client.get_account()
                    portfolio_value = float(getattr(account, 'portfolio_value', 0))

                    # Calculate P&L
                    pnl = sum(float(getattr(pos, 'unrealized_pl', 0)) for pos in all_positions)

                    positions_by_strategy[strategy_name] = {
                        'positions': positions,
                        'portfolio_value': portfolio_value,
                        'pnl': pnl,
                        'all_positions': {p.symbol: p for p in all_positions}
                    }

                    total_portfolio_value += portfolio_value
                    total_pnl += pnl

                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logging.error("Error retrieving data for %s: %s", strategy_name, exc)
                    positions_by_strategy[strategy_name] = {
                        'positions': {},
                        'portfolio_value': 0.0,
                        'pnl': 0.0,
                        'all_positions': {}
                    }

            return positions_by_strategy, total_portfolio_value, total_pnl

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error retrieving portfolio data: %s", exc)
            return {}, 0.0, 0.0

    def get_trading_stats(self) -> Dict[str, float]:
        """Get real trading statistics from all strategies.

        Returns:
            Dict[str, float]: Aggregated trading statistics
        """
        try:
            total_trades_today = 0
            total_pnl = 0.0

            today = datetime.now(NY_TIMEZONE).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            for strategy_name, strategy_data in self.strategies.items():
                if not strategy_data.get('enabled'):
                    continue

                try:
                    client = strategy_data['client']

                    # Get trades for today
                    request = GetOrdersRequest(
                        status=QueryOrderStatus.CLOSED,
                        after=today
                    )
                    trades = client.get_orders(filter=request)
                    total_trades_today += len(trades)

                    # Calculate P&L
                    positions = client.get_all_positions()
                    pnl = sum(float(getattr(pos, 'unrealized_pl', 0)) for pos in positions)
                    total_pnl += pnl

                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logging.error("Error retrieving stats for %s: %s", strategy_name, exc)

            return {
                "trades_today": total_trades_today,
                "pnl": total_pnl,
                "win_rate": 0.0  # Simplified version, win_rate requires history analysis
            }
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error retrieving trading statistics: %s", exc)
            return {"trades_today": 0, "pnl": 0.0, "win_rate": 0.0}

    def get_settings(self) -> Dict[str, Any]:
        """Get bot settings.

        Returns:
            Dict[str, Any]: Settings dictionary with all strategies
        """
        strategies_info = {}

        for strategy_name, strategy_data in self.strategies.items():
            if not strategy_data.get('enabled'):
                continue

            config = strategy_data['config']
            strategies_info[strategy_name] = {
                'positions_count': config.get('top_count', 10),
                'mode': 'Paper Trading' if config.get('paper', True) else 'Live Trading',
                'enabled': True
            }

        return {
            "rebalance_time": "10:00 NY",
            "strategies": strategies_info
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

    def get_rebalance_preview(self) -> Dict[str, Dict[str, Any]]:
        """Get a preview of what would happen in rebalancing (dry-run) for all strategies.

        Returns:
            Dict[str, Dict]: Rebalance plan for each strategy
        """
        previews = {}

        for strategy_name, strategy_data in self.strategies.items():
            if not strategy_data.get('enabled'):
                continue

            client = strategy_data['client']
            strategy = strategy_data['strategy']

            try:
                # Get current positions
                all_positions = client.get_all_positions()
                current_positions = {pos.symbol: float(pos.qty) for pos in all_positions}
                positions_dict = {p.symbol: p for p in all_positions}

                # Get account
                account = client.get_account()
                available_cash = float(getattr(account, 'cash', 0))

                # Get top N by momentum
                top_tickers = strategy.get_signals()

                # Calculate what would change
                positions_to_close = list(set(current_positions.keys()) - set(top_tickers))
                positions_to_open = list(set(top_tickers) - set(current_positions.keys()))

                # Calculate position size
                position_size = 0.0
                if positions_to_open and available_cash > 0:
                    position_size = available_cash / len(positions_to_open)

                previews[strategy_name] = {
                    "current_positions": current_positions,
                    "positions_dict": positions_dict,
                    "top_tickers": top_tickers,
                    "top_count": strategy_data['config'].get('top_count', 10),
                    "positions_to_close": positions_to_close,
                    "positions_to_open": positions_to_open,
                    "available_cash": available_cash,
                    "position_size": position_size
                }

            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.error("Error previewing rebalance for %s: %s", strategy_name, exc)
                previews[strategy_name] = {
                    "error": str(exc),
                    "current_positions": {},
                    "positions_dict": {},
                    "top_tickers": [],
                    "top_count": strategy_data['config'].get('top_count', 10),
                    "positions_to_close": [],
                    "positions_to_open": [],
                    "available_cash": 0.0,
                    "position_size": 0.0
                }

        return previews


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

        settings = self.trading_bot.get_settings()
        message += f"\n📅 Rebalance: {settings['rebalance_time']}\n"

        # Display all active strategies
        if settings.get('strategies'):
            message += "\n⚙️ <b>Active Strategies:</b>\n"
            for strategy_name, strategy_info in settings['strategies'].items():
                message += (
                    f"  • <b>{strategy_name}</b>: "
                    f"{strategy_info['mode']} "
                    f"({strategy_info['positions_count']} positions)\n"
                )
        else:
            message += "\n⚙️ No active strategies\n"

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

    async def send_error_notification(self, error_title: str, error_msg: str,
                                      is_warning: bool = False) -> None:
        """Send error notification to admins.

        Args:
            error_title: Error title/name
            error_msg: Detailed error message
            is_warning: If True, use warning icon (⚠️), else critical icon (🚨)
        """
        if not ADMIN_IDS:
            logging.info("Admin list is empty, error notification not sent")
            return

        icon = "⚠️" if is_warning else "🚨"
        now_ny = datetime.now(NY_TIMEZONE)
        message = (
            f"{icon} <b>Error: {error_title}</b>\n\n"
            f"⏰ Time (NY): {now_ny.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"📝 Details:\n{error_msg}"
        )

        await self._send_to_admins(message)

    def send_error_notification_sync(self, error_title: str, error_msg: str,
                                     is_warning: bool = False) -> None:
        """Sync wrapper for sending error notification.

        Args:
            error_title: Error title/name
            error_msg: Detailed error message
            is_warning: If True, use warning icon (⚠️), else critical icon (🚨)
        """
        try:
            try:
                loop = asyncio.get_running_loop()
                asyncio.run_coroutine_threadsafe(
                    self.send_error_notification(error_title, error_msg, is_warning),
                    loop
                ).result(timeout=30)
            except RuntimeError:
                asyncio.run(self.send_error_notification(error_title, error_msg,
                                                         is_warning))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error sending error notification: %s", exc)

    async def send_rebalance_request(self) -> None:
        """Send rebalance request with preview and ask for confirmation."""
        if not ADMIN_IDS:
            logging.info("Admin list is empty, sending rebalance request to no one")
            return

        # Set flag indicating we're waiting for confirmation
        self.trading_bot.awaiting_rebalance_confirmation = True

        # Get rebalance preview
        preview = self.trading_bot.get_rebalance_preview()

        # Check for errors in preview
        if "error" in preview:
            logging.error("Rebalance preview error: %s", preview['error'])
            return

        # Build response message
        current_positions = preview.get("current_positions", {})
        positions_dict = preview.get("positions_dict", {})
        top_tickers = preview.get("top_tickers", [])
        positions_to_close = preview.get("positions_to_close", [])
        positions_to_open = preview.get("positions_to_open", [])
        available_cash = preview.get("available_cash", 0.0)
        position_size = preview.get("position_size", 0.0)

        msg = "🔄 <b>Rebalance Request - Need Confirmation</b>\n\n"

        # Current positions
        msg += "<b>📍 Current Positions:</b>\n"
        if current_positions:
            for symbol, qty in current_positions.items():
                pos_info = positions_dict.get(symbol)
                if pos_info:
                    market_value = float(getattr(pos_info, 'market_value', 0))
                    msg += f"  {symbol}: {float(qty):.2f} shares (${market_value:.2f})\n"
                else:
                    msg += f"  {symbol}: {float(qty):.2f} shares\n"
        else:
            msg += "  No open positions\n"

        msg += "\n<b>🎯 Top 10 by Momentum:</b>\n"
        for i, ticker in enumerate(top_tickers, 1):
            msg += f"  {i}. {ticker}\n"

        msg += "\n<b>📉 Positions to Close:</b>\n"
        if positions_to_close:
            for symbol in positions_to_close:
                pos_info = positions_dict.get(symbol)
                if pos_info:
                    market_value = float(getattr(pos_info, 'market_value', 0))
                    msg += f"  ❌ {symbol} (${market_value:.2f})\n"
                else:
                    msg += f"  ❌ {symbol}\n"
        else:
            msg += "  None\n"

        msg += "\n<b>📈 Positions to Open:</b>\n"
        if positions_to_open:
            for symbol in positions_to_open:
                msg += f"  ✅ {symbol} (${position_size:.2f})\n"
        else:
            msg += "  None\n"

        msg += "\n<b>💰 Summary:</b>\n"
        msg += f"  Available cash: ${available_cash:.2f}\n"
        msg += f"  Position size: ${position_size:.2f}\n"
        msg += f"  Changes: {len(positions_to_close)} close + {len(positions_to_open)} open\n"

        msg += "\n<b>👉 Reply with:</b>\n"
        msg += "  <code>да</code> or <code>yes</code> - Approve rebalance\n"
        msg += "  <code>нет</code> or <code>no</code> - Reject rebalance"

        await self._send_to_admins(msg)

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
            BotCommand(command="clear", description="🗑 Clear cache (admin only)"),
        ])
        await self.dp.start_polling(self.bot, allowed_updates=None)


async def main() -> None:
    """Main program function."""
    trading_bot = TradingBot()
    telegram_bot = TelegramBot(trading_bot)

    # Set reference to Telegram bot in trading bot
    trading_bot.set_telegram_bot(telegram_bot)

    # Get reference to main event loop
    loop = asyncio.get_running_loop()

    # Add Telegram logging handler for ERROR logs
    telegram_handler = TelegramLoggingHandler(telegram_bot.bot, loop)
    logging.getLogger().addHandler(telegram_handler)

    # Start trading bot (starts scheduler)
    trading_bot.start()

    # Send startup message to admins
    await telegram_bot.send_startup_message()

    # Start Telegram bot in async task
    telegram_task = asyncio.create_task(telegram_bot.start())

    # Setup signal handlers
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
