"""Module with Telegram bot command handlers."""
import asyncio
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
        """Handle /test_rebalance command (dry run for all strategies)."""
        loading_msg = await message.answer("⏳ Загружаю данные для ребалансировки...")
        previews = await asyncio.to_thread(trading_bot.get_rebalance_preview)

        if not previews:
            await loading_msg.delete()
            raise ValueError("No rebalance preview available")

        msg = "📊 <b>Rebalance Preview (DRY RUN)</b>\n\n"

        for strategy_name, preview in previews.items():
            # Check for errors
            if "error" in preview:
                msg += f"<b>🔹 {strategy_name.upper()}:</b>\n"
                msg += f"  ❌ Error: {preview['error']}\n\n"
                continue

            # Build response for this strategy
            current_positions = preview.get("current_positions", {})
            positions_dict = preview.get("positions_dict", {})
            top_count = preview.get("top_count", 10)
            top_tickers = preview.get("top_tickers", [])
            positions_to_close = preview.get("positions_to_close", [])
            positions_to_open = preview.get("positions_to_open", [])
            available_cash = preview.get("available_cash", 0.0)
            position_size = preview.get("position_size", 0.0)

            msg += f"<b>🔹 {strategy_name.upper()}</b>\n\n"

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

            msg += f"\n<b>🎯 Top {top_count} by Momentum:</b>\n"
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
            msg += "\n" + "─" * 40 + "\n\n"

        msg += "⚠️ <i>This is a DRY RUN - no trades executed</i>"

        await loading_msg.delete()
        await message.answer(msg, parse_mode="HTML")

    @router.message(Command("info"))
    async def show_info(message: Message):
        """Handle /info command."""
        msg = (
            "🤖 <b>Automated Trading Bot</b>\n\n"
            "<b>Strategies:</b>\n"
            "  • paper_low: Top-10 S&P 500 momentum\n"
            "  • paper_medium: Top-50 S&P 500 momentum\n"
            "  • paper_high: Top-50 S&P 500+HIGH momentum\n\n"
            "<b>Rebalancing:</b> Daily at 10:00 AM (NY time)\n"
            "<b>API:</b> Alpaca Markets\n"
        )
        await message.answer(msg, parse_mode="HTML")

    @router.message(Command("portfolio"))
    @telegram_handler("❌ Error retrieving portfolio data")
    async def show_portfolio(message: Message):
        """Handle /portfolio command."""
        # Get portfolio data from TradingBot (by strategy)
        loading_msg = await message.answer("⏳ Получаю данные портфеля...")
        positions_by_strategy, total_value, total_pnl = await asyncio.to_thread(trading_bot.get_portfolio_status)

        if not positions_by_strategy:
            await loading_msg.delete()
            raise ValueError("Failed to retrieve portfolio data")

        msg = "📊 <b>Portfolio Status (All Strategies)</b>\n\n"
        msg += f"<b>💼 Total Portfolio Value:</b> ${total_value:.2f}\n"
        msg += f"<b>📈 Total P&L:</b> ${total_pnl:.2f}\n\n"
        msg += "─" * 40 + "\n\n"

        for strategy_name, data in positions_by_strategy.items():
            positions = data['positions']
            portfolio_value = data['portfolio_value']
            pnl = data['pnl']
            positions_dict = data['all_positions']

            msg += f"<b>🔹 {strategy_name.upper()}</b>\n"
            msg += f"Portfolio: ${portfolio_value:.2f} | P&L: ${pnl:.2f}\n\n"

            if positions:
                msg += "<b>Positions:</b>\n"
                for symbol, qty in positions.items():
                    if symbol in positions_dict:
                        pos_info = positions_dict[symbol]
                        market_value = float(pos_info.market_value)
                        msg += f"  {symbol}: {float(qty):.2f} shares (${market_value:.2f})\n"
                    else:
                        msg += f"  {symbol}: {float(qty):.2f} shares\n"
            else:
                msg += "  No open positions\n"

            msg += "\n" + "─" * 40 + "\n\n"

        await loading_msg.delete()
        await message.answer(msg, parse_mode="HTML")

    @router.message(Command("stats"))
    @telegram_handler("❌ Error retrieving trading statistics")
    async def show_stats(message: Message):
        """Handle /stats command."""
        loading_msg = await message.answer("⏳ Загружаю статистику...")
        stats = await asyncio.to_thread(trading_bot.get_trading_stats)

        if not stats:
            await loading_msg.delete()
            raise ValueError("Statistics unavailable")

        msg = (
            "📊 <b>Trading Statistics (All Strategies)</b>\n\n"
            f"<b>📝 Total Trades Today:</b> {stats.get('trades_today', 0)}\n"
            f"<b>💰 Total P&L:</b> ${stats.get('pnl', 0.0):.2f}\n"
            f"<b>📈 Win Rate:</b> {stats.get('win_rate', 0.0):.2f}%"
        )
        await loading_msg.delete()
        await message.answer(msg, parse_mode="HTML")

    @router.message(Command("settings"))
    @telegram_handler("❌ Error retrieving settings")
    async def show_settings(message: Message):
        """Handle /settings command."""
        settings = trading_bot.get_settings()

        if not settings:
            raise ValueError("Settings unavailable")

        msg = "⚙️ <b>Bot Settings</b>\n\n"
        msg += f"<b>🕐 Rebalance Time:</b> {settings.get('rebalance_time', 'not set')}\n\n"
        msg += "<b>📊 Strategies:</b>\n"

        for name, config in settings.get('strategies', {}).items():
            positions_count = config.get('positions_count', 0)
            mode = config.get('mode', 'not set')
            msg += f"  • <b>{name}</b>: {positions_count} positions ({mode})\n"

        await message.answer(msg, parse_mode="HTML")

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
