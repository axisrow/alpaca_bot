"""Утилиты и вспомогательные функции."""
import logging
import time
from functools import wraps
from typing import Callable, TypeVar, Any

T = TypeVar('T')


def retry_on_exception(
    retries: int = 3,
    delay: int = 1
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Декоратор для повторных попыток выполнения функции при исключении.

    Args:
        retries: Количество попыток выполнения
        delay: Задержка между попытками в секундах

    Returns:
        Декорированная функция с механизмом повторных попыток
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
                        "Попытка %d не удалась: %s",
                        attempt + 1,
                        exc
                    )
                    time.sleep(delay)
        return wrapper
    return decorator
