"""Unit tests for TelegramBot class."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from core.telegram_bot import TelegramBot


class TestTelegramBotInitialization:
    """Tests for TelegramBot initialization."""

    @patch('core.telegram_bot.TELEGRAM_BOT_TOKEN', None)
    def test_telegram_bot_initialization_without_token(self):
        """Test that TelegramBot fails without TELEGRAM_BOT_TOKEN."""
        mock_trading_bot = MagicMock()

        with pytest.raises(AssertionError):
            TelegramBot(mock_trading_bot)


