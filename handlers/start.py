"""Start command handler."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardRemove


def setup_start_router():
    """Setup router with start command.

    Returns:
        Router: Configured router with start handler
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

    return router
