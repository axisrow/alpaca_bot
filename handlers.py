"""Module with Telegram bot command handlers."""
import logging
from pathlib import Path

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardRemove

from config import ADMIN_IDS
from data_loader import DataLoader
from utils import telegram_handler


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
            "/test_rebalance - Test rebalance (dry run)\n"
            "/info - Bot information\n"
            "/portfolio - Portfolio status\n"
            "/stats - Trading statistics\n"
            "/settings - Bot settings\n"
            "/clear - Clear cache (admin only)"
        )

    @router.message(Command("check_rebalance"))
    @telegram_handler("❌ Error retrieving rebalance information")
    async def cmd_check_rebalance(message: Message):
        """Handle /check_rebalance command."""
        days_until = trading_bot.calculate_days_until_rebalance()
        next_date = trading_bot.get_next_rebalance_date()
        msg = trading_bot.rebalance_flag.get_countdown_message(
            days_until, next_date
        )

        await message.answer(msg, parse_mode="HTML")

    @router.message(Command("test_rebalance"))
    @telegram_handler("❌ Error running test rebalance")
    async def cmd_test_rebalance(message: Message):
        """Handle /test_rebalance command (dry run)."""
        preview = trading_bot.get_rebalance_preview()

        # Check for errors in preview
        if "error" in preview:
            raise ValueError(f"Rebalance preview error: {preview['error']}")

        # Build response message
        current_positions = preview.get("current_positions", {})
        positions_dict = preview.get("positions_dict", {})
        top_tickers = preview.get("top_tickers", [])
        positions_to_close = preview.get("positions_to_close", [])
        positions_to_open = preview.get("positions_to_open", [])
        available_cash = preview.get("available_cash", 0.0)
        position_size = preview.get("position_size", 0.0)

        msg = "📊 <b>Rebalance Preview (DRY RUN)</b>\n\n"

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
        msg += "\n⚠️ <i>This is a DRY RUN - no trades executed</i>"

        await message.answer(msg, parse_mode="HTML")

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
    @telegram_handler("❌ Error retrieving portfolio data")
    async def show_portfolio(message: Message):
        """Handle /portfolio command."""
        # Get portfolio data from TradingBot
        positions, account, account_pnl = trading_bot.get_portfolio_status()

        # Verify account data was retrieved correctly
        if not account:
            raise ValueError("Failed to retrieve account data")

        # Build message
        msg = "Portfolio Status:\n\n"

        if positions:
            all_positions = trading_bot.trading_client.get_all_positions()
            positions_dict = {p.symbol: p for p in all_positions}

            msg += "Positions:\n"
            msg += "\n".join(
                f"{symbol} – {float(qty):.2f} shares "
                f"(${float(positions_dict[symbol].market_value):.2f})"
                if symbol in positions_dict else
                f"{symbol} – {float(qty):.2f} shares (no price data)"
                for symbol, qty in positions.items()
            )
            msg += "\n"
        else:
            msg += "Positions: No open positions\n"

        msg += "\nPortfolio:\n"
        msg += f"Total: {float(account.portfolio_value):.2f}\n"
        msg += f"\nP&L: ${account_pnl:.2f}"

        await message.answer(msg)

    @router.message(Command("stats"))
    @telegram_handler("❌ Error retrieving trading statistics")
    async def show_stats(message: Message):
        """Handle /stats command."""
        # Get statistics from TradingBot
        stats = trading_bot.get_trading_stats()

        # Verify statistics were retrieved
        if not stats:
            raise ValueError("Statistics unavailable")

        msg = (
            f"Trading Statistics:\n"
            f"Trades today: {stats.get('trades_today', 0)}\n"
            f"Profit/Loss: ${stats.get('pnl', 0.0):.2f}\n"
            f"Win rate: {stats.get('win_rate', 0.0):.2f}%"
        )
        await message.answer(msg)

    @router.message(Command("settings"))
    @telegram_handler("❌ Error retrieving settings")
    async def show_settings(message: Message):
        """Handle /settings command."""
        # Get settings from TradingBot
        settings = trading_bot.get_settings()

        # Verify settings were retrieved
        if not settings:
            raise ValueError("Settings unavailable")

        msg = (
            f"Bot Settings:\n"
            f"- Rebalance time: {settings.get('rebalance_time', 'not set')}\n"
            f"- Number of positions: {settings.get('positions_count', 0)}\n"
            f"- Mode: {settings.get('mode', 'not set')}"
        )
        await message.answer(msg)

    @router.message(Command("clear"))
    @telegram_handler("❌ Error clearing cache")
    async def cmd_clear_cache(message: Message):
        """Handle /clear command (admin only)."""
        # Check if user is admin
        if message.from_user.id not in ADMIN_IDS:
            await message.answer("❌ This command is only available to administrators")
            return

        # Get cache file info before deletion
        cache_file = Path("data/cache.pkl")
        cache_size = 0

        if cache_file.exists():
            cache_size = cache_file.stat().st_size

        # Clear cache
        DataLoader.clear_cache()

        # Format size in human-readable format
        if cache_size > 0:
            if cache_size > 1024 * 1024:
                size_str = f"{cache_size / (1024 * 1024):.2f} MB"
            elif cache_size > 1024:
                size_str = f"{cache_size / 1024:.2f} KB"
            else:
                size_str = f"{cache_size} B"

            msg = f"✅ Cache cleared successfully\n\n📊 Freed: {size_str}"
        else:
            msg = "✅ Cache was already empty"

        await message.answer(msg)

    @router.message(F.text.lower().in_(["да", "yes", "y"]))
    @telegram_handler("❌ Error approving rebalance")
    async def approve_rebalance(message: Message):
        """Handle rebalance approval."""
        if not trading_bot.awaiting_rebalance_confirmation:
            await message.answer("❌ No pending rebalance request")
            return

        await message.answer("✅ Rebalance approved. Executing...")

        # Execute rebalance
        logging.info("Executing rebalance (approved by admin)")
        trading_bot.execute_rebalance()
        trading_bot.awaiting_rebalance_confirmation = False

        await message.answer("✅ Portfolio rebalancing completed successfully")

    @router.message(F.text.lower().in_(["нет", "no", "n"]))
    @telegram_handler("❌ Error rejecting rebalance")
    async def reject_rebalance(message: Message):
        """Handle rebalance rejection."""
        if not trading_bot.awaiting_rebalance_confirmation:
            await message.answer("❌ No pending rebalance request")
            return

        await message.answer("❌ Rebalance rejected")
        logging.info("Rebalance rejected by admin")
        trading_bot.awaiting_rebalance_confirmation = False

    @router.message()
    async def echo(message: Message):
        """Handle all other messages."""
        await message.answer(
            "Use menu buttons or commands to control the bot.\n"
            "Type /help for assistance"
        )

    return router
