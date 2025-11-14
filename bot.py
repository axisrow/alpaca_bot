"""Main module for trading bot with Telegram interface."""
import asyncio
import logging
import signal

from core import TradingBot, TelegramBot, TelegramLoggingHandler

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
