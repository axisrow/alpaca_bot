import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from utils import retry_on_exception, get_positions, telegram_handler


class TestRetryDecorator:
    """Test retry_on_exception decorator"""

    def test_retry_success_first_attempt(self):
        """Should succeed on first attempt"""
        @retry_on_exception()
        def successful_func():
            return "success"

        result = successful_func()
        assert result == "success"

    def test_retry_success_after_failures(self):
        """Should succeed after retries"""
        attempt = {"count": 0}

        @retry_on_exception(retries=3, delay=0)
        def flaky_func():
            attempt["count"] += 1
            if attempt["count"] < 3:
                raise ValueError("Attempt failed")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert attempt["count"] == 3

    def test_retry_all_attempts_fail(self):
        """Should raise exception after all retries exhausted"""
        @retry_on_exception(retries=2, delay=0)
        def always_fails():
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            always_fails()

    def test_retry_custom_attempts(self):
        """Should respect custom retry count"""
        attempt = {"count": 0}

        @retry_on_exception(retries=2, delay=0)
        def flaky_func():
            attempt["count"] += 1
            raise ValueError("Failed")

        with pytest.raises(ValueError):
            flaky_func()

        assert attempt["count"] == 2

    def test_retry_logs_warning_on_retry(self):
        """Should log warning when retrying"""
        attempt = {"count": 0}

        @retry_on_exception(retries=3, delay=0)
        def flaky_func():
            attempt["count"] += 1
            if attempt["count"] < 2:
                raise ValueError("Retry me")
            return "success"

        with patch("logging.warning") as mock_warning:
            result = flaky_func()
            assert result == "success"
            mock_warning.assert_called()


class TestGetPositions:
    """Test get_positions function"""

    def test_get_positions_empty(self, mock_trading_client):
        """Should return empty dict when no positions"""
        mock_trading_client.get_all_positions.return_value = []
        result = get_positions(mock_trading_client)
        assert result == {}

    def test_get_positions_with_data(self, mock_trading_client):
        """Should return positions dict with symbol and quantity"""
        position = MagicMock()
        position.symbol = "AAPL"
        position.qty = 10.5
        mock_trading_client.get_all_positions.return_value = [position]

        result = get_positions(mock_trading_client)
        assert result == {"AAPL": 10.5}

    def test_get_positions_multiple(self, mock_trading_client):
        """Should return multiple positions"""
        position1 = MagicMock()
        position1.symbol = "AAPL"
        position1.qty = 10.0

        position2 = MagicMock()
        position2.symbol = "GOOGL"
        position2.qty = 5.0

        mock_trading_client.get_all_positions.return_value = [position1, position2]
        result = get_positions(mock_trading_client)
        assert result == {"AAPL": 10.0, "GOOGL": 5.0}

    def test_get_positions_api_exception(self, mock_trading_client):
        """Should propagate API exception"""
        mock_trading_client.get_all_positions.side_effect = Exception("API Error")

        with pytest.raises(Exception, match="API Error"):
            get_positions(mock_trading_client)


class TestTelegramHandler:
    """Test telegram_handler decorator"""

    @pytest.mark.asyncio
    async def test_telegram_handler_success(self):
        """Should handle successful execution"""
        @telegram_handler()
        async def test_handler(message):
            return "success"

        message = MagicMock()
        result = await test_handler(message)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_telegram_handler_error(self):
        """Should handle exceptions and send error message"""
        @telegram_handler("Custom error")
        async def failing_handler(message):
            raise ValueError("Test error")

        message = AsyncMock()
        await failing_handler(message)
        message.answer.assert_called_with("Custom error")
