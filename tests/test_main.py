"""Тесты для модуля main."""
from datetime import datetime, time as dt_time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
import pytz

from main import (
    RebalanceFlag,
    MarketSchedule,
    PortfolioManager,
    TradingBot
)


class TestRebalanceFlag:
    """Тесты для класса RebalanceFlag."""

    def test_has_rebalanced_today_no_file(self, tmp_path):
        """Тест когда файл флага не существует."""
        flag = RebalanceFlag(flag_path=tmp_path / "test_flag.txt")
        assert flag.has_rebalanced_today() is False

    def test_has_rebalanced_today_true(self, tmp_path):
        """Тест когда ребалансировка была сегодня."""
        flag_path = tmp_path / "test_flag.txt"
        flag_path.write_text(datetime.now().strftime("%Y-%m-%d"))

        flag = RebalanceFlag(flag_path=flag_path)
        assert flag.has_rebalanced_today() is True

    def test_has_rebalanced_today_false(self, tmp_path):
        """Тест когда ребалансировка была вчера."""
        flag_path = tmp_path / "test_flag.txt"
        flag_path.write_text("2020-01-01")

        flag = RebalanceFlag(flag_path=flag_path)
        assert flag.has_rebalanced_today() is False

    def test_write_flag(self, tmp_path):
        """Тест записи флага."""
        flag_path = tmp_path / "subdir" / "test_flag.txt"
        flag = RebalanceFlag(flag_path=flag_path)

        flag.write_flag()

        assert flag_path.exists()
        assert flag_path.read_text() == datetime.now().strftime("%Y-%m-%d")


class TestMarketSchedule:
    """Тесты для класса MarketSchedule."""

    def test_current_ny_time(self, mock_trading_client):
        """Тест получения текущего времени в Нью-Йорке."""
        schedule = MarketSchedule(mock_trading_client)
        ny_time = schedule.current_ny_time

        assert ny_time.tzinfo is not None
        # Проверяем, что это NY timezone
        assert str(ny_time.tzinfo) in ['EST', 'EDT', 'America/New_York']

    def test_check_market_status_open(self, mock_trading_client):
        """Тест когда рынок открыт."""
        mock_clock = Mock()
        mock_clock.is_open = True
        mock_trading_client.get_clock.return_value = mock_clock

        schedule = MarketSchedule(mock_trading_client)

        with patch.object(MarketSchedule, 'current_ny_time', new_callable=lambda: property(lambda self: datetime(2024, 1, 15, 10, 0, tzinfo=pytz.timezone('America/New_York')))):
            is_open, reason = schedule.check_market_status()

            assert is_open is True
            assert reason == "рынок открыт"

    def test_check_market_status_weekend(self, mock_trading_client):
        """Тест когда выходной день."""
        schedule = MarketSchedule(mock_trading_client)

        with patch.object(MarketSchedule, 'current_ny_time', new_callable=lambda: property(lambda self: datetime(2024, 1, 20, 10, 0, tzinfo=pytz.timezone('America/New_York')))):
            is_open, reason = schedule.check_market_status()

            assert is_open is False
            assert "выходной день" in reason

    def test_check_market_status_holiday(self, mock_trading_client):
        """Тест когда праздничный день."""
        mock_clock = Mock()
        mock_clock.is_open = False
        mock_trading_client.get_clock.return_value = mock_clock

        schedule = MarketSchedule(mock_trading_client)

        with patch.object(MarketSchedule, 'current_ny_time', new_callable=lambda: property(lambda self: datetime(2024, 1, 15, 10, 0, tzinfo=pytz.timezone('America/New_York')))):
            is_open, reason = schedule.check_market_status()

            assert is_open is False
            assert reason == "праздничный день"

    def test_is_open_property(self, mock_trading_client):
        """Тест свойства is_open."""
        mock_clock = Mock()
        mock_clock.is_open = True
        mock_trading_client.get_clock.return_value = mock_clock

        schedule = MarketSchedule(mock_trading_client)

        with patch.object(MarketSchedule, 'current_ny_time', new_callable=lambda: property(lambda self: datetime(2024, 1, 15, 10, 0, tzinfo=pytz.timezone('America/New_York')))):
            assert schedule.is_open is True


