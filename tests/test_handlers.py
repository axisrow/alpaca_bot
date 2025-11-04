import pytest
from unittest.mock import MagicMock, AsyncMock
from handlers import setup_router, telegram_handler


@pytest.fixture
def mock_trading_bot():
    """Create mock trading bot"""
    bot = MagicMock()
    bot.get_portfolio_status.return_value = ({"AAPL": 10}, MagicMock(), 100.0)
    bot.get_trading_stats.return_value = {"trades_today": 5, "pnl": 1000.0, "win_rate": 0.6}
    bot.get_settings.return_value = {"rebalance_time": "10:00 NY", "positions_count": 10, "mode": "Paper Trading"}
    bot.calculate_days_until_rebalance.return_value = 5
    bot.get_next_rebalance_date.return_value = MagicMock()
    bot.rebalance_flag.get_countdown_message.return_value = "Countdown message"
    return bot


class TestSetupRouter:
    """Test setup_router and handlers"""

    def test_setup_router_creates_router(self, mock_trading_bot):
        """Should create router"""
        router = setup_router(mock_trading_bot)
        assert router is not None

    def test_setup_router_with_mock_bot(self, mock_trading_bot):
        """Should create router with trading bot"""
        router = setup_router(mock_trading_bot)
        assert router is not None
        # Verify that bot methods are accessible
        assert mock_trading_bot.get_portfolio_status is not None


class TestTelegramHandlerDecorator:
    """Test telegram_handler decorator"""

    @pytest.mark.asyncio
    async def test_decorator_with_success(self):
        """Should handle successful handler execution"""
        @telegram_handler()
        async def test_handler(message):
            return "success"

        message = AsyncMock()
        result = await test_handler(message)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_decorator_with_error(self):
        """Should handle exceptions in handler"""
        @telegram_handler("Custom error")
        async def failing_handler(message):
            raise ValueError("Test error")

        message = AsyncMock()
        message.answer = AsyncMock()

        await failing_handler(message)
        message.answer.assert_called_with("Custom error")

    @pytest.mark.asyncio
    async def test_decorator_default_error_message(self):
        """Should use default error message"""
        @telegram_handler()
        async def failing_handler(message):
            raise RuntimeError("Something went wrong")

        message = AsyncMock()
        message.answer = AsyncMock()

        await failing_handler(message)
        message.answer.assert_called()
