"""
Интеграционные тесты для InvestorManager с детальными проверками расчетов.

Тест-кейс: Полный цикл с тремя инвесторами, включая:
1. Депозиты
2. Ребалансировку и распределение сделок
3. Проверку контрольных сумм
4. Расчет positions_value и P&L
"""
import csv
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from decimal import Decimal

from core.investor_manager import InvestorManager, Investor
import pytz

NY_TIMEZONE = pytz.timezone('America/New_York')


@pytest.fixture
def temp_investors_dir(tmp_path):
    """Создать временную директорию для тестирования."""
    investors_dir = tmp_path / "data" / "investors"
    investors_dir.mkdir(parents=True, exist_ok=True)
    return investors_dir


@pytest.fixture
def registry_file(tmp_path):
    """Создать временный файл реестра инвесторов."""
    registry_path = tmp_path / "investors_registry.csv"

    # Создать реестр с тремя инвесторами
    with open(registry_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'name', 'creation_date', 'fee_percent', 'is_fee_receiver',
            'high_watermark', 'last_fee_date', 'status'
        ])
        writer.writeheader()
        writer.writerows([
            {
                'name': 'Alexey',
                'creation_date': '2025-01-01',
                'fee_percent': '0.0',
                'is_fee_receiver': 'True',
                'high_watermark': '0.0',
                'last_fee_date': '2025-01-01',
                'status': 'active'
            },
            {
                'name': 'Alex',
                'creation_date': '2025-01-01',
                'fee_percent': '0.0',
                'is_fee_receiver': 'True',
                'high_watermark': '0.0',
                'last_fee_date': '2025-01-01',
                'status': 'active'
            },
            {
                'name': 'Cherry',
                'creation_date': '2025-01-15',
                'fee_percent': '20.0',
                'is_fee_receiver': 'False',
                'high_watermark': '10000.0',
                'last_fee_date': '2025-01-01',
                'status': 'active'
            }
        ])

    return registry_path


@pytest.fixture
def investor_manager(tmp_path, registry_file, monkeypatch):
    """Создать InvestorManager с временными директориями."""
    # Изменить рабочую директорию
    monkeypatch.chdir(tmp_path)

    manager = InvestorManager(str(registry_file))
    manager.investors_dir = tmp_path / "data" / "investors"
    manager.investors_dir.mkdir(parents=True, exist_ok=True)

    # Создать директории для инвесторов
    for investor_name in ['Alexey', 'Alex', 'Cherry']:
        investor_dir = manager.investors_dir / investor_name
        investor_dir.mkdir(parents=True, exist_ok=True)

    return manager