class TestPortfolioManager:
    """Тесты для класса PortfolioManager."""

    def test_init(self, mock_trading_client):
        """Тест инициализации менеджера портфеля."""
        manager = PortfolioManager(mock_trading_client)

        assert manager.trading_client == mock_trading_client
        assert manager.strategy is not None

    def test_get_current_positions(self, mock_trading_client):
        """Тест получения текущих позиций."""
        pos1 = Mock()
        pos1.symbol = "AAPL"
        pos1.qty = "10.0"

        pos2 = Mock()
        pos2.symbol = "GOOGL"
        pos2.qty = "5.0"

        mock_trading_client.get_all_positions.return_value = [pos1, pos2]

        manager = PortfolioManager(mock_trading_client)
        positions = manager.get_current_positions()

        assert positions == {"AAPL": 10.0, "GOOGL": 5.0}

    def test_close_positions(self, mock_trading_client):
        """Тест закрытия позиций."""
        manager = PortfolioManager(mock_trading_client)

        positions = ["AAPL", "GOOGL"]
        manager.close_positions(positions)

        assert mock_trading_client.close_position.call_count == 2

    def test_open_positions(self, mock_trading_client):
        """Тест открытия позиций."""
        manager = PortfolioManager(mock_trading_client)

        tickers = ["AAPL", "GOOGL"]
        manager.open_positions(tickers, 1000.0)

        assert mock_trading_client.submit_order.call_count == 2


