"""Pytest configuration and fixtures."""
import subprocess
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def pytest_sessionstart(session):
    """
    Called before the test session starts.
    Kills any running instance of the bot to ensure a clean environment.
    """
    try:
        # Kill any process matching "bot.py" (more robust than "python bot.py")
        subprocess.run(["pkill", "-f", "bot.py"], check=False)
        print("\n[INFO] Killed running bot instances (if any).")
    except Exception as e:
        print(f"\n[WARNING] Failed to kill bot instances: {e}")


@pytest.fixture
def mock_trading_client():
    """Mock Alpaca trading client."""
    client = MagicMock()
    client.get_account.return_value = MagicMock(
        portfolio_value=100000.0,
        cash=50000.0
    )
    client.get_all_positions.return_value = []
    client.get_orders.return_value = []
    return client


@pytest.fixture
def mock_strategy():
    """Mock trading strategy."""
    strategy = MagicMock()
    strategy.rebalance.return_value = None
    strategy.get_signals.return_value = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'AMZN']
    return strategy


@pytest.fixture
def mock_data_loader():
    """Mock market data helpers exported inside core.alpaca_bot."""
    with patch('core.alpaca_bot.get_snp500_tickers') as mock_get_tickers, \
            patch('core.alpaca_bot.load_market_data') as mock_load_market_data:
        mock_get_tickers.return_value = [
            'AAPL', 'MSFT', 'GOOGL', 'TSLA', 'AMZN'
        ] * 2
        mock_load_market_data.return_value = None
        yield SimpleNamespace(
            get_snp500_tickers=mock_get_tickers,
            load_market_data=mock_load_market_data,
        )


@pytest.fixture
def mock_investor_manager():
    """Mock investor manager."""
    manager = MagicMock()
    manager.get_pending_operations.return_value = []
    manager.save_daily_snapshot.return_value = None
    return manager


@pytest.fixture
def mock_market_schedule():
    """Mock market schedule."""
    schedule = MagicMock()
    schedule.check_market_status.return_value = (True, "Market open")
    schedule.count_trading_days.return_value = 22
    return schedule


@pytest.fixture
def mock_rebalance_flag():
    """Mock rebalance flag."""
    flag = MagicMock()
    flag.has_rebalanced_today.return_value = False
    flag.get_last_rebalance_date.return_value = None
    flag.get_countdown_message.return_value = "Days until rebalance: 0"
    return flag


@pytest.fixture
def mock_portfolio_manager():
    """Mock portfolio manager."""
    manager = MagicMock()
    return manager
