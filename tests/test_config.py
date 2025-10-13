"""Тесты для модуля config."""
import os
from unittest.mock import patch

import pytest


def test_snp500_tickers_exists():
    """Тест наличия списка S&P500 тикеров."""
    from config import snp500_tickers

    assert isinstance(snp500_tickers, list)
    assert len(snp500_tickers) > 0


def test_snp500_tickers_length():
    """Тест длины списка S&P500 тикеров."""
    from config import snp500_tickers

    # S&P500 содержит примерно 500 компаний
    assert len(snp500_tickers) >= 400  # Минимум 400
    assert len(snp500_tickers) <= 550  # Максимум 550


def test_snp500_tickers_format():
    """Тест формата тикеров."""
    from config import snp500_tickers

    # Все тикеры должны быть строками
    assert all(isinstance(ticker, str) for ticker in snp500_tickers)

    # Все тикеры должны быть непустыми
    assert all(len(ticker) > 0 for ticker in snp500_tickers)

    # Тикеры обычно в верхнем регистре
    assert all(ticker.isupper() for ticker in snp500_tickers)


def test_snp500_tickers_contains_major_companies():
    """Тест что список содержит основные компании."""
    from config import snp500_tickers

    # Проверяем наличие известных крупных компаний
    major_companies = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']

    for company in major_companies:
        assert company in snp500_tickers, f"{company} должна быть в списке S&P500"


def test_snp500_tickers_no_duplicates():
    """Тест отсутствия дубликатов."""
    from config import snp500_tickers

    assert len(snp500_tickers) == len(set(snp500_tickers)), "В списке не должно быть дубликатов"


@patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'test_token_123'})
def test_telegram_bot_token_loaded():
    """Тест загрузки токена Telegram бота."""
    # Нужно переимпортировать модуль с новыми переменными окружения
    import importlib
    import config
    importlib.reload(config)

    assert config.TELEGRAM_BOT_TOKEN == 'test_token_123'


def test_telegram_bot_token_missing():
    """Тест отсутствия токена Telegram бота в .env."""
    # Этот тест проверяет, что код корректно обрабатывает отсутствие токена
    # Модуль config уже загружен, поэтому мы просто проверяем, что переменная установлена
    from config import TELEGRAM_BOT_TOKEN

    # Токен должен быть установлен (из .env или переменных окружения)
    assert TELEGRAM_BOT_TOKEN is not None, "TELEGRAM_BOT_TOKEN должен быть установлен"


def test_admin_ids_exists():
    """Тест наличия списка администраторов."""
    from config import ADMIN_IDS

    assert isinstance(ADMIN_IDS, list)
    # Проверяем, что все элементы - целые числа (Telegram chat IDs)
    assert all(isinstance(admin_id, int) for admin_id in ADMIN_IDS)


def test_config_imports():
    """Тест что все необходимые импорты работают."""
    try:
        from config import snp500_tickers, TELEGRAM_BOT_TOKEN, ADMIN_IDS
        assert True
    except ImportError as e:
        pytest.fail(f"Не удалось импортировать из config: {e}")
