import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from datetime import datetime, timedelta
import pandas as pd
import pytz

NY_TZ = pytz.timezone("America/New_York")


@pytest.fixture
def mock_trading_client():
    """Mock Alpaca TradingClient with all necessary methods"""
    client = MagicMock()

    # Mock clock for market status
    clock_mock = MagicMock()
    clock_mock.is_open = True
    client.get_clock.return_value = clock_mock

    # Mock account
    account_mock = MagicMock()
    account_mock.cash = 10000.0
    account_mock.portfolio_value = 20000.0
    client.get_account.return_value = account_mock

    # Mock positions
    position_mock = MagicMock()
    position_mock.symbol = "AAPL"
    position_mock.qty = 10.0
    position_mock.market_value = 1500.0
    position_mock.unrealized_pl = 100.0
    client.get_all_positions.return_value = [position_mock]

    # Mock close_position
    client.close_position.return_value = None

    # Mock submit_order
    order_mock = MagicMock()
    order_mock.symbol = "AAPL"
    order_mock.qty = 5
    client.submit_order.return_value = order_mock

    # Mock get_orders
    client.get_orders.return_value = []

    return client


@pytest.fixture
def mock_yfinance(monkeypatch):
    """Mock yfinance download"""
    df = pd.DataFrame({
        "Close": [100 + i for i in range(250)]  # 250 trading days
    })
    monkeypatch.setattr("yfinance.download", MagicMock(return_value=df))
    return df


@pytest.fixture
def mock_telegram_message():
    """Mock Telegram Message object"""
    message = AsyncMock()
    message.answer = AsyncMock()
    return message


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mock environment variables"""
    monkeypatch.setenv('ALPACA_API_KEY', 'test_key')
    monkeypatch.setenv('ALPACA_SECRET_KEY', 'test_secret')
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'test_token')


@pytest.fixture
def current_ny_time():
    """Fixture providing current NY time"""
    return datetime.now(NY_TZ)
