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


    @patch('core.telegram_bot.TELEGRAM_BOT_TOKEN', '123456789:AABBCCDDEEFFaabbccddeeff')
    @patch('asyncio.get_running_loop')
    def test_telegram_bot_session_timeout(self, mock_get_loop):
        """Test that TelegramBot initializes session with correct timeout."""
        mock_loop = MagicMock()
        mock_get_loop.return_value = mock_loop
        
        mock_trading_bot = MagicMock()
        
        # Initialize bot
        bot = TelegramBot(mock_trading_bot)
        
        # Check session timeout
        assert bot.bot.session.timeout == 120, \
            f"Session timeout should be 120, but got {bot.bot.session.timeout}"
