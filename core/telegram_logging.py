"""Telegram logging handler module."""
import asyncio
import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError

from config import ADMIN_IDS
from .utils import retry_on_telegram_error


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

    @retry_on_telegram_error(retries=4, initial_delay=2.0)
    async def _send_message_to_admin(self, admin_id: int, message: str) -> None:
        """Send message to a single admin with retry logic.

        Args:
            admin_id: Telegram user ID
            message: Message text to send
        """
        await self.bot.send_message(
            chat_id=admin_id,
            text=message,
            parse_mode="HTML",
            request_timeout=30
        )

    async def _send_to_admins(self, message: str) -> None:
        """Send message to all admin IDs.

        Args:
            message: Message text to send
        """
        for admin_id in ADMIN_IDS:
            try:
                await self._send_message_to_admin(admin_id, message)
            except (TelegramNetworkError, Exception):  # pylint: disable=broad-exception-caught
                # Silently ignore - don't log to prevent infinite loops
                # Network errors will already be logged by the retry decorator
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
