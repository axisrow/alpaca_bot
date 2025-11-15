"""Telegram logging handler module with functional programming approach."""
import asyncio
import logging
from typing import Any

from aiogram import Bot

from config import ADMIN_IDS


def create_telegram_logging_handler(
    bot: Bot,
    loop: asyncio.AbstractEventLoop
) -> logging.Handler:
    """Create a custom logging handler that sends ERROR logs to Telegram admins.

    Args:
        bot: Aiogram Bot instance
        loop: Main event loop

    Returns:
        Configured logging handler
    """

    class TelegramLoggingHandler(logging.Handler):
        """Custom logging handler that sends ERROR logs to Telegram admins."""

        def __init__(self):
            """Initialize handler."""
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
                message = f"🚨 <b>Error</b>\\n\\n<code>{log_message}</code>"

                # Schedule sending on main event loop
                future = asyncio.run_coroutine_threadsafe(
                    _send_to_admins(self.bot, message),
                    self.loop
                )
                # Add callback to handle any exceptions from the coroutine
                future.add_done_callback(_handle_send_result)
            except Exception:  # pylint: disable=broad-exception-caught
                # Silently ignore errors to prevent infinite loops
                pass

    return TelegramLoggingHandler()


async def _send_to_admins(bot: Bot, message: str) -> None:
    """Send message to all admin IDs.

    Args:
        bot: Bot instance
        message: Message text to send
    """
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=message,
                parse_mode="HTML",
                request_timeout=30
            )
        except Exception:  # pylint: disable=broad-exception-caught
            # Silently ignore - don't log to prevent infinite loops
            pass


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
