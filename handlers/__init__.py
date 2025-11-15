"""Handlers package."""
from aiogram import Router

from .start import setup_start_router
from .admins import setup_admin_router
from .users import setup_user_router
from .catchall import setup_catchall_router


def setup_router(trading_bot):
    """Setup main router combining user and admin routers.

    Args:
        trading_bot: Trading bot instance

    Returns:
        Router: Main router with all handlers
    """
    main_router = Router()

    # Include routers in priority order:
    # 1. Start router (most important)
    # 2. Admin router (specific admin commands)
    # 3. User router (general user commands)
    # 4. Catchall router (unknown messages - MUST be last)
    main_router.include_router(setup_start_router())
    main_router.include_router(setup_admin_router(trading_bot))
    main_router.include_router(setup_user_router(trading_bot))
    main_router.include_router(setup_catchall_router())

    return main_router
