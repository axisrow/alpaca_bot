"""Utilities and helper functions."""
import logging
import time
from functools import wraps
from typing import Callable, TypeVar, Any, Dict

T = TypeVar('T')


def retry_on_exception(
    retries: int = 3,
    delay: int = 1
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for retrying function execution on exception.

    Args:
        retries: Number of execution attempts
        delay: Delay between attempts in seconds

    Returns:
        Decorated function with retry mechanism
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    if attempt == retries:
                        logging.error(
                            "All %d attempts failed for %s (final error): %s",
                            retries,
                            func.__name__,
                            exc,
                            exc_info=True
                        )
                        raise
                    logging.warning(
                        "Attempt %d/%d failed for %s: %s",
                        attempt,
                        retries,
                        func.__name__,
                        exc
                    )
                    time.sleep(delay)
            raise RuntimeError("Unexpected: retry loop completed without returning or raising")
        return wrapper
    return decorator


@retry_on_exception()
def get_positions(trading_client) -> Dict[str, float]:
    """Get current trading positions.

    Args:
        trading_client: Alpaca trading client

    Returns:
        Dict[str, float]: Dictionary of positions {ticker: quantity}
    """
    positions = trading_client.get_all_positions()
    return {pos.symbol: float(pos.qty) for pos in positions}


def telegram_handler(error_message: str = "❌ An error occurred"):
    """Decorator for handling Telegram command errors.

    Args:
        error_message: Default error message to send on exception

    Returns:
        Decorated function with error handling
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(message, *args: Any, **kwargs: Any) -> Any:
            try:
                return await func(message, *args, **kwargs)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                user_id = (
                    getattr(message, 'from_user', {}).id
                    if hasattr(message, 'from_user') else 'unknown'
                )
                logging.error(
                    "Error in Telegram command %s (user %s): %s",
                    func.__name__,
                    user_id,
                    exc,
                    exc_info=True
                )
                await message.answer(error_message)
        return wrapper
    return decorator
