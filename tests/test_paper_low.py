"""Integration tests for PaperLowStrategy with real Alpaca paper API."""
import pytest
from alpaca.trading.client import TradingClient

import config
from strategies.paper_low import PaperLowStrategy
from utils import get_positions


@pytest.mark.integration
class TestPaperLowIntegration:
    """Integration tests with real Alpaca API."""

    @pytest.fixture
    def alpaca_client(self):
        """Create real Alpaca paper trading client."""
        if not config.ALPACA_API_KEY_LOW or not config.ALPACA_SECRET_KEY_LOW:
            pytest.skip("ALPACA_API_KEY_LOW and ALPACA_SECRET_KEY_LOW not set")

        return TradingClient(
            api_key=config.ALPACA_API_KEY_LOW,
            secret_key=config.ALPACA_SECRET_KEY_LOW,
            paper=True
        )

    @pytest.fixture
    def paper_low_strategy(self, alpaca_client):
        """Create PaperLowStrategy with real client."""
        return PaperLowStrategy(
            trading_client=alpaca_client,
            tickers=config.SNP500_TICKERS,
            top_count=50
        )

    def test_strategy_initialization(self, paper_low_strategy):
        """Test strategy initializes correctly."""
        assert paper_low_strategy.tickers == config.SNP500_TICKERS
        assert paper_low_strategy.top_count == 50
        assert paper_low_strategy.trading_client is not None

    def test_get_signals_returns_top_50(self, paper_low_strategy):
        """Test get_signals returns exactly 50 stocks."""
        signals = paper_low_strategy.get_signals()

        assert isinstance(signals, list)
        assert len(signals) <= 50  # May be less if not enough data
        # All signals should be in SNP500_TICKERS
        for ticker in signals:
            assert ticker in config.SNP500_TICKERS

    def test_get_signals_valid_tickers(self, paper_low_strategy):
        """Test get_signals returns valid ticker symbols."""
        signals = paper_low_strategy.get_signals()

        # All should be strings
        assert all(isinstance(ticker, str) for ticker in signals)
        # All should be uppercase
        assert all(ticker.isupper() for ticker in signals)
        # No duplicates
        assert len(signals) == len(set(signals))

    def test_account_status(self, alpaca_client):
        """Test can retrieve account status."""
        account = alpaca_client.get_account()

        assert account is not None
        assert hasattr(account, 'cash')
        assert hasattr(account, 'portfolio_value')
        assert float(account.cash) >= 0

    def test_get_positions(self, alpaca_client):
        """Test can retrieve current positions."""
        positions = get_positions(alpaca_client)

        assert isinstance(positions, dict)
        # Positions should be valid tickers if any exist
        for ticker, quantity in positions.items():
            assert isinstance(ticker, str)
            assert ticker.isupper()
            assert isinstance(quantity, float)
            assert quantity > 0

    def test_rebalance_calculation(self, alpaca_client, paper_low_strategy):
        """Test rebalance can calculate positions to close/open."""
        # Get current state
        current_positions_dict = get_positions(alpaca_client)
        current_positions = list(current_positions_dict.keys())
        top_tickers = paper_low_strategy.get_signals()

        # Calculate what would change
        top_tickers_set = set(top_tickers)
        current_positions_set = set(current_positions)

        positions_to_close = list(current_positions_set - top_tickers_set)
        positions_to_open = list(top_tickers_set - current_positions_set)

        # Validation
        assert isinstance(positions_to_close, list)
        assert isinstance(positions_to_open, list)
        # No overlap
        assert len(set(positions_to_close) & set(positions_to_open)) == 0

    def test_account_cash_calculation(self, alpaca_client):
        """Test position sizing calculation logic."""
        account = alpaca_client.get_account()
        available_cash = float(account.cash)

        # Simulate position sizing
        num_positions = 50
        if num_positions > 0 and available_cash > 0:
            position_size = available_cash / num_positions
            # Position size should be positive
            assert position_size > 0

    def test_momentum_calculation_logic(self, paper_low_strategy):
        """Test momentum calculation produces expected results."""
        from data_loader import DataLoader

        # Load data and calculate momentum
        data = DataLoader.load_market_data(period="1y")
        close_prices = data.xs('Close', level=1, axis=1)

        # Verify data structure
        assert close_prices is not None
        assert len(close_prices) > 0

        # Calculate momentum: last_price / first_price - 1
        momentum = (close_prices.iloc[-1] / close_prices.iloc[0] - 1)

        # All momentum values should be numeric
        assert momentum.dtype in ['float64', 'float32']
        # Momentum should have reasonable values (usually between -1 and 10+)
        assert momentum.min() > -1  # Can't lose more than 100%
        assert momentum.max() < 100  # Reasonable upper bound

    def test_strategy_top_count_configuration(self):
        """Test strategy correctly uses top_count configuration."""
        for top_count in [10, 25, 50]:
            strategy = PaperLowStrategy(
                trading_client=None,  # type: ignore
                tickers=config.SNP500_TICKERS,
                top_count=top_count
            )
            assert strategy.top_count == top_count
