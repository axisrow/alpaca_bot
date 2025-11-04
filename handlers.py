"""Module with Telegram bot command handlers."""
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardRemove


def setup_router(trading_bot):
    """Setup router with access to TradingBot.

    Args:
        trading_bot: Trading bot instance

    Returns:
        Router: Configured router with handlers
    """
    router = Router()

    @router.message(Command("start"))
    async def cmd_start(message: Message):
        """Handle /start command."""
        await message.answer(
            "Hello! I'm your trading bot assistant.\n"
            "Type /help to see available commands.",
            reply_markup=ReplyKeyboardRemove()
        )

    @router.message(Command("help"))
    async def cmd_help(message: Message):
        """Handle /help command."""
        await message.answer(
            "Available commands:\n"
            "/start - Start\n"
            "/help - Show help\n"
            "/check_rebalance - Days until rebalancing\n"
            "/info - Bot information\n"
            "/portfolio - Portfolio status\n"
            "/stats - Trading statistics\n"
            "/settings - Bot settings"
        )

    @router.message(Command("check_rebalance"))
    async def cmd_check_rebalance(message: Message):
        """Handle /check_rebalance command."""
        try:
            days_until = trading_bot.calculate_days_until_rebalance()

            if days_until == 0:
                msg = (
                    "⏰ <b>Rebalancing today!</b>\n\n"
                    "🔄 Portfolio will be rebalanced to top 10 S&P 500 stocks\n"
                    "⏱️ Rebalance time: 10:00 (NY)"
                )
            else:
                next_rebalance_date = trading_bot.get_next_rebalance_date()
                formatted_date = next_rebalance_date.strftime("%Y-%m-%d")
                msg = (
                    f"📊 <b>Rebalancing countdown</b>\n\n"
                    f"📅 Days remaining: <b>{days_until}</b> trading days\n"
                    f"📈 Strategy: Momentum Trading (S&P 500)\n"
                    f"⏱️ Next rebalance: <b>{formatted_date}</b> at 10:00 AM (NY)"
                )

            await message.answer(msg, parse_mode="HTML")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error checking days until rebalance: %s", exc)
            await message.answer(
                "❌ Error retrieving rebalance information"
            )

    @router.message(Command("info"))
    async def show_info(message: Message):
        """Handle /info command."""
        await message.answer(
            "Automated trading bot for stock market trading.\n"
            "Strategy: Momentum Trading\n"
            "Rebalancing: daily at 10:00 (NY)\n"
            "Uses Alpaca Markets API"
        )

    @router.message(Command("portfolio"))
    async def show_portfolio(message: Message):
        """Handle /portfolio command."""
        try:
            # Get portfolio data from TradingBot
            positions, account, account_pnl = trading_bot.get_portfolio_status()

            # Verify account data was retrieved correctly
            if not account:
                raise ValueError("Failed to retrieve account data")

            # Build message
            msg = "Portfolio Status:\n\n"

            if positions:
                msg += "Positions:\n"
                for symbol, qty in positions.items():
                    # Get market value for position
                    all_positions = trading_bot.trading_client.get_all_positions()
                    position = next((p for p in all_positions
                                     if p.symbol == symbol), None)
                    if position:
                        value = float(position.market_value)
                        msg += (f"{symbol} – {float(qty):.2f} shares "
                                f"(${value:.2f})\n")
                    else:
                        msg += (f"{symbol} – {float(qty):.2f} shares "
                                f"(no price data)\n")
            else:
                msg += "Positions: No open positions\n"

            msg += "\nPortfolio:\n"
            msg += f"Total: {float(account.portfolio_value):.2f}\n"
            msg += f"\nP&L: ${account_pnl:.2f}"

            await message.answer(msg)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error retrieving portfolio data: %s", exc)
            await message.answer(
                "❌ Error retrieving portfolio data"
            )

    @router.message(Command("stats"))
    async def show_stats(message: Message):
        """Handle /stats command."""
        try:
            # Get statistics from TradingBot
            stats = trading_bot.get_trading_stats()

            # Verify statistics were retrieved
            if not stats:
                raise ValueError("Statistics unavailable")

            msg = "Trading Statistics:\n"
            msg += f"Trades today: {stats.get('trades_today', 0)}\n"
            msg += f"Profit/Loss: ${stats.get('pnl', 0.0):.2f}\n"
            msg += f"Win rate: {stats.get('win_rate', 0.0):.2f}%"
            await message.answer(msg)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error retrieving trading statistics: %s", exc)
            await message.answer(
                "❌ Error retrieving trading statistics"
            )

    @router.message(Command("settings"))
    async def show_settings(message: Message):
        """Handle /settings command."""
        try:
            # Get settings from TradingBot
            settings = trading_bot.get_settings()

            # Verify settings were retrieved
            if not settings:
                raise ValueError("Settings unavailable")

            msg = "Bot Settings:\n"
            msg += (f"- Rebalance time: "
                    f"{settings.get('rebalance_time', 'not set')}\n")
            msg += (f"- Number of positions: "
                    f"{settings.get('positions_count', 0)}\n")
            msg += f"- Mode: {settings.get('mode', 'not set')}"
            await message.answer(msg)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error retrieving settings: %s", exc)
            await message.answer("❌ Error retrieving settings")

    @router.message()
    async def echo(message: Message):
        """Handle all other messages."""
        await message.answer(
            "Use menu buttons or commands to control the bot.\n"
            "Type /help for assistance"
        )

    return router
