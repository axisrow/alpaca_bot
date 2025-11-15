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


def setup_admin_router(trading_bot_state):
    """Setup router with admin commands.

    Args:
        trading_bot_state: Trading bot state dictionary

    Returns:
        Router: Configured router with handlers
    """
    router = Router()

    @router.message(Command("check_rebalance"))
    @telegram_handler("❌ Error retrieving rebalance information")
    async def cmd_check_rebalance(message: Message):
        """Handle /check_rebalance command."""
        from core.alpaca_bot import calculate_days_until_rebalance, get_next_rebalance_date
        from core.rebalance_flag import get_countdown_message

        days_until = calculate_days_until_rebalance(trading_bot_state)
        next_date = get_next_rebalance_date(trading_bot_state)
        msg = get_countdown_message(days_until, next_date)

        await message.answer(msg, parse_mode="HTML")

    @router.message(Command("test_rebalance"))
    @telegram_handler("❌ Error running test rebalance")
    async def cmd_test_rebalance(message: Message):
        """Handle /test_rebalance command (dry run for all strategies)."""
        from core.alpaca_bot import get_rebalance_preview

        loading_msg = await message.answer("⏳ Загружаю данные для ребалансировки...")
        previews = await asyncio.to_thread(get_rebalance_preview, trading_bot_state)

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
            from core.alpaca_bot import calculate_total_close_value
            total_close_value = calculate_total_close_value(positions_to_close, positions_dict)

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
        from core.alpaca_bot import execute_rebalance, set_awaiting_rebalance_confirmation

        if not trading_bot_state.get('awaiting_rebalance_confirmation'):
            await message.answer("❌ No pending rebalance request")
            return

        await message.answer("✅ Rebalance approved. Executing...")

        # Execute rebalance
        logging.info("Executing rebalance (approved by admin)")
        await asyncio.to_thread(execute_rebalance, trading_bot_state)
        set_awaiting_rebalance_confirmation(trading_bot_state, False)

        await message.answer("✅ Portfolio rebalancing completed successfully")

    @router.message(F.text.lower().in_(["нет", "no", "n"]))
    @telegram_handler("❌ Error rejecting rebalance")
    async def reject_rebalance(message: Message):
        """Handle rebalance rejection."""
        from core.alpaca_bot import set_awaiting_rebalance_confirmation

        if not trading_bot_state.get('awaiting_rebalance_confirmation'):
            await message.answer("❌ No pending rebalance request")
            return

        await message.answer("❌ Rebalance rejected")
        logging.info("Rebalance rejected by admin")
        set_awaiting_rebalance_confirmation(trading_bot_state, False)

    @router.message(Command("deposit"))
    @telegram_handler("❌ Error processing deposit")
    async def cmd_deposit(message: Message):
        """Handle /deposit command."""
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
            await message.answer("❌ Invalid account. Use: low, medium, or high")
            return

        # Get investor manager state
        investor_manager_state = trading_bot_state.get('investor_manager_state')
        if not investor_manager_state:
            await message.answer("❌ Investor manager not available")
            return

        # Check investor exists
        from core.investor_manager import investor_exists, deposit
        if not investor_exists(investor_manager_state, investor_name):
            await message.answer(f"❌ Investor '{investor_name}' not found")
            return

        # Create pending deposit operation
        try:
            operation_ids = deposit(
                investor_manager_state,
                investor_name,
                amount,
                account,
                datetime.now()
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
            msg += f"<b>Account:</b> {account}\n"
            msg += f"<b>Amount:</b> ${amount:,.2f}\n"
        else:
            msg += "<b>Distribution:</b>\n"
            msg += f"  • Low (45%): ${amount * 0.45:,.2f}\n"
            msg += f"  • Medium (35%): ${amount * 0.35:,.2f}\n"
            msg += f"  • High (20%): ${amount * 0.20:,.2f}\n"

        msg += "\n🔄 Investment will occur at next rebalance"

        await message.answer(msg, parse_mode="HTML")

    @router.message(Command("withdraw"))
    @telegram_handler("❌ Error processing withdrawal")
    async def cmd_withdraw(message: Message):
        """Handle /withdraw command."""
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
            await message.answer("❌ Invalid account. Use: low, medium, or high")
            return

        # Get investor manager state
        investor_manager_state = trading_bot_state.get('investor_manager_state')
        if not investor_manager_state:
            await message.answer("❌ Investor manager not available")
            return

        from core.investor_manager import (
            investor_exists, calculate_investor_balance,
            check_and_calculate_fees, withdraw
        )

        # Check investor exists
        if not investor_exists(investor_manager_state, investor_name):
            await message.answer(f"❌ Investor '{investor_name}' not found")
            return

        # Check balance
        balance = calculate_investor_balance(investor_manager_state, investor_name)

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
        fee_info = check_and_calculate_fees(
            investor_manager_state,
            at_rebalance=False,
            for_investor=investor_name
        )

        # Create pending withdrawal operation
        try:
            operation_ids = withdraw(
                investor_manager_state,
                investor_name,
                amount,
                account,
                datetime.now()
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
            msg += f"<b>Account:</b> {account}\n"
            msg += f"<b>Amount:</b> ${amount:,.2f}\n"
        else:
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
        """Handle /balance_check command."""
        # Admin only
        if message.from_user.id not in ADMIN_IDS:
            await message.answer("❌ Admin only")
            return

        loading_msg = await message.answer("⏳ Checking balance integrity...")

        # Get trading client for live strategy
        if 'live' not in trading_bot_state['strategies']:
            await loading_msg.delete()
            await message.answer("❌ Live strategy not available")
            return

        trading_client = trading_bot_state['strategies']['live']['client']
        investor_manager_state = trading_bot_state.get('investor_manager_state')

        if not investor_manager_state:
            await loading_msg.delete()
            await message.answer("❌ Investor manager not available")
            return

        # Check balance integrity
        from core.investor_manager import verify_balance_integrity
        is_valid, msg_text = await asyncio.to_thread(
            verify_balance_integrity,
            investor_manager_state,
            trading_client
        )

        icon = "✅" if is_valid else "❌"
        await loading_msg.delete()
        await message.answer(f"{icon} {msg_text}", parse_mode="HTML")

    @router.message(Command("investors"))
    @telegram_handler("❌ Error retrieving investors data")
    async def cmd_investors(message: Message):
        """Handle /investors command."""
        loading_msg = await message.answer("⏳ Loading investors data...")

        investor_manager_state = trading_bot_state.get('investor_manager_state')
        if not investor_manager_state:
            await loading_msg.delete()
            await message.answer("❌ Investor manager not available")
            return

        # Get all balances
        from core.investor_manager import get_all_balances
        balances = await asyncio.to_thread(get_all_balances, investor_manager_state)

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
        """Handle /export command."""
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

        investor_manager_state = trading_bot_state.get('investor_manager_state')
        if not investor_manager_state:
            await message.answer("❌ Investor manager not available")
            return

        from core.investor_manager import investor_exists
        # Check investor exists
        if not investor_exists(investor_manager_state, investor_name):
            await message.answer(f"❌ Investor '{investor_name}' not found")
            return

        # Get investor path
        investor_path = investor_manager_state['investors_dir'] / investor_name

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

    return router
