"""Unit tests for Telegram bot helper functions."""

from unittest.mock import MagicMock, patch

import pytest

from core.telegram_bot import create_telegram_bot_state


class TestCreateTelegramBotState:
    """Tests for create_telegram_bot_state factory."""

    def test_initialization_without_token(self):
        """Ensure TELEGRAM_BOT_TOKEN is required."""
        with patch('core.telegram_bot.TELEGRAM_BOT_TOKEN', None):
            with pytest.raises(AssertionError):
                create_telegram_bot_state(MagicMock())

    def test_state_contains_expected_objects(self):
        """Ensure bot state wiring uses injected dependencies."""
        mock_bot = MagicMock(name='Bot')
        mock_dp = MagicMock(name='Dispatcher')
        mock_session = MagicMock(name='AiohttpSession')
        mock_router = MagicMock(name='Router')

        trading_bot_state = {'foo': 'bar'}

        with (
            patch('core.telegram_bot.TELEGRAM_BOT_TOKEN', 'token'),
            patch('core.telegram_bot.AiohttpSession', return_value=mock_session) as session_cls,
            patch('core.telegram_bot.Bot', return_value=mock_bot) as bot_cls,
            patch('core.telegram_bot.Dispatcher', return_value=mock_dp) as dispatcher_cls,
            patch('handlers.setup_router', return_value=mock_router) as setup_router,
        ):
            state = create_telegram_bot_state(trading_bot_state)

        session_cls.assert_called_once_with(timeout=60)
        bot_cls.assert_called_once_with(token='token', session=mock_session)
        dispatcher_cls.assert_called_once_with()
        setup_router.assert_called_once_with(trading_bot_state)

        assert state['bot'] is mock_bot
        assert state['dp'] is mock_dp
        assert state['router'] is mock_router
        assert state['trading_bot_state'] == trading_bot_state

