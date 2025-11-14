"""Telegram bot class for managing Telegram interactions."""
import logging
from datetime import datetime
from typing import Any, Dict, cast

from aiogram.client.session.aiohttp import AiohttpSession
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from config import TELEGRAM_BOT_TOKEN, ADMIN_IDS
from .rebalance_flag import NY_TIMEZONE
from .utils import run_sync


class TelegramBot:
    """Class for Telegram bot."""

    def __init__(self, trading_bot: 'TradingBot'):
        """Initialize Telegram bot.

        Args:
            trading_bot: Trading bot instance
        """
        assert TELEGRAM_BOT_TOKEN is not None, "TELEGRAM_BOT_TOKEN must be set"

        # Create session with increased timeout for production stability
        session = AiohttpSession(timeout=60)  # 60 second timeout for all requests

        self.bot = Bot(token=TELEGRAM_BOT_TOKEN, session=session)
        self.dp = Dispatcher()
        self.trading_bot = trading_bot

        # Import here to avoid circular dependency
        from handlers import setup_router
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
                    parse_mode="HTML",
                    request_timeout=30
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
            run_sync(self.send_daily_countdown(), timeout=30)
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
            run_sync(
                self.send_error_notification(error_title, error_msg, is_warning),
                timeout=30
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error sending error notification: %s", exc)

    async def send_rebalance_request(self) -> None:
        """Send rebalance request with preview and ask for confirmation."""
        if not ADMIN_IDS:
            logging.info("Admin list is empty, sending rebalance request to no one")
            return

        # Set flag indicating we're waiting for confirmation
        self.trading_bot.awaiting_rebalance_confirmation = True

        # Get rebalance preview for all strategies
        previews = self.trading_bot.get_rebalance_preview()

        # Check if we have any strategy preview
        if not previews:
            logging.error("No strategy previews available")
            return

        # Get first strategy preview
        preview = next(iter(previews.values()))

        # Check for errors in preview
        if "error" in preview:
            logging.error("Rebalance preview error: %s", preview['error'])
            return

        # Build response message
        current_positions = cast(Dict[str, float], preview.get("current_positions", {}))
        positions_dict = cast(Dict[str, Any], preview.get("positions_dict", {}))
        top_tickers = cast(list, preview.get("top_tickers", []))
        positions_to_close = cast(list, preview.get("positions_to_close", []))
        positions_to_open = cast(list, preview.get("positions_to_open", []))
        available_cash = float(cast(float, preview.get("available_cash", 0.0)))
        position_size = float(cast(float, preview.get("position_size", 0.0)))

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
                msg += f"  ✅ {symbol}\n"
        else:
            msg += "  None\n"

        # Calculate total value to open
        total_open_value = len(positions_to_open) * position_size if positions_to_open else 0.0

        msg += "\n<b>💰 Summary:</b>\n"
        msg += f"  Available cash: ${available_cash:.2f}\n"
        total_close_value = self.trading_bot._calculate_total_close_value(positions_to_close, positions_dict)
        msg += f"  Positions to close: {len(positions_to_close)} (${total_close_value:.2f}) | "
        msg += f"Positions to open: {len(positions_to_open)} (${total_open_value:.2f})\n"

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
            BotCommand(command="test_rebalance", description="🧪 Test rebalance (admin only)"),
            BotCommand(command="clear", description="🗑 Clear cache (admin only)"),
        ])
        await self.dp.start_polling(self.bot, allowed_updates=None)
