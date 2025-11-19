"""Admin command handlers."""
import asyncio
import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile

from config import ADMIN_IDS, CACHE_FILE
from core.data_loader import clear_cache
from core.utils import telegram_handler


def setup_admin_router(trading_bot):
    """Setup router with admin commands.

    Args:
        trading_bot: Trading bot instance

    Returns:
        Router: Configured router with handlers
    """
    router = Router()

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

        summary = trading_bot.build_rebalance_summary(previews)
        msg = (
            "📊 <b>Rebalance Preview (DRY RUN)</b>\n\n"
            f"{summary}\n\n"
            "⚠️ <i>This is a DRY RUN - no trades executed</i>"
        )

        await loading_msg.delete()
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
        cache_file = CACHE_FILE
        cache_size = 0

        if cache_file.exists():
            cache_size = cache_file.stat().st_size

        # Clear cache
        clear_cache()

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

    @router.message(Command("force_rebalance"))
    @telegram_handler("❌ Error executing forced rebalance")
    async def cmd_force_rebalance(message: Message):
        """Handle /force_rebalance command - force portfolio rebalancing."""
        # Admin only
        if message.from_user.id not in ADMIN_IDS:
            await message.answer("❌ Admin only")
            return

        # Show preview
        loading_msg = await message.answer("⏳ Calculating rebalance preview...")
        previews = await asyncio.to_thread(trading_bot.get_rebalance_preview)

        if not previews:
            await loading_msg.delete()
            raise ValueError("No rebalance preview available")

        summary = trading_bot.build_rebalance_summary(previews)
        await loading_msg.edit_text(
            f"📊 <b>Forced Rebalance Preview</b>\n\n"
            f"{summary}\n\n"
            "⚠️ <i>Executing forced rebalance (ignoring all checks)...</i>",
            parse_mode="HTML"
        )

        # Execute rebalance
        await asyncio.to_thread(trading_bot.execute_rebalance)
        await message.answer("✅ Forced rebalance completed successfully")

    return router
