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
    """Mock yfinance download with real MultiIndex structure (Ticker, Price)"""
    index = pd.date_range("2023-11-07", periods=250, freq="D", name="Date")
    columns = pd.MultiIndex.from_arrays(
        [
            ["AAPL"] * 5 + ["GOOGL"] * 5 + ["MSFT"] * 5,  # Level 0: Ticker
            ["Open", "High", "Low", "Close", "Volume"] * 3,  # Level 1: Price field
        ],
        names=["Ticker", "Price"],
    )
    data_values = [[100 + i, 101 + i, 99 + i, 100.5 + i, 1000000 + i * 100]
                   for i in range(250)]
    # Repeat for 3 tickers
    data_values_full = []
    for row in data_values:
        data_values_full.append(row * 3)

    df = pd.DataFrame(data_values_full, index=index, columns=columns)
    monkeypatch.setattr("yfinance.download", MagicMock(return_value=df))
    return df


@pytest.fixture
def mock_data_loader(monkeypatch):
    """Mock DataLoader.load_market_data with real MultiIndex structure (Ticker, Price)"""
    index = pd.date_range("2023-11-07", periods=250, freq="D", name="Date")
    columns = pd.MultiIndex.from_arrays(
        [
            ["AAPL"] * 5 + ["GOOGL"] * 5 + ["MSFT"] * 5,  # Level 0: Ticker
            ["Open", "High", "Low", "Close", "Volume"] * 3,  # Level 1: Price field
        ],
        names=["Ticker", "Price"],
    )
    data_values = [[100 + i, 101 + i, 99 + i, 100.5 + i, 1000000 + i * 100]
                   for i in range(250)]
    # Repeat for 3 tickers
    data_values_full = []
    for row in data_values:
        data_values_full.append(row * 3)

    df = pd.DataFrame(data_values_full, index=index, columns=columns)
    monkeypatch.setattr("data_loader.DataLoader.load_market_data", MagicMock(return_value=df))
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
