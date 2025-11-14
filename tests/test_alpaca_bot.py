"""Unit tests for TradingBot class."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, ANY
from core.alpaca_bot import TradingBot




class TestCalculateTotalCloseValue:
    """Tests for _calculate_total_close_value helper method."""

    def test_calculate_total_close_value_empty_list(self):
        """Test with empty positions to close."""
        positions_dict = {}
        result = TradingBot._calculate_total_close_value([], positions_dict)
        assert result == 0.0

    def test_calculate_total_close_value_single_position(self):
        """Test with single position to close."""
        pos = MagicMock()
        pos.market_value = 1000.0

        positions_dict = {'AAPL': pos}
        result = TradingBot._calculate_total_close_value(['AAPL'], positions_dict)
        assert result == 1000.0

    def test_calculate_total_close_value_multiple_positions(self):
        """Test with multiple positions to close."""
        pos1 = MagicMock()
        pos1.market_value = 1000.0
        pos2 = MagicMock()
        pos2.market_value = 2000.0
        pos3 = MagicMock()
        pos3.market_value = 1500.0

        positions_dict = {
            'AAPL': pos1,
            'MSFT': pos2,
            'GOOGL': pos3
        }
        result = TradingBot._calculate_total_close_value(
            ['AAPL', 'MSFT', 'GOOGL'],
            positions_dict
        )
        assert result == 4500.0

    def test_calculate_total_close_value_missing_market_value(self):
        """Test with position missing market_value attribute."""
        pos1 = MagicMock(spec=[])  # No attributes
        pos2 = MagicMock()
        pos2.market_value = 2000.0

        positions_dict = {
            'AAPL': pos1,
            'MSFT': pos2
        }
        result = TradingBot._calculate_total_close_value(
            ['AAPL', 'MSFT'],
            positions_dict
        )
        # AAPL has no market_value, should return 0; MSFT is 2000
        assert result == 2000.0

    def test_calculate_total_close_value_nonexistent_position(self):
        """Test with position symbol not in dict."""
        pos1 = MagicMock()
        pos1.market_value = 1000.0

        positions_dict = {'AAPL': pos1}
        result = TradingBot._calculate_total_close_value(
            ['AAPL', 'MSFT'],  # MSFT doesn't exist
            positions_dict
        )
        # Only AAPL is 1000
        assert result == 1000.0


