"""Telegram logging handler module."""
import asyncio
import logging
from typing import Any

from aiogram import Bot

from config import ADMIN_IDS


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
                    parse_mode="HTML",
                    request_timeout=30
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
