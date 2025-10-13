"""Фикстуры для тестов."""
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock
from typing import Dict, Any

import pytest
import pytz


@pytest.fixture
def mock_trading_client():
    """Мок TradingClient для тестов."""
    client = MagicMock()

    # Мок для get_account
    mock_account = Mock()
    mock_account.cash = "10000.00"
    mock_account.portfolio_value = "15000.00"
    client.get_account.return_value = mock_account

    # Мок для get_clock
    mock_clock = Mock()
    mock_clock.is_open = True
    client.get_clock.return_value = mock_clock

    # Мок для get_all_positions
    client.get_all_positions.return_value = []

    return client


@pytest.fixture
def mock_position():
    """Мок позиции для тестов."""
    position = Mock()
    position.symbol = "AAPL"
    position.qty = "10.0"
    position.market_value = "1500.00"
    position.unrealized_pl = "50.00"
    return position


@pytest.fixture
def sample_tickers():
    """Пример списка тикеров для тестов."""
    return ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA']


@pytest.fixture
def temp_flag_file(tmp_path: Path):
    """Временный файл для флага ребалансировки."""
    flag_path = tmp_path / "last_rebalance.txt"
    return flag_path


@pytest.fixture
def ny_timezone():
    """Временная зона Нью-Йорка."""
    return pytz.timezone('America/New_York')


@pytest.fixture
def mock_yfinance_data():
    """Мок данных yfinance."""
    import pandas as pd
    import numpy as np

    # Создаем DataFrame с историческими данными
    dates = pd.date_range(start='2023-01-01', end='2024-01-01', freq='D')
    tickers = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'META',
               'NVDA', 'JPM', 'BAC', 'WMT', 'XOM', 'CVX']

    # Генерируем случайные цены с разным momentum
    data = {}
    np.random.seed(42)
    for ticker in tickers:
        # Разный рост для разных акций
        growth_rate = np.random.uniform(0.0001, 0.0005)
        noise = np.random.normal(0, 0.01, len(dates))
        prices = 100 * np.exp(growth_rate * np.arange(len(dates)) + noise)
        data[ticker] = prices

    df = pd.DataFrame(data, index=dates)

    # Создаем MultiIndex колонки как в yfinance
    df.columns = pd.MultiIndex.from_product([['Close'], df.columns])

    return df


@pytest.fixture
def mock_telegram_message():
    """Мок Telegram сообщения."""
    message = Mock()
    message.answer = Mock()
    message.text = "Test message"
    message.from_user = Mock()
    message.from_user.id = 12345
    return message


@pytest.fixture
def mock_telegram_callback():
    """Мок Telegram callback query."""
    callback = Mock()
    callback.answer = Mock()
    callback.message = Mock()
    callback.message.answer = Mock()
    callback.data = "test_callback"
    return callback
