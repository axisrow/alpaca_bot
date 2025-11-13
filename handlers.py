"""Module with Telegram bot command handlers."""
import asyncio
import logging
from pathlib import Path

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.types import FSInputFile

from config import ADMIN_IDS
from data_loader import DataLoader
from utils import telegram_handler
from stories.story_engine import StoryEngine


def setup_router(trading_bot):
    """Setup router with access to TradingBot.

    Args:
        trading_bot: Trading bot instance

    Returns:
        Router: Configured router with handlers
    """
    router = Router()
    story_engine = StoryEngine()  # Initialize story engine

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
            "/settings - Bot settings\n\n"
            "📖 Story Mode (NEW):\n"
            "/story - Show available stories\n"
            "/read_story <id> - Start reading a story\n"
            "/read_chapter - Read next chapter\n"
            "/story_status - Check story progress\n\n"
            "Admin commands:\n"
            "/balance_check - Verify balance integrity\n"
            "/investors - Show all investors balances\n"
            "/export <name> - Export investor CSV files\n"
            "/clear - Clear cache\n"
            "/deposit - Deposit to investor\n"
            "/withdraw - Withdraw from investor"
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

            # Summary statistics only (no detailed lists)
            msg += f"📍 Current Positions: {len(current_positions)}\n"
            msg += f"📉 Positions to Close: {len(positions_to_close)}\n"
            msg += f"📈 Positions to Open: {len(positions_to_open)}\n"

            # Calculate total value to close
            total_close_value = 0.0
            for symbol in positions_to_close:
                pos_info = positions_dict.get(symbol)
                if pos_info:
                    market_value = float(getattr(pos_info, 'market_value', 0))
                    total_close_value += market_value

            # Calculate total value to open
            total_open_value = len(positions_to_open) * position_size if positions_to_open else 0.0

            msg += "\n<b>💰 Summary:</b>\n"
            msg += f"  Available cash: ${available_cash:.2f}\n"
            msg += f"  Positions to close: {len(positions_to_close)} (${total_close_value:.2f}) | "
            msg += f"Positions to open: {len(positions_to_open)} (${total_open_value:.2f})\n"
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

    @router.message(Command("deposit"))
    @telegram_handler("❌ Error processing deposit")
    async def cmd_deposit(message: Message):
        """Handle /deposit command - deposit money to investor account.

        Usage: /deposit <name> <amount> [account]

        Examples:
        /deposit Cherry 10000          → distribute by default (45/35/20)
        /deposit Cherry 5000 low       → deposit to low account only
        /deposit Cherry 3000 medium    → deposit to medium account only

        account: low, medium, high (optional)
        """
        # Admin only
        if message.from_user.id not in ADMIN_IDS:
            await message.answer("❌ Admin only")
            return

        # Parse command
        parts = message.text.split()
        if len(parts) < 3 or len(parts) > 4:
            await message.answer(
                "Usage: /deposit <name> <amount> [account]\n\n"
                "Examples:\n"
                "/deposit Cherry 10000\n"
                "/deposit Cherry 5000 low\n\n"
                "Accounts: low, medium, high"
            )
            return

        investor_name = parts[1]

        try:
            amount = float(parts[2])
        except ValueError:
            await message.answer("❌ Invalid amount")
            return

        # Optional account
        account = parts[3].lower() if len(parts) == 4 else None

        # Validate account
        if account and account not in ['low', 'medium', 'high']:
            await message.answer(
                "❌ Invalid account. Use: low, medium, or high"
            )
            return

        # Check investor exists
        if not trading_bot.investor_manager.investor_exists(investor_name):
            await message.answer(f"❌ Investor '{investor_name}' not found")
            return

        # Create pending deposit operation
        try:
            from datetime import datetime
            operation_ids = trading_bot.investor_manager.deposit(
                investor_name, amount, account, datetime.now()
            )
        except Exception as exc:
            await message.answer(f"❌ Error: {str(exc)}")
            return

        # Format response
        msg = f"✅ <b>Deposit Request Created</b>\n\n"
        msg += f"<b>Investor:</b> {investor_name}\n"
        msg += f"<b>Total Amount:</b> ${amount:,.2f}\n"
        msg += f"<b>Status:</b> pending\n\n"

        if account:
            # Specific account
            msg += f"<b>Account:</b> {account}\n"
            msg += f"<b>Amount:</b> ${amount:,.2f}\n"
        else:
            # Default distribution
            msg += "<b>Distribution:</b>\n"
            msg += f"  • Low (45%): ${amount * 0.45:,.2f}\n"
            msg += f"  • Medium (35%): ${amount * 0.35:,.2f}\n"
            msg += f"  • High (20%): ${amount * 0.20:,.2f}\n"

        msg += "\n🔄 Investment will occur at next rebalance"

        await message.answer(msg, parse_mode="HTML")

    @router.message(Command("withdraw"))
    @telegram_handler("❌ Error processing withdrawal")
    async def cmd_withdraw(message: Message):
        """Handle /withdraw command - withdraw money from investor account.

        Usage: /withdraw <name> <amount> [account]

        Examples:
        /withdraw Cherry 1000 medium   → withdraw 1000 from medium account
        /withdraw Cherry 5000          → withdraw proportionally (45/35/20)

        account: low, medium, high (optional)
        """
        # Admin only
        if message.from_user.id not in ADMIN_IDS:
            await message.answer("❌ Admin only")
            return

        # Parse command
        parts = message.text.split()
        if len(parts) < 3 or len(parts) > 4:
            await message.answer(
                "Usage: /withdraw <name> <amount> [account]\n\n"
                "Examples:\n"
                "/withdraw Cherry 1000 medium\n"
                "/withdraw Cherry 5000\n\n"
                "Accounts: low, medium, high"
            )
            return

        investor_name = parts[1]

        try:
            amount = float(parts[2])
        except ValueError:
            await message.answer("❌ Invalid amount")
            return

        # Optional account
        account = parts[3].lower() if len(parts) == 4 else None

        # Validate account
        if account and account not in ['low', 'medium', 'high']:
            await message.answer(
                "❌ Invalid account. Use: low, medium, or high"
            )
            return

        # Check investor exists
        if not trading_bot.investor_manager.investor_exists(investor_name):
            await message.answer(f"❌ Investor '{investor_name}' not found")
            return

        # Check balance
        balance = trading_bot.investor_manager.calculate_investor_balance(
            investor_name
        )

        if account:
            # Withdraw from specific account
            available = balance[account]['total_value']
            if amount > available:
                await message.answer(
                    f"❌ Insufficient balance on {account}\n"
                    f"Available: ${available:,.2f}\n"
                    f"Requested: ${amount:,.2f}"
                )
                return
        else:
            # Withdraw proportionally
            total_available = balance['total_value']
            if amount > total_available:
                await message.answer(
                    f"❌ Insufficient balance\n"
                    f"Available: ${total_available:,.2f}\n"
                    f"Requested: ${amount:,.2f}"
                )
                return

        # Check for fee at withdrawal
        fee_info = trading_bot.investor_manager.check_and_calculate_fees(
            at_rebalance=False,
            for_investor=investor_name
        )

        # Create pending withdrawal operation
        try:
            from datetime import datetime
            operation_ids = trading_bot.investor_manager.withdraw(
                investor_name, amount, account, datetime.now()
            )
        except Exception as exc:
            await message.answer(f"❌ Error: {str(exc)}")
            return

        # Format response
        msg = f"✅ <b>Withdrawal Request Created</b>\n\n"
        msg += f"<b>Investor:</b> {investor_name}\n"
        msg += f"<b>Total Amount:</b> ${amount:,.2f}\n"
        msg += f"<b>Status:</b> pending\n\n"

        if account:
            # Specific account
            msg += f"<b>Account:</b> {account}\n"
            msg += f"<b>Amount:</b> ${amount:,.2f}\n"
        else:
            # Proportionally
            msg += "<b>Distribution:</b>\n"
            msg += f"  • Low (45%): ${amount * 0.45:,.2f}\n"
            msg += f"  • Medium (35%): ${amount * 0.35:,.2f}\n"
            msg += f"  • High (20%): ${amount * 0.20:,.2f}\n"

        # Show fee if applicable
        if fee_info and investor_name in fee_info:
            fee = fee_info[investor_name]
            msg += f"\n⚠️ <b>Performance fee:</b> ${fee:,.2f}\n"
            msg += f"<b>Net withdrawal:</b> ${amount - fee:,.2f}\n"

        msg += "\n🔄 Withdrawal will occur at next rebalance"

        await message.answer(msg, parse_mode="HTML")

    @router.message(Command("balance_check"))
    @telegram_handler("❌ Error checking balance integrity")
    async def cmd_balance_check(message: Message):
        """Handle /balance_check command - verify balance integrity."""
        # Admin only
        if message.from_user.id not in ADMIN_IDS:
            await message.answer("❌ Admin only")
            return

        loading_msg = await message.answer("⏳ Checking balance integrity...")

        # Get trading client for live strategy
        if 'live' not in trading_bot.strategies:
            await loading_msg.delete()
            await message.answer("❌ Live strategy not available")
            return

        trading_client = trading_bot.strategies['live']['client']

        # Check balance integrity
        is_valid, msg_text = await asyncio.to_thread(
            trading_bot.investor_manager.verify_balance_integrity,
            trading_client
        )

        icon = "✅" if is_valid else "❌"
        await loading_msg.delete()
        await message.answer(f"{icon} {msg_text}", parse_mode="HTML")

    @router.message(Command("investors"))
    @telegram_handler("❌ Error retrieving investors data")
    async def cmd_investors(message: Message):
        """Handle /investors command - show all investors balances."""
        loading_msg = await message.answer("⏳ Loading investors data...")

        # Get all balances
        balances = await asyncio.to_thread(
            trading_bot.investor_manager.get_all_balances
        )

        if not balances:
            await loading_msg.delete()
            await message.answer("❌ No investors found")
            return

        msg = "👥 <b>Investors Summary</b>\n\n"

        total_portfolio = 0.0
        total_pnl = 0.0

        for investor_name, data in balances.items():
            total_value = data.get('total_value', 0.0)
            pnl = data.get('pnl', 0.0)

            total_portfolio += total_value
            total_pnl += pnl

            msg += f"<b>{investor_name}</b>\n"
            msg += f"  💰 Balance: ${total_value:,.2f}\n"
            msg += f"  📈 P&L: ${pnl:,.2f}\n\n"

        msg += "─" * 40 + "\n"
        msg += f"<b>Total Portfolio:</b> ${total_portfolio:,.2f}\n"
        msg += f"<b>Total P&L:</b> ${total_pnl:,.2f}"

        await loading_msg.delete()
        await message.answer(msg, parse_mode="HTML")

    @router.message(Command("export"))
    @telegram_handler("❌ Error exporting data")
    async def cmd_export(message: Message):
        """Handle /export command - download investor CSV files.

        Usage: /export <name>
        Files: operations.csv, trades.csv
        """
        # Admin only
        if message.from_user.id not in ADMIN_IDS:
            await message.answer("❌ Admin only")
            return

        # Parse command
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("Usage: /export <name>")
            return

        investor_name = parts[1]

        # Check investor exists
        if not trading_bot.investor_manager.investor_exists(investor_name):
            await message.answer(f"❌ Investor '{investor_name}' not found")
            return

        # Get investor path
        investor_path = trading_bot.investor_manager._get_investor_path(investor_name)

        # Find and send files
        files_found = []
        files_to_send = ['operations.csv', 'trades.csv']

        for filename in files_to_send:
            file_path = investor_path / filename
            if file_path.exists():
                files_found.append((filename, file_path))

        if not files_found:
            await message.answer(f"❌ No files found for investor '{investor_name}'")
            return

        # Send files
        msg = f"📥 Exporting files for <b>{investor_name}</b>...\n\n"

        for filename, file_path in files_found:
            try:
                await message.answer_document(
                    FSInputFile(file_path),
                    caption=f"📄 {filename}"
                )
                msg += f"✅ {filename}\n"
            except Exception as exc:
                msg += f"❌ {filename}: {str(exc)}\n"

        await message.answer(msg, parse_mode="HTML")

    @router.message(Command("story"))
    @telegram_handler()
    async def cmd_story(message: Message):
        """Handle /story command - show available stories."""
        stories = story_engine.get_available_stories()

        if not stories:
            await message.answer("📖 No stories available yet.")
            return

        story_list = "🎭 **Available Stories**\n\n"
        for story in stories:
            story_list += (
                f"📖 **{story['title']}**\n"
                f"   Description: {story['description']}\n"
                f"   👥 Audience: {story['audience']}\n"
                f"   📚 Chapters: {story['chapters']}\n"
                f"   Start with: `/read_story {story['id']}`\n\n"
            )

        await message.answer(story_list, parse_mode="HTML")

    @router.message(Command("read_story"))
    @telegram_handler()
    async def cmd_read_story(message: Message):
        """Handle /read_story {story_id} - start reading a story."""
        args = message.text.split()

        if len(args) < 2:
            await message.answer(
                "📖 Usage: /read_story <story_id>\n\n"
                "Available story IDs:\n"
                "• digital_freedom_quest - The epic journey of a young trader"
            )
            return

        story_id = args[1]

        if not story_engine.start_story(story_id):
            await message.answer(f"❌ Story '{story_id}' not found.")
            return

        story = story_engine.active_story
        intro = story.get_story_intro()

        await message.answer(intro, parse_mode="HTML")

    @router.message(Command("read_chapter"))
    @telegram_handler()
    async def cmd_read_chapter(message: Message):
        """Handle /read_chapter - read next chapter of active story."""
        if not story_engine.active_story:
            await message.answer(
                "📖 No active story. Start one with:\n"
                "/read_story digital_freedom_quest"
            )
            return

        chapter = story_engine.get_current_chapter()

        if not chapter:
            await message.answer(
                "✅ Story completed! You've reached the end of this journey.\n\n"
                "Want another story? /story"
            )
            return

        chapter_text = (
            f"{chapter['emoji']} **{chapter['title']}**\n\n"
            f"{chapter['content']}\n\n"
            f"📖 {story_engine.active_story.get_progress()}"
        )

        await message.answer(chapter_text, parse_mode="HTML")

    @router.message(Command("story_status"))
    @telegram_handler()
    async def cmd_story_status(message: Message):
        """Handle /story_status - show current story progress."""
        status = story_engine.get_story_status()

        if not status:
            await message.answer(
                "📖 No active story yet.\n"
                "Start your journey: /read_story digital_freedom_quest"
            )
            return

        await message.answer(status, parse_mode="HTML")

    @router.message()
    async def echo(message: Message):
        """Handle all other messages."""
        await message.answer(
            "Use menu buttons or commands to control the bot.\n"
            "Type /help for assistance"
        )

    return router