class TestDepositAndDistribution:
    """Тесты для депозитов и распределения сделок."""

    def test_deposit_default_allocation(self, investor_manager):
        """
        Тест: Депозит инвестора распределяется по умолчанию 45/35/20.

        Сценарий:
        - Cherry вносит $10,000
        - Проверить, что создаются 3 pending операции:
          - LOW: $4,500 (45%)
          - MEDIUM: $3,500 (35%)
          - HIGH: $2,000 (20%)
        """
        # ARRANGE
        investor_name = 'Cherry'
        amount = 10000.0
        now = datetime.now(NY_TIMEZONE)

        # ACT
        operation_ids = investor_manager.deposit(investor_name, amount, date=now)

        # ASSERT
        assert len(operation_ids) == 3, "Должно быть создано 3 операции"

        # Проверить файл operations.csv
        operations_file = investor_manager.investors_dir / investor_name / 'operations.csv'
        assert operations_file.exists(), "Файл operations.csv должен существовать"

        operations = []
        with open(operations_file, 'r') as f:
            reader = csv.DictReader(f)
            operations = list(reader)

        assert len(operations) == 3, f"Должно быть 3 операции, но есть {len(operations)}"

        # Проверить каждую операцию
        operations_by_account = {op['account']: op for op in operations}

        # LOW: 45% = $4,500
        low_op = operations_by_account.get('low')
        assert low_op is not None, "Операция для LOW должна существовать"
        assert float(low_op['amount']) == 4500.0, f"LOW должен быть $4,500, но {float(low_op['amount'])}"
        assert low_op['operation'] == 'deposit'
        assert low_op['status'] == 'pending'

        # MEDIUM: 35% = $3,500
        medium_op = operations_by_account.get('medium')
        assert medium_op is not None, "Операция для MEDIUM должна существовать"
        assert float(medium_op['amount']) == 3500.0, f"MEDIUM должен быть $3,500"
        assert medium_op['operation'] == 'deposit'
        assert medium_op['status'] == 'pending'

        # HIGH: 20% = $2,000
        high_op = operations_by_account.get('high')
        assert high_op is not None, "Операция для HIGH должна существовать"
        assert float(high_op['amount']) == 2000.0, f"HIGH должен быть $2,000"
        assert high_op['operation'] == 'deposit'
        assert high_op['status'] == 'pending'

    def test_distribute_trade_proportional(self, investor_manager):
        """
        Тест: Сделки распределяются пропорционально капиталу инвесторов.

        Сценарий:
        - Alexey: $10,000 (40% от total = $4,000 на LOW)
        - Alex: $5,000 (20% от total = $2,000 на LOW)
        - Cherry: $10,000 (40% от total = $4,000 на LOW)
        - Total на LOW: $10,000

        Покупка 100 акций AAPL по $100:
        - Alexey получит: 100 * 40% = 40 акций
        - Alex получит: 100 * 20% = 20 акций
        - Cherry получит: 100 * 40% = 40 акций
        """
        # ARRANGE
        now = datetime.now(NY_TIMEZONE)

        # Создать депозиты для всех инвесторов
        for investor_name, amount in [('Alexey', 10000), ('Alex', 5000), ('Cherry', 10000)]:
            investor_manager.deposit(investor_name, amount, date=now)
            # Mark as completed
            ops_file = investor_manager.investors_dir / investor_name / 'operations.csv'
            rows = []
            with open(ops_file, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            for row in rows:
                row['status'] = 'completed'
                if row['operation'] == 'deposit' and row['account'] == 'low':
                    row['balance_after'] = row['amount']
            with open(ops_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys() if rows else [])
                writer.writeheader()
                writer.writerows(rows)

        # ACT - Распределить сделку
        investor_manager.distribute_trade_to_investors(
            account='low',
            action='BUY',
            ticker='AAPL',
            total_shares=100.0,
            price=100.0
        )

        # ASSERT - Проверить распределение в trades.csv
        expected_distribution = {
            'Alexey': {'shares': 40.0, 'cost': 4000.0},
            'Alex': {'shares': 20.0, 'cost': 2000.0},
            'Cherry': {'shares': 40.0, 'cost': 4000.0}
        }

        for investor_name, expected in expected_distribution.items():
            trades_file = investor_manager.investors_dir / investor_name / 'trades.csv'
            assert trades_file.exists(), f"trades.csv для {investor_name} должен существовать"

            with open(trades_file, 'r') as f:
                reader = csv.DictReader(f)
                trades = list(reader)

            assert len(trades) == 1, f"Должна быть 1 сделка для {investor_name}"
            trade = trades[0]

            actual_shares = float(trade['shares'])
            actual_price = float(trade['price'])
            actual_amount = float(trade['amount'])
            actual_total_shares = float(trade['total_shares_after'])

            print(f"\n{investor_name}:")
            print(f"  Expected: {expected['shares']} shares @ $100 = ${expected['cost']}")
            print(f"  Actual: {actual_shares} shares @ ${actual_price} = ${actual_amount}")

            assert actual_shares == pytest.approx(expected['shares'], abs=0.01), \
                f"{investor_name}: ожидается {expected['shares']} акций, получено {actual_shares}"
            assert actual_price == 100.0
            assert actual_amount == pytest.approx(expected['cost'], abs=0.01)
            assert actual_total_shares == pytest.approx(expected['shares'], abs=0.01)

    def test_balance_calculation_with_positions(self, investor_manager):
        """
        Тест: Расчет баланса инвестора с учетом positions_value.

        Сценарий:
        - Alexey: $10,000 (распределено 45/35/20)
        - Alex: $5,000 (распределено 45/35/20)
        - Cherry: $10,000 (распределено 45/35/20)
        - Total на LOW: $10,000 капитала

        Распределение на LOW:
        - Alexey: $4,500 (45%)
        - Alex: $2,250 (22.5%)
        - Cherry: $4,500 (45%)
        - Ждите, это 91.5%!  Нет, $10,000 * 45% = $4,500 на LOW всего,
          но это от общего $25,000, так что на LOW:
          - Alexey: $10,000 * 45% = $4,500
          - Alex: $5,000 * 45% = $2,250
          - Cherry: $10,000 * 45% = $4,500
          - Total: $11,250

        Покупка 10 акций AAPL @ $100 = $1,000:
        - Alexey получит: 10 * ($4,500/$11,250) = 4 акции
        - Alex получит: 10 * ($2,250/$11,250) = 2 акции
        - Cherry получит: 10 * ($4,500/$11,250) = 4 акции
        """
        # ARRANGE
        now = datetime.now(NY_TIMEZONE)

        # Все три инвестора вносят деньги
        for investor_name, amount in [('Alexey', 10000), ('Alex', 5000), ('Cherry', 10000)]:
            investor_manager.deposit(investor_name, amount, date=now)

            # Mark as completed
            ops_file = investor_manager.investors_dir / investor_name / 'operations.csv'
            rows = []
            with open(ops_file, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            for row in rows:
                row['status'] = 'completed'
                row['balance_after'] = row['amount']
            with open(ops_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

        # Покупка 10 акций AAPL @ $100 = $1,000 на LOW
        investor_manager.distribute_trade_to_investors(
            account='low',
            action='BUY',
            ticker='AAPL',
            total_shares=10.0,
            price=100.0
        )

        # ACT
        cherry_balance = investor_manager.calculate_investor_balance('Cherry')
        all_balances = investor_manager.get_all_balances()

        # ASSERT - Проверить Cherry
        print(f"\nCherry Balance:")
        print(f"  LOW:")
        print(f"    cash: ${cherry_balance['low']['cash']:.2f}")
        print(f"    positions_value: ${cherry_balance['low']['positions_value']:.2f}")
        print(f"    total: ${cherry_balance['low']['total_value']:.2f}")
        print(f"  MEDIUM:")
        print(f"    cash: ${cherry_balance['medium']['cash']:.2f}")
        print(f"    total: ${cherry_balance['medium']['total_value']:.2f}")
        print(f"  HIGH:")
        print(f"    cash: ${cherry_balance['high']['cash']:.2f}")
        print(f"    total: ${cherry_balance['high']['total_value']:.2f}")
        print(f"  TOTAL: ${cherry_balance['total_value']:.2f}")

        # Cherry внес $10,000, и это не изменилось
        assert cherry_balance['total_value'] == pytest.approx(10000.0, abs=1.0), \
            f"Total value должна быть $10,000, но {cherry_balance['total_value']}"

        # На LOW: покупил AAPL на $1,000, значит cash = $4,500 - $1,000 = $3,500
        expected_cash_low = 4500.0 - (10.0 * 100.0 * (4500.0 / 11250.0))
        assert cherry_balance['low']['cash'] == pytest.approx(expected_cash_low, abs=1.0), \
            f"Cash на LOW должна быть ~$3,600, но {cherry_balance['low']['cash']}"

        # Проверить целостность по всем инвесторам
        print(f"\nAll Balances:")
        total_virtual = 0.0
        for investor_name, balance_info in all_balances.items():
            print(f"  {investor_name}: ${balance_info['total_value']:.2f}")
            total_virtual += balance_info['total_value']
        print(f"  TOTAL: ${total_virtual:.2f}")

        assert total_virtual == pytest.approx(25000.0, abs=1.0), \
            f"Total virtual баланс должен быть $25,000, но {total_virtual}"


class TestPnLCalculation:
    """Тесты для расчета P&L."""

    def test_pnl_with_price_increase(self, investor_manager):
        """
        Тест: Расчет P&L при росте цены.

        Сценарий:
        - Alexey вносит $10,000
        - Покупает 100 акций AAPL по $100 (cost = $10,000)
        - Цена растет до $120
        - Unrealized P&L = (120-100) * 100 = $2,000
        """
        # ARRANGE
        now = datetime.now(NY_TIMEZONE)
        investor_manager.deposit('Alexey', 10000.0, date=now)

        # Mark as completed
        ops_file = investor_manager.investors_dir / 'Alexey' / 'operations.csv'
        rows = []
        with open(ops_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        for row in rows:
            row['status'] = 'completed'
            row['balance_after'] = row['amount']
        with open(ops_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        # Покупка
        investor_manager.distribute_trade_to_investors(
            account='low',
            action='BUY',
            ticker='AAPL',
            total_shares=100.0,
            price=100.0
        )

        # ACT - Рассчитать с новыми ценами
        current_prices = {'AAPL': 120.0}
        positions_value, realized_pnl, unrealized_pnl = \
            investor_manager._calculate_positions_value_and_pnl(
                'Alexey', 'low', current_prices
            )

        # ASSERT
        print(f"\nAlexy P&L with price increase to $120:")
        print(f"  positions_value: ${positions_value}")
        print(f"  unrealized_pnl: ${unrealized_pnl}")
        print(f"  realized_pnl: ${realized_pnl}")

        # Alexey имеет все $10,000 на low (100%)
        # Он получит 100 * 100% = 100 акций
        assert positions_value == pytest.approx(100 * 120, abs=0.01), \
            "positions_value должна быть 100 акций @ $120 = $12,000"
        assert unrealized_pnl == pytest.approx(100 * 20, abs=0.01), \
            "unrealized_pnl должна быть $2,000"

    def test_balance_integrity_check(self, investor_manager):
        """
        Тест: Проверка целостности баланса (контрольные суммы).

        Сценарий:
        - Alexey: $10,000 (40% = $4,000 на low + $3,000 на medium + $3,000 на high)
        - Alex: $5,000 (20% = $2,000 + $1,500 + $1,500)
        - Cherry: $10,000 (40% = $4,000 + $3,000 + $3,000)
        - Total virtual = $25,000
        - Real equity должен быть $25,000

        Проверить:
        1. SUM(cash всех инвесторов) = SUM(deposits) - SUM(withdrawals) - SUM(fees)
        2. SUM(positions всех инвесторов) = SUM(покупок) * share - SUM(продаж) * share
        """
        # ARRANGE
        now = datetime.now(NY_TIMEZONE)

        # Создать депозиты
        for investor_name, amount in [('Alexey', 10000), ('Alex', 5000), ('Cherry', 10000)]:
            investor_manager.deposit(investor_name, amount, date=now)

        # Mark as completed
        for investor_name in ['Alexey', 'Alex', 'Cherry']:
            ops_file = investor_manager.investors_dir / investor_name / 'operations.csv'
            rows = []
            with open(ops_file, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            for row in rows:
                row['status'] = 'completed'
                row['balance_after'] = row['amount']
            with open(ops_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

        # ACT - Получить все балансы
        all_balances = investor_manager.get_all_balances()

        # ASSERT - Проверить контрольные суммы
        total_virtual = sum(
            b['total_value'] for b in all_balances.values()
        )

        print(f"\nBalance Integrity Check:")
        for investor_name, balance in all_balances.items():
            print(f"  {investor_name}: ${balance['total_value']:.2f}")
        print(f"  TOTAL: ${total_virtual:.2f}")

        assert total_virtual == pytest.approx(25000.0, abs=1.0), \
            f"Total virtual баланс должен быть $25,000, но {total_virtual}"

        # Проверить распределение по счетам
        low_total = sum(
            b['accounts']['low']['total_value'] for b in all_balances.values()
        )
        medium_total = sum(
            b['accounts']['medium']['total_value'] for b in all_balances.values()
        )
        high_total = sum(
            b['accounts']['high']['total_value'] for b in all_balances.values()
        )

        print(f"  LOW: ${low_total:.2f} (45% expected: ${25000 * 0.45:.2f})")
        print(f"  MEDIUM: ${medium_total:.2f} (35% expected: ${25000 * 0.35:.2f})")
        print(f"  HIGH: ${high_total:.2f} (20% expected: ${25000 * 0.20:.2f})")

        assert low_total == pytest.approx(25000 * 0.45, abs=1.0)
        assert medium_total == pytest.approx(25000 * 0.35, abs=1.0)
        assert high_total == pytest.approx(25000 * 0.20, abs=1.0)
