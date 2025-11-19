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
