"""Catch-all handler for unknown messages."""
from aiogram import Router
from aiogram.types import Message


def setup_catchall_router():
    """Setup router with catch-all handler for unknown messages.

    Returns:
        Router: Configured router with catch-all handler
    """
    router = Router()

    @router.message()
    async def echo(message: Message):
        """Handle all other messages."""
        await message.answer(
            "Use menu buttons or commands to control the bot.\n"
            "Type /help for assistance"
        )

    return router
