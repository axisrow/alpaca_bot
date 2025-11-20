import pytest
from unittest.mock import MagicMock, patch
from strategies.live import LiveStrategy
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce

class MockOrder:
    def __init__(self, id, filled_avg_price=None, filled_qty=None):
        self.id = id
        self.filled_avg_price = filled_avg_price
        self.filled_qty = filled_qty

@pytest.fixture
def mock_trading_client():
    return MagicMock()

@pytest.fixture
def mock_investor_manager():
    return MagicMock()

def test_open_account_positions_fallback_logic(mock_trading_client, mock_investor_manager):
    """
    Test that verifies the incorrect fallback logic when order status is not available.
    Current behavior (Bug): If order status check fails, it defaults to shares=1.0 and price=cash_per_position.
    """
    # Setup
    strategy = LiveStrategy(trading_client=mock_trading_client, tickers=['AAPL'], investor_manager=mock_investor_manager)
    
    # Mock submit_order to return an order with an ID
    mock_trading_client.submit_order.return_value = MockOrder(id="test_order_id")
    
    # Mock get_order_by_id to always return an order WITHOUT filled info (simulating delay/timeout)
    # In the actual code, it retries 10 times. We'll make it return an empty/unfilled order every time.
    mock_trading_client.get_order_by_id.return_value = MockOrder(id="test_order_id", filled_avg_price=None, filled_qty=None)
    
    account_name = "low"
    tickers = ["AAPL"]
    cash_per_position = 1000.0
    
    # Mock data_client
    mock_data_client = MagicMock()
    strategy.data_client = mock_data_client
    
    # Mock get_stock_latest_trade response
    mock_trade = MagicMock()
    mock_trade.price = 200.0
    mock_data_client.get_stock_latest_trade.return_value = {'AAPL': mock_trade}

    # Execute
    strategy._open_account_positions(account_name, tickers, cash_per_position)
    
    # Verify
    # The fix should cause distribute_trade_to_investors to be called with:
    # shares = 1000.0 / 200.0 = 5.0
    # price = 200.0
    
    mock_investor_manager.distribute_trade_to_investors.assert_called_once()
    call_args = mock_investor_manager.distribute_trade_to_investors.call_args
    
    # Check arguments: account, action, ticker, shares, price
    assert call_args[0][0] == account_name
    assert call_args[0][1] == 'BUY'
    assert call_args[0][2] == 'AAPL'
    
    shares_arg = call_args[0][3]
    price_arg = call_args[0][4]
    
    print(f"Recorded Trade -> Shares: {shares_arg}, Price: {price_arg}")
    
    assert shares_arg == 5.0, f"Fix verification failed: Shares should be 5.0 (1000/200), got {shares_arg}"
    assert price_arg == 200.0, f"Fix verification failed: Price should be 200.0, got {price_arg}"


def test_rebalance_uses_broker_positions_only(monkeypatch):
    """Strategy should rely on broker positions (not ledger) when deciding closes/opens."""

    class FakePosition:
        def __init__(self, symbol):
            self.symbol = symbol
            self.qty = 1

    class FakeAccount:
        def __init__(self, equity: float):
            self.equity = equity

    trading_client = MagicMock()
    trading_client.get_all_positions.return_value = [FakePosition('OLD1'), FakePosition('OLD2')]
    trading_client.get_account.return_value = FakeAccount(10000.0)

    strategy = LiveStrategy(trading_client=trading_client, tickers=['OLD2', 'NEW1'])

    closed = []
    opened = []

    # Guard: raising here would show we touched ledger-based positions
    monkeypatch.setattr(LiveStrategy, "_get_investor_positions", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ledger should not be used")))
    monkeypatch.setattr(strategy, "_get_account_tickers", lambda account_name: ['OLD2', 'NEW1'])
    monkeypatch.setattr(strategy, "_calculate_signals", lambda tickers: ['OLD2', 'NEW1'])
    monkeypatch.setattr(strategy, "_close_account_positions", lambda account_name, positions: closed.append((account_name, sorted(positions))))
    monkeypatch.setattr(strategy, "_open_account_positions", lambda account_name, tickers, size: opened.append((account_name, sorted(tickers))))

    strategy.rebalance()

    # Each account (low/medium/high) should try to close OLD1 (broker fact) and open NEW1
    assert closed == [
        ('low', ['OLD1']),
        ('medium', ['OLD1']),
        ('high', ['OLD1'])
    ]
    assert opened == [
        ('low', ['NEW1']),
        ('medium', ['NEW1']),
        ('high', ['NEW1'])
    ]
