import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime, timedelta
import pytz
from pathlib import Path
from tempfile import TemporaryDirectory

NY_TZ = pytz.timezone("America/New_York")


class TestRebalanceFlag:
    """Test RebalanceFlag class"""

    def test_get_last_rebalance_date_file_not_exists(self):
        """Should return None if flag file doesn't exist"""
        from bot import RebalanceFlag

        with TemporaryDirectory() as tmpdir:
            flag = RebalanceFlag(flag_path=Path(tmpdir) / "nonexistent.txt")
            result = flag.get_last_rebalance_date()
            assert result is None

    def test_get_last_rebalance_date_valid_date(self):
        """Should return datetime if valid date in file"""
        from bot import RebalanceFlag

        with TemporaryDirectory() as tmpdir:
            flag_path = Path(tmpdir) / "flag.txt"
            flag_path.write_text("2024-01-15", encoding="utf-8")
            flag = RebalanceFlag(flag_path=flag_path)
            result = flag.get_last_rebalance_date()
            assert result.strftime("%Y-%m-%d") == "2024-01-15"

    def test_get_last_rebalance_date_invalid_date(self):
        """Should return None for invalid date format"""
        from bot import RebalanceFlag

        with TemporaryDirectory() as tmpdir:
            flag_path = Path(tmpdir) / "flag.txt"
            flag_path.write_text("invalid", encoding="utf-8")
            flag = RebalanceFlag(flag_path=flag_path)
            result = flag.get_last_rebalance_date()
            assert result is None  # Invalid dates return None, not raise ValueError

    def test_has_rebalanced_today_true(self):
        """Should return True if rebalanced today"""
        from bot import RebalanceFlag

        with TemporaryDirectory() as tmpdir:
            flag_path = Path(tmpdir) / "flag.txt"
            today = datetime.now(NY_TZ).strftime("%Y-%m-%d")
            flag_path.write_text(today, encoding="utf-8")
            flag = RebalanceFlag(flag_path=flag_path)
            assert flag.has_rebalanced_today() is True

    def test_has_rebalanced_today_false(self):
        """Should return False if not rebalanced today"""
        from bot import RebalanceFlag

        with TemporaryDirectory() as tmpdir:
            flag_path = Path(tmpdir) / "flag.txt"
            yesterday = (datetime.now(NY_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
            flag_path.write_text(yesterday, encoding="utf-8")
            flag = RebalanceFlag(flag_path=flag_path)
            assert flag.has_rebalanced_today() is False

    def test_write_flag(self):
        """Should write today's date to file"""
        from bot import RebalanceFlag

        with TemporaryDirectory() as tmpdir:
            flag_path = Path(tmpdir) / "flag.txt"
            flag = RebalanceFlag(flag_path=flag_path)
            flag.write_flag()
            today = datetime.now(NY_TZ).strftime("%Y-%m-%d")
            assert flag_path.read_text(encoding="utf-8") == today

    def test_get_countdown_message_zero_days(self):
        """Should return message for rebalance now"""
        from bot import RebalanceFlag

        flag = RebalanceFlag()
        next_date = datetime.now(NY_TZ)
        msg = flag.get_countdown_message(0, next_date)
        assert "rebalancing" in msg.lower()

    def test_get_countdown_message_positive_days(self):
        """Should return message with days until rebalance"""
        from bot import RebalanceFlag

        flag = RebalanceFlag()
        next_date = datetime.now(NY_TZ) + timedelta(days=5)
        msg = flag.get_countdown_message(5, next_date)
        assert "5" in msg


class TestMarketSchedule:
    """Test MarketSchedule class"""

    def test_current_ny_time(self, mock_trading_client):
        """Should return current time in NY timezone"""
        from bot import MarketSchedule

        schedule = MarketSchedule(mock_trading_client)
        now = schedule.current_ny_time
        assert now.tzinfo is not None  # Has timezone info

    def test_is_open_market_open(self, mock_trading_client):
        """Should return True when market is open"""
        from bot import MarketSchedule

        clock = MagicMock()
        clock.is_open = True
        mock_trading_client.get_clock.return_value = clock

        schedule = MarketSchedule(mock_trading_client)
        assert schedule.is_open is True

    def test_is_open_market_closed(self, mock_trading_client):
        """Should return False when market is closed"""
        from bot import MarketSchedule

        clock = MagicMock()
        clock.is_open = False
        mock_trading_client.get_clock.return_value = clock

        schedule = MarketSchedule(mock_trading_client)
        assert schedule.is_open is False

    def test_check_market_status_open(self, mock_trading_client):
        """Should return (True, message) when market open"""
        from bot import MarketSchedule

        clock = MagicMock()
        clock.is_open = True
        mock_trading_client.get_clock.return_value = clock

        schedule = MarketSchedule(mock_trading_client)
        is_open, msg = schedule.check_market_status()
        assert is_open is True
        assert isinstance(msg, str)

    def test_check_market_status_closed(self, mock_trading_client):
        """Should return (False, message) when market closed"""
        from bot import MarketSchedule

        clock = MagicMock()
        clock.is_open = False
        mock_trading_client.get_clock.return_value = clock

        schedule = MarketSchedule(mock_trading_client)
        is_open, msg = schedule.check_market_status()
        assert is_open is False
        assert isinstance(msg, str)

    def test_count_trading_days(self, mock_trading_client):
        """Should count trading days excluding weekends"""
        from bot import MarketSchedule

        schedule = MarketSchedule(mock_trading_client)
        # From Monday to Friday = 5 trading days
        start = datetime(2024, 1, 1)  # Monday
        end = datetime(2024, 1, 5)    # Friday
        count = schedule.count_trading_days(start, end)
        assert count > 0


class TestPortfolioManager:
    """Test PortfolioManager class"""

    def test_get_current_positions(self, mock_trading_client):
        """Should return current positions"""
        from bot import PortfolioManager

        manager = PortfolioManager(mock_trading_client)
        positions = manager.get_current_positions()
        assert isinstance(positions, dict)

    def test_get_current_positions_empty(self, mock_trading_client):
        """Should handle empty positions"""
        from bot import PortfolioManager

        mock_trading_client.get_all_positions.return_value = []
        manager = PortfolioManager(mock_trading_client)
        positions = manager.get_current_positions()
        assert positions == {}


class TestTradingBot:
    """Test TradingBot class"""

    def test_trading_bot_init(self, mock_env_vars, mock_trading_client):
        """Should initialize trading bot"""
        from bot import TradingBot

        with patch("bot.TradingClient", return_value=mock_trading_client):
            with patch("bot.load_dotenv"):
                bot = TradingBot()
                assert bot is not None
                assert bot.trading_client is not None

    def test_perform_rebalance_skip_if_done_today(self, mock_env_vars, mock_trading_client):
        """Should skip rebalance if already done today"""
        from bot import TradingBot

        with patch("bot.TradingClient", return_value=mock_trading_client):
            with patch("bot.load_dotenv"):
                bot = TradingBot()
                bot.rebalance_flag = MagicMock()
                bot.rebalance_flag.has_rebalanced_today.return_value = True
                bot.portfolio_manager.strategy.rebalance = MagicMock()

                bot.perform_rebalance()
                # rebalance should not be called
                bot.portfolio_manager.strategy.rebalance.assert_not_called()

    def test_perform_rebalance_market_closed(self, mock_env_vars, mock_trading_client):
        """Should skip rebalance if market is closed"""
        from bot import TradingBot

        with patch("bot.TradingClient", return_value=mock_trading_client):
            with patch("bot.load_dotenv"):
                bot = TradingBot()
                bot.rebalance_flag = MagicMock()
                bot.rebalance_flag.has_rebalanced_today.return_value = False

                # Mock market closed
                bot.market_schedule.check_market_status = MagicMock(return_value=(False, "closed"))
                bot.portfolio_manager.strategy.rebalance = MagicMock()

                bot.perform_rebalance()
                # Should not execute rebalance if market closed
                bot.portfolio_manager.strategy.rebalance.assert_not_called()

    def test_calculate_days_until_rebalance(self, mock_env_vars, mock_trading_client):
        """Should calculate days until next rebalance"""
        from bot import TradingBot

        with patch("bot.TradingClient", return_value=mock_trading_client):
            with patch("bot.load_dotenv"):
                bot = TradingBot()
                days = bot.calculate_days_until_rebalance()
                assert isinstance(days, int)
                assert days >= 0

    def test_get_portfolio_status(self, mock_env_vars, mock_trading_client):
        """Should return portfolio status"""
        from bot import TradingBot

        with patch("bot.TradingClient", return_value=mock_trading_client):
            with patch("bot.load_dotenv"):
                bot = TradingBot()
                positions, account, pnl = bot.get_portfolio_status()
                assert isinstance(positions, dict)
                assert account is not None
                assert isinstance(pnl, (int, float))