class TestTradingBot:
    """Тесты для класса TradingBot."""

    @patch.dict('os.environ', {'ALPACA_API_KEY': 'test_key', 'ALPACA_SECRET_KEY': 'test_secret'})
    @patch('main.load_dotenv')
    @patch('main.TradingClient')
    def test_init(self, mock_client_class, mock_load_dotenv):
        """Тест инициализации торгового бота."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        bot = TradingBot()

        assert bot.api_key == 'test_key'
        assert bot.secret_key == 'test_secret'
        assert bot.trading_client == mock_client
        mock_load_dotenv.assert_called_once()

    @patch.dict('os.environ', {}, clear=True)
    @patch('main.load_dotenv')
    def test_init_no_api_keys(self, mock_load_dotenv):
        """Тест инициализации без API ключей."""
        with pytest.raises(SystemExit):
            TradingBot()

    @patch.dict('os.environ', {'ALPACA_API_KEY': 'test_key', 'ALPACA_SECRET_KEY': 'test_secret'})
    @patch('main.load_dotenv')
    @patch('main.TradingClient')
    def test_perform_rebalance_already_done(self, mock_client_class, mock_load_dotenv, tmp_path):
        """Тест ребалансировки когда уже была сегодня."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        bot = TradingBot()

        # Устанавливаем флаг на сегодня
        flag_path = tmp_path / "test_flag.txt"
        flag_path.write_text(datetime.now().strftime("%Y-%m-%d"))
        bot.rebalance_flag = RebalanceFlag(flag_path=flag_path)

        # Мокируем метод ребалансировки стратегии
        with patch.object(bot.portfolio_manager.strategy, 'rebalance') as mock_rebalance:
            bot.perform_rebalance()

            # Проверяем, что стратегия не вызывалась
            mock_rebalance.assert_not_called()

    @patch.dict('os.environ', {'ALPACA_API_KEY': 'test_key', 'ALPACA_SECRET_KEY': 'test_secret'})
    @patch('main.load_dotenv')
    @patch('main.TradingClient')
    def test_get_portfolio_status(self, mock_client_class, mock_load_dotenv, mock_position):
        """Тест получения статуса портфеля."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Настраиваем моки
        mock_client.get_all_positions.return_value = [mock_position]

        mock_account = Mock()
        mock_account.portfolio_value = "15000.00"
        mock_client.get_account.return_value = mock_account

        bot = TradingBot()
        positions, account, pnl = bot.get_portfolio_status()

        assert isinstance(positions, dict)
        assert account == mock_account
        assert isinstance(pnl, float)

    @patch.dict('os.environ', {'ALPACA_API_KEY': 'test_key', 'ALPACA_SECRET_KEY': 'test_secret'})
    @patch('main.load_dotenv')
    @patch('main.TradingClient')
    def test_get_trading_stats(self, mock_client_class, mock_load_dotenv):
        """Тест получения торговой статистики."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Настраиваем моки
        mock_client.get_orders.return_value = []
        mock_client.get_all_positions.return_value = []

        bot = TradingBot()
        stats = bot.get_trading_stats()

        assert isinstance(stats, dict)
        assert "trades_today" in stats
        assert "pnl" in stats
        assert "win_rate" in stats

    @patch.dict('os.environ', {'ALPACA_API_KEY': 'test_key', 'ALPACA_SECRET_KEY': 'test_secret'})
    @patch('main.load_dotenv')
    @patch('main.TradingClient')
    def test_get_settings(self, mock_client_class, mock_load_dotenv):
        """Тест получения настроек бота."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        bot = TradingBot()
        settings = bot.get_settings()

        assert isinstance(settings, dict)
        assert "rebalance_time" in settings
        assert "positions_count" in settings
        assert "mode" in settings
        assert settings["positions_count"] == 10


class TestTelegramBot:
    """Тесты для класса TelegramBot."""

    @patch.dict('os.environ', {'ALPACA_API_KEY': 'test_key', 'ALPACA_SECRET_KEY': 'test_secret'})
    @patch('main.load_dotenv')
    @patch('main.TradingClient')
    @patch('main.ADMIN_IDS', [123456, 789012])
    def test_send_startup_message(self, mock_client_class, mock_load_dotenv):
        """Тест отправки стартового сообщения."""
        import asyncio
        from main import TelegramBot

        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Создаем моки
        trading_bot = MagicMock()
        trading_bot.market_schedule.check_market_status.return_value = (True, "рынок открыт")
        trading_bot.get_settings.return_value = {
            "mode": "Paper Trading",
            "rebalance_time": "10:00 NY",
            "positions_count": 10
        }

        telegram_bot = TelegramBot(trading_bot)

        # Мокируем отправку сообщения
        async def mock_send():
            await telegram_bot.send_startup_message()

        with patch.object(telegram_bot.bot, 'send_message', new_callable=AsyncMock) as mock_send_message:
            asyncio.run(mock_send())

            # Проверяем, что сообщение было отправлено обоим администраторам
            assert mock_send_message.call_count == 2

            # Проверяем параметры первого вызова
            first_call = mock_send_message.call_args_list[0]
            assert first_call.kwargs['chat_id'] == 123456
            assert 'Бот запущен' in first_call.kwargs['text']
            assert first_call.kwargs['parse_mode'] == 'HTML'

    @patch.dict('os.environ', {'ALPACA_API_KEY': 'test_key', 'ALPACA_SECRET_KEY': 'test_secret'})
    @patch('main.load_dotenv')
    @patch('main.TradingClient')
    @patch('main.ADMIN_IDS', [])
    def test_send_startup_message_no_admins(self, mock_client_class, mock_load_dotenv):
        """Тест отправки стартового сообщения когда нет администраторов."""
        import asyncio
        from main import TelegramBot

        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        trading_bot = MagicMock()
        telegram_bot = TelegramBot(trading_bot)

        async def mock_send():
            await telegram_bot.send_startup_message()

        with patch.object(telegram_bot.bot, 'send_message', new_callable=AsyncMock) as mock_send_message:
            asyncio.run(mock_send())

            # Проверяем, что сообщение не было отправлено
            mock_send_message.assert_not_called()


# Вспомогательный класс для асинхронных моков
class AsyncMock(MagicMock):
    """Мок для асинхронных функций."""
    async def __call__(self, *args, **kwargs):
        return super().__call__(*args, **kwargs)
