"""
Unit тесты для InvestorManager - методы расчета позиций и P&L.
"""
import csv
import pytest
from datetime import datetime
from pathlib import Path

from core.investor_manager import InvestorManager
import pytz

NY_TIMEZONE = pytz.timezone('America/New_York')


@pytest.fixture
def investor_manager_with_trades(tmp_path, monkeypatch):
    """Создать InvestorManager с тестовыми данными trades.csv."""
    monkeypatch.chdir(tmp_path)

    # Создать реестр
    registry_path = tmp_path / "investors_registry.csv"
    with open(registry_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'name', 'creation_date', 'fee_percent', 'is_fee_receiver',
            'high_watermark', 'last_fee_date', 'status'
        ])
        writer.writeheader()
        writer.writerow({
            'name': 'TestInvestor',
            'creation_date': '2025-01-01',
            'fee_percent': '0.0',
            'is_fee_receiver': 'False',
            'high_watermark': '0.0',
            'last_fee_date': '2025-01-01',
            'status': 'active'
        })

    manager = InvestorManager(str(registry_path))
    manager.investors_dir = tmp_path / "data" / "investors"
    manager.investors_dir.mkdir(parents=True, exist_ok=True)
    investor_dir = manager.investors_dir / "TestInvestor"
    investor_dir.mkdir(parents=True, exist_ok=True)

    return manager


class TestPositionsCalculation:
    """Тесты для расчета positions_value из trades.csv."""

    def test_get_investor_positions_empty(self, investor_manager_with_trades):
        """Тест: Получить позиции для инвестора без сделок (должно быть пусто)."""
        positions = investor_manager_with_trades._get_investor_positions('TestInvestor', 'low')
        assert positions == {}

    def test_get_investor_positions_single_buy(self, investor_manager_with_trades):
        """
        Тест: Получить позиции после одной покупки.

        Сценарий:
        - BUY 100 shares AAPL @ $150
        - Ожидаемо: {AAPL: 100}
        """
        # ARRANGE - Создать trades.csv с одной покупкой
        trades_file = investor_manager_with_trades.investors_dir / "TestInvestor" / "trades.csv"
        with open(trades_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'date', 'timestamp', 'account', 'action', 'ticker',
                'shares', 'price', 'amount', 'total_shares_after', 'notes'
            ])
            writer.writeheader()
            writer.writerow({
                'date': '2025-01-15',
                'timestamp': '10:00:00',
                'account': 'low',
                'action': 'BUY',
                'ticker': 'AAPL',
                'shares': '100.0',
                'price': '150.00',
                'amount': '15000.00',
                'total_shares_after': '100.0',
                'notes': 'Test buy'
            })

        # ACT
        positions = investor_manager_with_trades._get_investor_positions('TestInvestor', 'low')

        # ASSERT
        assert positions == {'AAPL': 100.0}

    def test_get_investor_positions_buy_and_sell(self, investor_manager_with_trades):
        """
        Тест: Получить позиции после покупки и частичной продажи.

        Сценарий:
        - BUY 100 shares AAPL @ $150
        - SELL 30 shares AAPL @ $160
        - Ожидаемо: {AAPL: 70}
        """
        # ARRANGE
        trades_file = investor_manager_with_trades.investors_dir / "TestInvestor" / "trades.csv"
        with open(trades_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'date', 'timestamp', 'account', 'action', 'ticker',
                'shares', 'price', 'amount', 'total_shares_after', 'notes'
            ])
            writer.writeheader()
            writer.writerows([
                {
                    'date': '2025-01-15',
                    'timestamp': '10:00:00',
                    'account': 'low',
                    'action': 'BUY',
                    'ticker': 'AAPL',
                    'shares': '100.0',
                    'price': '150.00',
                    'amount': '15000.00',
                    'total_shares_after': '100.0',
                    'notes': 'Buy'
                },
                {
                    'date': '2025-01-20',
                    'timestamp': '14:00:00',
                    'account': 'low',
                    'action': 'SELL',
                    'ticker': 'AAPL',
                    'shares': '30.0',
                    'price': '160.00',
                    'amount': '4800.00',
                    'total_shares_after': '70.0',
                    'notes': 'Sell'
                }
            ])

        # ACT
        positions = investor_manager_with_trades._get_investor_positions('TestInvestor', 'low')

        # ASSERT
        assert positions == {'AAPL': 70.0}

    def test_get_investor_positions_multiple_tickers(self, investor_manager_with_trades):
        """
        Тест: Получить позиции с несколькими тикерами.

        Сценарий:
        - BUY 100 AAPL @ $150
        - BUY 50 MSFT @ $300
        - SELL 20 AAPL @ $160
        - Ожидаемо: {AAPL: 80, MSFT: 50}
        """
        # ARRANGE
        trades_file = investor_manager_with_trades.investors_dir / "TestInvestor" / "trades.csv"
        with open(trades_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'date', 'timestamp', 'account', 'action', 'ticker',
                'shares', 'price', 'amount', 'total_shares_after', 'notes'
            ])
            writer.writeheader()
            writer.writerows([
                {
                    'date': '2025-01-15',
                    'timestamp': '10:00:00',
                    'account': 'low',
                    'action': 'BUY',
                    'ticker': 'AAPL',
                    'shares': '100.0',
                    'price': '150.00',
                    'amount': '15000.00',
                    'total_shares_after': '100.0',
                    'notes': 'Buy AAPL'
                },
                {
                    'date': '2025-01-16',
                    'timestamp': '11:00:00',
                    'account': 'low',
                    'action': 'BUY',
                    'ticker': 'MSFT',
                    'shares': '50.0',
                    'price': '300.00',
                    'amount': '15000.00',
                    'total_shares_after': '50.0',
                    'notes': 'Buy MSFT'
                },
                {
                    'date': '2025-01-20',
                    'timestamp': '14:00:00',
                    'account': 'low',
                    'action': 'SELL',
                    'ticker': 'AAPL',
                    'shares': '20.0',
                    'price': '160.00',
                    'amount': '3200.00',
                    'total_shares_after': '80.0',
                    'notes': 'Sell AAPL'
                }
            ])

        # ACT
        positions = investor_manager_with_trades._get_investor_positions('TestInvestor', 'low')

        # ASSERT
        assert positions == {'AAPL': 80.0, 'MSFT': 50.0}


