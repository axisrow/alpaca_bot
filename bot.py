"""Main module for trading bot with Telegram interface."""
import asyncio
import logging
import signal

from core.alpaca_bot import create_trading_bot_state, start, stop, set_telegram_bot_state
from core.telegram_bot import (
    create_telegram_bot_state,
    setup_handlers,
    send_startup_message,
    start as telegram_start,
    stop as telegram_stop
)
from core.telegram_logging import create_telegram_logging_handler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('data/trading_bot.log')
    ]
)


async def main() -> None:
    """Main program function."""
    # Create trading bot state
    trading_bot_state = create_trading_bot_state()

    # Create telegram bot state
    telegram_bot_state = create_telegram_bot_state(trading_bot_state)

    # Set reference to Telegram bot in trading bot
    set_telegram_bot_state(trading_bot_state, telegram_bot_state)

    # Get reference to main event loop
    loop = asyncio.get_running_loop()

    # Add Telegram logging handler for ERROR logs
    telegram_handler = create_telegram_logging_handler(telegram_bot_state['bot'], loop)
    logging.getLogger().addHandler(telegram_handler)

    # Setup telegram handlers
    setup_handlers(telegram_bot_state)

    # Start trading bot (starts scheduler)
    start(trading_bot_state)

    # Send startup message to admins
    await send_startup_message(telegram_bot_state)

    # Start Telegram bot in async task
    telegram_task = asyncio.create_task(telegram_start(telegram_bot_state))

    # Setup signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(shutdown(trading_bot_state, telegram_bot_state))
        )

    try:
        await telegram_task
    except asyncio.CancelledError:
        logging.info("Telegram task cancelled")


async def shutdown(trading_bot_state, telegram_bot_state) -> None:
    """Graceful shutdown of all components.

    Args:
        trading_bot_state: Trading bot state
        telegram_bot_state: Telegram bot state
    """
    logging.info("Shutting down...")
    stop(trading_bot_state)
    await telegram_stop(telegram_bot_state)
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
