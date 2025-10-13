"""Тесты для модуля utils."""
import time
from unittest.mock import Mock, patch

import pytest

from utils import retry_on_exception


def test_retry_on_exception_success():
    """Тест успешного выполнения функции с первого раза."""
    @retry_on_exception(retries=3, delay=0)
    def success_function():
        return "success"

    result = success_function()
    assert result == "success"


def test_retry_on_exception_retry_and_success():
    """Тест повторных попыток с успешным выполнением."""
    mock_func = Mock(side_effect=[Exception("Error 1"), Exception("Error 2"), "success"])

    @retry_on_exception(retries=3, delay=0)
    def retry_function():
        return mock_func()

    result = retry_function()
    assert result == "success"
    assert mock_func.call_count == 3


def test_retry_on_exception_all_failures():
    """Тест исчерпания всех попыток."""
    mock_func = Mock(side_effect=Exception("Persistent error"))

    @retry_on_exception(retries=3, delay=0)
    def failing_function():
        return mock_func()

    with pytest.raises(Exception, match="Persistent error"):
        failing_function()

    assert mock_func.call_count == 3


def test_retry_on_exception_with_delay():
    """Тест задержки между попытками."""
    mock_func = Mock(side_effect=[Exception("Error 1"), "success"])

    @retry_on_exception(retries=3, delay=0.1)
    def delayed_function():
        return mock_func()

    start = time.time()
    result = delayed_function()
    elapsed = time.time() - start

    assert result == "success"
    assert elapsed >= 0.1  # Проверяем, что была задержка
    assert mock_func.call_count == 2


def test_retry_on_exception_with_args():
    """Тест работы декоратора с аргументами функции."""
    @retry_on_exception(retries=3, delay=0)
    def function_with_args(a, b, c=10):
        return a + b + c

    result = function_with_args(5, 3, c=2)
    assert result == 10


def test_retry_on_exception_different_exception_types():
    """Тест обработки разных типов исключений."""
    mock_func = Mock(side_effect=[ValueError("Value error"), TypeError("Type error"), "success"])

    @retry_on_exception(retries=3, delay=0)
    def multi_exception_function():
        return mock_func()

    result = multi_exception_function()
    assert result == "success"
    assert mock_func.call_count == 3
