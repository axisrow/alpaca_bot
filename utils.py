"""Utilities and helper functions."""
import logging
import time
from functools import wraps
from typing import Callable, TypeVar, Any

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
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    if attempt == retries - 1:
                        raise
                    logging.warning(
                        "Attempt %d failed: %s",
                        attempt + 1,
                        exc
                    )
                    time.sleep(delay)
        return wrapper
    return decorator
