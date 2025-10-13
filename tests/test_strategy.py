"""Тесты для модуля strategy."""
from unittest.mock import Mock, patch, MagicMock

import pandas as pd
import pytest

from strategy import MomentumStrategy


def test_momentum_strategy_init(mock_trading_client, sample_tickers):
    """Тест инициализации стратегии."""
    strategy = MomentumStrategy(mock_trading_client, sample_tickers)

    assert strategy.trading_client == mock_trading_client
    assert strategy.tickers == sample_tickers


def test_get_signals(mock_trading_client, sample_tickers, mock_yfinance_data):
    """Тест получения торговых сигналов."""
    strategy = MomentumStrategy(mock_trading_client, sample_tickers)

    with patch('strategy.yf.download', return_value=mock_yfinance_data):
        signals = strategy.get_signals()

        assert isinstance(signals, list)
        assert len(signals) == 10  # Топ-10 акций
        assert all(isinstance(s, str) for s in signals)


def test_get_signals_no_close_column(mock_trading_client, sample_tickers):
    """Тест обработки отсутствия колонки Close."""
    strategy = MomentumStrategy(mock_trading_client, sample_tickers)

    # Создаем DataFrame без колонки Close
    bad_data = pd.DataFrame({'Open': [100, 101, 102]})

    with patch('strategy.yf.download', return_value=bad_data):
        with pytest.raises(KeyError, match="Столбец 'Close' отсутствует в данных"):
            strategy.get_signals()


def test_get_positions(mock_trading_client, sample_tickers):
    """Тест получения текущих позиций."""
    strategy = MomentumStrategy(mock_trading_client, sample_tickers)

    # Настраиваем мок позиций
    pos1 = Mock()
    pos1.symbol = "AAPL"
    pos1.qty = "10.5"

    pos2 = Mock()
    pos2.symbol = "GOOGL"
    pos2.qty = "5.0"

    mock_trading_client.get_all_positions.return_value = [pos1, pos2]

    positions = strategy.get_positions()

    assert positions == {"AAPL": 10.5, "GOOGL": 5.0}
    mock_trading_client.get_all_positions.assert_called_once()


def test_close_positions(mock_trading_client, sample_tickers):
    """Тест закрытия позиций."""
    strategy = MomentumStrategy(mock_trading_client, sample_tickers)

    positions_to_close = ["AAPL", "GOOGL"]
    strategy.close_positions(positions_to_close)

    assert mock_trading_client.close_position.call_count == 2
    mock_trading_client.close_position.assert_any_call("AAPL")
    mock_trading_client.close_position.assert_any_call("GOOGL")


def test_close_positions_with_error(mock_trading_client, sample_tickers):
    """Тест обработки ошибок при закрытии позиций."""
    strategy = MomentumStrategy(mock_trading_client, sample_tickers)

    # Настраиваем мок, чтобы вызвать исключение
    mock_trading_client.close_position.side_effect = Exception("API Error")

    positions_to_close = ["AAPL"]
    # Не должно упасть, только залогирует ошибку
    strategy.close_positions(positions_to_close)

    mock_trading_client.close_position.assert_called_once_with("AAPL")


def test_open_positions(mock_trading_client, sample_tickers):
    """Тест открытия новых позиций."""
    strategy = MomentumStrategy(mock_trading_client, sample_tickers)

    tickers_to_open = ["AAPL", "GOOGL"]
    cash_per_position = 1000.0

    strategy.open_positions(tickers_to_open, cash_per_position)

    assert mock_trading_client.submit_order.call_count == 2

    # Проверяем параметры первого вызова
    first_call_args = mock_trading_client.submit_order.call_args_list[0][0][0]
    assert first_call_args.symbol == "AAPL"
    assert first_call_args.notional == 1000.0


def test_open_positions_with_error(mock_trading_client, sample_tickers):
    """Тест обработки ошибок при открытии позиций."""
    strategy = MomentumStrategy(mock_trading_client, sample_tickers)

    # Настраиваем мок, чтобы вызвать исключение
    mock_trading_client.submit_order.side_effect = Exception("API Error")

    tickers_to_open = ["AAPL"]
    # Не должно упасть, только залогирует ошибку
    strategy.open_positions(tickers_to_open, 1000.0)

    mock_trading_client.submit_order.assert_called_once()


def test_rebalance_full_scenario(mock_trading_client, sample_tickers, mock_yfinance_data):
    """Тест полного сценария ребалансировки."""
    strategy = MomentumStrategy(mock_trading_client, sample_tickers)

    # Настраиваем текущие позиции - используем тикер, которого нет в sample_tickers
    pos1 = Mock()
    pos1.symbol = "IBM"  # Этот тикер не в sample_tickers, будет закрыт
    pos1.qty = "10.0"

    mock_trading_client.get_all_positions.return_value = [pos1]

    # Настраиваем аккаунт
    mock_account = Mock()
    mock_account.cash = "10000.00"
    mock_trading_client.get_account.return_value = mock_account

    with patch('strategy.yf.download', return_value=mock_yfinance_data):
        with patch('strategy.time.sleep'):  # Пропускаем sleep
            strategy.rebalance()

    # Проверяем, что позиция IBM была закрыта (т.к. не в топ-10 из sample_tickers)
    # На самом деле, из-за того, что мы используем только 5 тикеров в sample_tickers,
    # все они войдут в топ-10, и IBM будет закрыт
    mock_trading_client.close_position.assert_called_with("IBM")

    # Проверяем, что были открыты новые позиции
    assert mock_trading_client.submit_order.called


def test_rebalance_insufficient_cash(mock_trading_client, sample_tickers, mock_yfinance_data):
    """Тест ребалансировки с недостаточным количеством средств."""
    strategy = MomentumStrategy(mock_trading_client, sample_tickers)

    mock_trading_client.get_all_positions.return_value = []

    # Настраиваем аккаунт с нулевым балансом
    mock_account = Mock()
    mock_account.cash = "0.00"
    mock_trading_client.get_account.return_value = mock_account

    with patch('strategy.yf.download', return_value=mock_yfinance_data):
        strategy.rebalance()

    # Проверяем, что новые позиции не открывались
    mock_trading_client.submit_order.assert_not_called()


def test_rebalance_position_size_too_small(mock_trading_client, sample_tickers, mock_yfinance_data):
    """Тест ребалансировки когда размер позиции слишком мал."""
    strategy = MomentumStrategy(mock_trading_client, sample_tickers)

    mock_trading_client.get_all_positions.return_value = []

    # Настраиваем аккаунт с очень маленьким балансом
    mock_account = Mock()
    mock_account.cash = "0.50"  # Меньше 1 доллара на позицию
    mock_trading_client.get_account.return_value = mock_account

    with patch('strategy.yf.download', return_value=mock_yfinance_data):
        strategy.rebalance()

    # Проверяем, что новые позиции не открывались
    mock_trading_client.submit_order.assert_not_called()
