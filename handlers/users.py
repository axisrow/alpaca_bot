"""User command handlers."""
import asyncio
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from core.utils import telegram_handler


def setup_user_router(trading_bot):
    """Setup router with user commands.

    Args:
        trading_bot: Trading bot instance

    Returns:
        Router: Configured router with handlers
    """
    router = Router()

    @router.message(Command("help"))
    async def cmd_help(message: Message):
        """Handle /help command."""
        await message.answer(
            "Available commands:\n"
            "/start - Start\n"
            "/help - Show help\n"
            "/info - Bot information\n"
            "/portfolio - Portfolio status\n"
            "/stats - Trading statistics\n"
            "/settings - Bot settings"
        )

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
        from core.alpaca_bot import get_portfolio_status
        loading_msg = await message.answer("⏳ Получаю данные портфеля...")
        positions_by_strategy, total_value, total_pnl = await asyncio.to_thread(
            get_portfolio_status, trading_bot
        )

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
        from core.alpaca_bot import get_trading_stats
        loading_msg = await message.answer("⏳ Загружаю статистику...")
        stats = await asyncio.to_thread(get_trading_stats, trading_bot)

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
        from core.alpaca_bot import get_settings
        settings = get_settings(trading_bot)

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

    return router