class TestPnLCalculation:
    """Тесты для расчета P&L."""

    def test_pnl_no_trades(self, investor_manager_with_trades):
        """Тест: P&L без сделок должен быть 0."""
        positions_value, realized_pnl, unrealized_pnl = \
            investor_manager_with_trades._calculate_positions_value_and_pnl(
                'TestInvestor', 'low'
            )

        assert positions_value == 0.0
        assert realized_pnl == 0.0
        assert unrealized_pnl == 0.0

    def test_unrealized_pnl_price_increase(self, investor_manager_with_trades):
        """
        Тест: Unrealized P&L при росте цены.

        Сценарий:
        - BUY 100 AAPL @ $150 = $15,000
        - Текущая цена: $160
        - Ожидаемо: positions_value = $16,000, unrealized_pnl = $1,000
        """
        # ARRANGE
        trades_file = investor_manager_with_trades.investors_dir / "TestInvestor" / "trades.csv"
        with open(trades_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'date', 'timestamp', 'account', 'action', 'ticker',
                'shares', 'price', 'amount', 'total_shares_after', 'notes'
            ])
            writer.writeheader()
            writer.writerow({
                'date': '2025-01-15',
                'timestamp': '10:00:00',
                'account': 'low',
                'action': 'BUY',
                'ticker': 'AAPL',
                'shares': '100.0',
                'price': '150.00',
                'amount': '15000.00',
                'total_shares_after': '100.0',
                'notes': 'Buy'
            })

        # ACT
        current_prices = {'AAPL': 160.0}
        positions_value, realized_pnl, unrealized_pnl = \
            investor_manager_with_trades._calculate_positions_value_and_pnl(
                'TestInvestor', 'low', current_prices
            )

        # ASSERT
        assert positions_value == pytest.approx(16000.0, abs=0.01)
        assert realized_pnl == pytest.approx(0.0, abs=0.01)
        assert unrealized_pnl == pytest.approx(1000.0, abs=0.01)

    def test_unrealized_pnl_price_decrease(self, investor_manager_with_trades):
        """
        Тест: Unrealized P&L при падении цены.

        Сценарий:
        - BUY 100 AAPL @ $150 = $15,000
        - Текущая цена: $140
        - Ожидаемо: positions_value = $14,000, unrealized_pnl = -$1,000
        """
        # ARRANGE
        trades_file = investor_manager_with_trades.investors_dir / "TestInvestor" / "trades.csv"
        with open(trades_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'date', 'timestamp', 'account', 'action', 'ticker',
                'shares', 'price', 'amount', 'total_shares_after', 'notes'
            ])
            writer.writeheader()
            writer.writerow({
                'date': '2025-01-15',
                'timestamp': '10:00:00',
                'account': 'low',
                'action': 'BUY',
                'ticker': 'AAPL',
                'shares': '100.0',
                'price': '150.00',
                'amount': '15000.00',
                'total_shares_after': '100.0',
                'notes': 'Buy'
            })

        # ACT
        current_prices = {'AAPL': 140.0}
        positions_value, realized_pnl, unrealized_pnl = \
            investor_manager_with_trades._calculate_positions_value_and_pnl(
                'TestInvestor', 'low', current_prices
            )

        # ASSERT
        assert positions_value == pytest.approx(14000.0, abs=0.01)
        assert realized_pnl == pytest.approx(0.0, abs=0.01)
        assert unrealized_pnl == pytest.approx(-1000.0, abs=0.01)

    def test_realized_pnl_sell_at_profit(self, investor_manager_with_trades):
        """
        Тест: Realized P&L при продаже с прибылью.

        Сценарий:
        - BUY 100 AAPL @ $150 = $15,000
        - SELL 100 AAPL @ $160 = $16,000
        - Ожидаемо: realized_pnl = $1,000, positions_value = 0, unrealized_pnl = 0
        """
        # ARRANGE
        trades_file = investor_manager_with_trades.investors_dir / "TestInvestor" / "trades.csv"
        with open(trades_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'date', 'timestamp', 'account', 'action', 'ticker',
                'shares', 'price', 'amount', 'total_shares_after', 'notes'
            ])
            writer.writeheader()
            writer.writerows([
                {
                    'date': '2025-01-15',
                    'timestamp': '10:00:00',
                    'account': 'low',
                    'action': 'BUY',
                    'ticker': 'AAPL',
                    'shares': '100.0',
                    'price': '150.00',
                    'amount': '15000.00',
                    'total_shares_after': '100.0',
                    'notes': 'Buy'
                },
                {
                    'date': '2025-01-20',
                    'timestamp': '14:00:00',
                    'account': 'low',
                    'action': 'SELL',
                    'ticker': 'AAPL',
                    'shares': '100.0',
                    'price': '160.00',
                    'amount': '16000.00',
                    'total_shares_after': '0.0',
                    'notes': 'Sell'
                }
            ])

        # ACT
        positions_value, realized_pnl, unrealized_pnl = \
            investor_manager_with_trades._calculate_positions_value_and_pnl(
                'TestInvestor', 'low'
            )

        # ASSERT
        assert positions_value == pytest.approx(0.0, abs=0.01)
        assert realized_pnl == pytest.approx(1000.0, abs=0.01)
        assert unrealized_pnl == pytest.approx(0.0, abs=0.01)

    def test_realized_pnl_sell_at_loss(self, investor_manager_with_trades):
        """
        Тест: Realized P&L при продаже с убытком.

        Сценарий:
        - BUY 100 AAPL @ $150 = $15,000
        - SELL 100 AAPL @ $140 = $14,000
        - Ожидаемо: realized_pnl = -$1,000
        """
        # ARRANGE
        trades_file = investor_manager_with_trades.investors_dir / "TestInvestor" / "trades.csv"
        with open(trades_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'date', 'timestamp', 'account', 'action', 'ticker',
                'shares', 'price', 'amount', 'total_shares_after', 'notes'
            ])
            writer.writeheader()
            writer.writerows([
                {
                    'date': '2025-01-15',
                    'timestamp': '10:00:00',
                    'account': 'low',
                    'action': 'BUY',
                    'ticker': 'AAPL',
                    'shares': '100.0',
                    'price': '150.00',
                    'amount': '15000.00',
                    'total_shares_after': '100.0',
                    'notes': 'Buy'
                },
                {
                    'date': '2025-01-20',
                    'timestamp': '14:00:00',
                    'account': 'low',
                    'action': 'SELL',
                    'ticker': 'AAPL',
                    'shares': '100.0',
                    'price': '140.00',
                    'amount': '14000.00',
                    'total_shares_after': '0.0',
                    'notes': 'Sell'
                }
            ])

        # ACT
        positions_value, realized_pnl, unrealized_pnl = \
            investor_manager_with_trades._calculate_positions_value_and_pnl(
                'TestInvestor', 'low'
            )

        # ASSERT
        assert positions_value == pytest.approx(0.0, abs=0.01)
        assert realized_pnl == pytest.approx(-1000.0, abs=0.01)
        assert unrealized_pnl == pytest.approx(0.0, abs=0.01)

    def test_combined_realized_and_unrealized_pnl(self, investor_manager_with_trades):
        """
        Тест: Комбинированный realized и unrealized P&L.

        Сценарий:
        - BUY 100 AAPL @ $150 = $15,000
        - SELL 50 AAPL @ $160 = $8,000 (realized PnL = $500)
        - Остаток: 50 AAPL @ $150, текущая цена = $170
        - Ожидаемо:
          - realized_pnl = $500
          - unrealized_pnl = 50 * ($170 - $150) = $1,000
          - positions_value = 50 * $170 = $8,500
        """
        # ARRANGE
        trades_file = investor_manager_with_trades.investors_dir / "TestInvestor" / "trades.csv"
        with open(trades_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'date', 'timestamp', 'account', 'action', 'ticker',
                'shares', 'price', 'amount', 'total_shares_after', 'notes'
            ])
            writer.writeheader()
            writer.writerows([
                {
                    'date': '2025-01-15',
                    'timestamp': '10:00:00',
                    'account': 'low',
                    'action': 'BUY',
                    'ticker': 'AAPL',
                    'shares': '100.0',
                    'price': '150.00',
                    'amount': '15000.00',
                    'total_shares_after': '100.0',
                    'notes': 'Buy'
                },
                {
                    'date': '2025-01-20',
                    'timestamp': '14:00:00',
                    'account': 'low',
                    'action': 'SELL',
                    'ticker': 'AAPL',
                    'shares': '50.0',
                    'price': '160.00',
                    'amount': '8000.00',
                    'total_shares_after': '50.0',
                    'notes': 'Sell'
                }
            ])

        # ACT
        current_prices = {'AAPL': 170.0}
        positions_value, realized_pnl, unrealized_pnl = \
            investor_manager_with_trades._calculate_positions_value_and_pnl(
                'TestInvestor', 'low', current_prices
            )

        # ASSERT
        print(f"\nCombined P&L:")
        print(f"  positions_value: ${positions_value:.2f}")
        print(f"  realized_pnl: ${realized_pnl:.2f}")
        print(f"  unrealized_pnl: ${unrealized_pnl:.2f}")

        assert positions_value == pytest.approx(8500.0, abs=0.01)
        assert realized_pnl == pytest.approx(500.0, abs=0.01)
        assert unrealized_pnl == pytest.approx(1000.0, abs=0.01)
