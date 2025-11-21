"""Tests for strategy tradable ticker filtering."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from strategies.base import BaseMomentumStrategy
from strategies.live import LiveStrategy


@pytest.mark.parametrize(
    "strategy_cls",
    [BaseMomentumStrategy, LiveStrategy],
)
def test_filter_keeps_non_fractionable_assets(strategy_cls):
    """Non-fractionable, но активные/торгуемые тикеры не должны отсеиваться."""
    trading_client = MagicMock()
    trading_client.get_asset.side_effect = [
        SimpleNamespace(status='active', tradable=True, fractionable=False),
        SimpleNamespace(status='active', tradable=True, fractionable=True),
    ]

    strategy = strategy_cls(trading_client=trading_client, tickers=[], top_count=2)

    filtered = strategy._filter_tradable_tickers(['DFDV', 'AAPL'])

    assert filtered == ['DFDV', 'AAPL']
    assert trading_client.get_asset.call_count == 2


def test_base_strategy_buys_whole_shares_for_non_fractionable(monkeypatch):
    """Base strategy должна использовать qty для нефракционных активов."""
    trading_client = MagicMock()
    trading_client.get_asset.return_value = SimpleNamespace(status='active', tradable=True, fractionable=False)

    strategy = BaseMomentumStrategy(trading_client=trading_client, tickers=['DFDV'])
    monkeypatch.setattr(strategy, "_preload_last_prices", lambda tickers: {'DFDV': 20.0})

    strategy.open_positions(['DFDV'], cash_per_position=50.0)

    order = trading_client.submit_order.call_args[0][0]
    assert getattr(order, 'qty', None) == 2
    assert getattr(order, 'notional', None) in (None, 0)


def test_live_strategy_buys_whole_shares_for_non_fractionable(monkeypatch):
    """Live strategy должна использовать qty для нефракционных активов."""
    trading_client = MagicMock()
    trading_client.get_asset.side_effect = [
        SimpleNamespace(status='active', tradable=True, fractionable=False),
        SimpleNamespace(status='active', tradable=True, fractionable=False),
    ]

    strategy = LiveStrategy(trading_client=trading_client, tickers=['DFDV'])
    monkeypatch.setattr(strategy, "_preload_last_prices", lambda tickers: {'DFDV': 25.0})

    strategy._open_account_positions('low', ['DFDV'], cash_per_position=60.0)

    order = trading_client.submit_order.call_args[0][0]
    assert getattr(order, 'qty', None) == 2
    assert getattr(order, 'notional', None) in (None, 0)
