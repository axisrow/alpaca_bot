"""Управление инвесторами и их операциями в LiveStrategy."""
import csv
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

import pytz
from alpaca.trading.client import TradingClient

NY_TIMEZONE = pytz.timezone('America/New_York')


@dataclass
class Investor:
    """Dataclass инвестора."""
    name: str
    creation_date: datetime
    fee_percent: float
    is_fee_receiver: bool
    high_watermark: float
    last_fee_date: datetime
    status: str  # active, inactive


class InvestorManager:
    """Управление инвесторами и их операциями."""

    # Распределение по умолчанию
    DEFAULT_ALLOCATION = {'low': 0.45, 'medium': 0.35, 'high': 0.20}

    def __init__(self, registry_path: str = 'investors_registry.csv'):
        """Инициализация менеджера инвесторов.

        Args:
            registry_path: Путь к файлу реестра инвесторов
        """
        self.registry_path = Path(registry_path)
        self.investors_dir = Path('data/investors')
        self.investors: Dict[str, Investor] = {}
        self.ny_timezone = NY_TIMEZONE
        self._load_registry()
        self._ensure_investor_directories()

    def _active_investors(self) -> Dict[str, Investor]:
        """Вернуть только активных инвесторов."""
        return {
            name: investor
            for name, investor in self.investors.items()
            if investor.status.lower() == 'active'
        }

    def _load_registry(self) -> None:
        """Загрузить реестр инвесторов из CSV."""
        if not self.registry_path.exists():
            logging.warning("Registry file not found: %s", self.registry_path)
            return

        try:
            with open(self.registry_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    investor = Investor(
                        name=row['name'],
                        creation_date=datetime.strptime(
                            row['creation_date'], '%Y-%m-%d'
                        ).replace(tzinfo=NY_TIMEZONE),
                        fee_percent=float(row['fee_percent']),
                        is_fee_receiver=row['is_fee_receiver'].lower() == 'true',
                        high_watermark=float(row['high_watermark']),
                        last_fee_date=datetime.strptime(
                            row['last_fee_date'], '%Y-%m-%d'
                        ).replace(tzinfo=NY_TIMEZONE),
                        status=row['status']
                    )
                    self.investors[investor.name] = investor

            logging.info("Loaded %d investors from registry", len(self.investors))
        except Exception as exc:
            logging.error("Error loading registry: %s", exc)

    def _save_registry(self) -> None:
        """Сохранить текущее состояние реестра инвесторов."""
        if not self.registry_path:
            return

        fieldnames = [
            'name',
            'creation_date',
            'fee_percent',
            'is_fee_receiver',
            'high_watermark',
            'last_fee_date',
            'status'
        ]

        try:
            with open(self.registry_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for investor in self.investors.values():
                    writer.writerow({
                        'name': investor.name,
                        'creation_date': investor.creation_date.strftime('%Y-%m-%d'),
                        'fee_percent': f"{investor.fee_percent:.4f}",
                        'is_fee_receiver': str(investor.is_fee_receiver),
                        'high_watermark': f"{investor.high_watermark:.2f}",
                        'last_fee_date': investor.last_fee_date.strftime('%Y-%m-%d'),
                        'status': investor.status
                    })
        except Exception as exc:
            logging.error("Error saving registry: %s", exc)

    def _ensure_investor_directories(self) -> None:
        """Создать папки для всех инвесторов."""
        self.investors_dir.mkdir(parents=True, exist_ok=True)
        for investor_name in self.investors:
            investor_path = self._get_investor_path(investor_name)
            investor_path.mkdir(parents=True, exist_ok=True)

    def _get_investor_path(self, name: str) -> Path:
        """Получить путь к папке инвестора."""
        return self.investors_dir / name

    def investor_exists(self, name: str) -> bool:
        """Проверить существование инвестора."""
        return name in self.investors

    # ==================== ОПЕРАЦИИ ====================

    def deposit(self, name: str, amount: float, account: Optional[str] = None,
                date: Optional[datetime] = None) -> List[str]:
        """Создать pending депозит.

        Args:
            name: Имя инвестора
            amount: Сумма
            account: 'low', 'medium', 'high' или None (распределить по умолчанию)
            date: Дата операции

        Returns:
            List[str]: Список operation_id
        """
        if not self.investor_exists(name):
            raise ValueError(f"Investor '{name}' not found")

        date = date or datetime.now(NY_TIMEZONE)
        operation_ids = []

        if account:
            # Зачисление на конкретный счет
            if account not in self.DEFAULT_ALLOCATION:
                raise ValueError(f"Invalid account: {account}")

            operation_id = self._create_operation(
                name, 'deposit', account, amount, date
            )
            operation_ids.append(operation_id)
            logging.info(
                "Created deposit operation for %s: %s account, $%.2f",
                name, account, amount
            )
        else:
            # Распределение по умолчанию
            for acc, percentage in self.DEFAULT_ALLOCATION.items():
                dep_amount = amount * percentage
                operation_id = self._create_operation(
                    name, 'deposit', acc, dep_amount, date
                )
                operation_ids.append(operation_id)
                logging.info(
                    "Created deposit operation for %s: %s account, $%.2f",
                    name, acc, dep_amount
                )

        return operation_ids

    def withdraw(self, name: str, amount: float, account: Optional[str] = None,
                 date: Optional[datetime] = None) -> List[str]:
        """Создать pending снятие.

        Args:
            name: Имя инвестора
            amount: Сумма
            account: 'low', 'medium', 'high' или None (пропорционально балансу)
            date: Дата операции

        Returns:
            List[str]: Список operation_id
        """
        if not self.investor_exists(name):
            raise ValueError(f"Investor '{name}' not found")

        date = date or datetime.now(NY_TIMEZONE)
        operation_ids = []

        if account:
            # Снятие со специфического счета
            if account not in self.DEFAULT_ALLOCATION:
                raise ValueError(f"Invalid account: {account}")

            # Проверить баланс
            balance = self.calculate_investor_balance(name)
            available = balance[account]['total_value']
            if amount > available:
                raise ValueError(
                    f"Insufficient balance on {account}: "
                    f"${available:.2f} < ${amount:.2f}"
                )

            operation_id = self._create_operation(
                name, 'withdraw', account, amount, date
            )
            operation_ids.append(operation_id)
            logging.info(
                "Created withdrawal operation for %s: %s account, $%.2f",
                name, account, amount
            )
        else:
            # Снятие пропорционально балансу
            balance = self.calculate_investor_balance(name)
            total_balance = balance['total_value']

            if amount > total_balance:
                raise ValueError(
                    f"Insufficient total balance: "
                    f"${total_balance:.2f} < ${amount:.2f}"
                )

            for acc, percentage in self.DEFAULT_ALLOCATION.items():
                withdraw_amount = amount * percentage
                operation_id = self._create_operation(
                    name, 'withdraw', acc, withdraw_amount, date
                )
                operation_ids.append(operation_id)
                logging.info(
                    "Created withdrawal operation for %s: %s account, $%.2f",
                    name, acc, withdraw_amount
                )

        return operation_ids

    def _create_operation(self, investor: str, operation_type: str,
                         account: str, amount: float,
                         date: datetime) -> str:
        """Создать операцию в файл operations.csv инвестора.

        Returns:
            str: operation_id (дата + время + счет)
        """
        investor_path = self._get_investor_path(investor)
        operations_file = investor_path / 'operations.csv'

        # Генерировать operation_id
        operation_id = f"{date.strftime('%Y%m%d_%H%M%S')}_{account}"

        # Подготовить данные
        timestamp = date.strftime('%Y-%m-%d %H:%M:%S')
        status = 'pending'
        balance_after = 0  # Обновится при process_pending_operations

        # Проверить существование файла
        file_exists = operations_file.exists()

        try:
            with open(operations_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Написать заголовок если файл новый
                if not file_exists:
                    writer.writerow([
                        'date', 'timestamp', 'operation', 'account',
                        'amount', 'status', 'balance_after', 'notes'
                    ])

                # Написать строку операции
                writer.writerow([
                    date.strftime('%Y-%m-%d'),
                    timestamp,
                    operation_type,
                    account,
                    f"{amount:.2f}",
                    status,
                    balance_after,
                    f"{operation_type.capitalize()} to {account}"
                ])

            logging.info(
                "Operation %s created for %s",
                operation_id, investor
            )
            return operation_id

        except Exception as exc:
            logging.error(
                "Error creating operation for %s: %s",
                investor, exc
            )
            raise

    # ==================== ОБРАБОТКА ОПЕРАЦИЙ ====================

    def process_pending_operations(self) -> Dict:
        """Обработать все pending операции при ребалансировке.

        Returns:
            Dict: Результаты обработки
        """
        results = {
            'processed': 0,
            'completed': [],
            'failed': []
        }

        for investor_name in self._active_investors():
            investor_results = self._process_investor_pending_ops(
                investor_name
            )
            results['processed'] += investor_results['processed']
            results['completed'].extend(investor_results['completed'])
            results['failed'].extend(investor_results['failed'])

        logging.info(
            "Processed pending operations: %d completed, %d failed",
            len(results['completed']),
            len(results['failed'])
        )

        return results

    def _process_investor_pending_ops(self, investor: str) -> Dict:
        """Обработать pending операции для одного инвестора."""
        investor_path = self._get_investor_path(investor)
        operations_file = investor_path / 'operations.csv'

        if not operations_file.exists():
            return {'processed': 0, 'completed': [], 'failed': []}

        results = {'processed': 0, 'completed': [], 'failed': []}
        updated_rows = []

        try:
            with open(operations_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                header = reader.fieldnames

                for row in reader:
                    if row['status'] == 'pending':
                        # Обновить статус на completed
                        row['status'] = 'completed'
                        row['balance_after'] = self._calculate_account_balance(
                            investor, row['account']
                        )
                        results['completed'].append(row['date'])
                        results['processed'] += 1
                        logging.info(
                            "Processed pending %s for %s on %s",
                            row['operation'],
                            investor,
                            row['account']
                        )

                    updated_rows.append(row)

            # Перезаписать файл с обновленными статусами
            with open(operations_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=header)
                writer.writeheader()
                writer.writerows(updated_rows)

        except Exception as exc:
            logging.error(
                "Error processing pending operations for %s: %s",
                investor, exc
            )

        return results

    def _calculate_account_balance(self, investor: str, account: str) -> float:
        """Рассчитать текущий баланс счета (только cash из operations.csv и trades).

        Логика:
        - Начальный баланс = SUM(deposits) - SUM(withdrawals) - SUM(fees) (из operations.csv)
        - Потом учитываем trades: для каждой BUY уменьшаем cash, для каждой SELL увеличиваем
        - Итого: balance = deposits - withdrawals - fees - (spent_on_buys) + (received_from_sells)
        """
        investor_path = self._get_investor_path(investor)
        operations_file = investor_path / 'operations.csv'
        trades_file = investor_path / 'trades.csv'

        balance = 0.0

        # 1. Получить balance из operations.csv
        if operations_file.exists():
            try:
                with open(operations_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['account'] == account and row['status'] == 'completed':
                            amount = float(row['amount'])
                            if row['operation'] == 'deposit':
                                balance += amount
                            elif row['operation'] == 'withdraw':
                                balance -= amount
                            elif row['operation'] == 'fee':
                                balance -= amount

            except Exception as exc:
                logging.error(
                    "Error reading operations for %s:%s - %s",
                    investor, account, exc
                )

        # 2. Учитать trades (BUY уменьшает cash, SELL увеличивает)
        if trades_file.exists():
            try:
                with open(trades_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row['account'] == account:
                            action = row['action']
                            amount = float(row['amount'])

                            if action == 'BUY':
                                # BUY уменьшает доступный cash
                                balance -= amount
                            elif action == 'SELL':
                                # SELL увеличивает cash
                                balance += amount

            except Exception as exc:
                logging.error(
                    "Error reading trades for %s:%s - %s",
                    investor, account, exc
                )

        return balance

    def _get_investor_positions(self, investor: str, account: str) -> Dict[str, float]:
        """Получить текущие позиции инвестора (количество акций по тикерам).

        Returns:
            Dict: {ticker: current_shares}
        """
        investor_path = self._get_investor_path(investor)
        trades_file = investor_path / 'trades.csv'

        positions = {}

        if not trades_file.exists():
            return positions

        try:
            with open(trades_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['account'] == account:
                        ticker = row['ticker']
                        total_shares_after = float(row['total_shares_after'])
                        # Последняя запись по тикеру - это текущее количество
                        positions[ticker] = total_shares_after

        except Exception as exc:
            logging.error(
                "Error getting positions for %s:%s - %s",
                investor, account, exc
            )

        return positions

    def _calculate_positions_value_and_pnl(
        self,
        investor: str,
        account: str,
        current_prices: Optional[Dict[str, float]] = None
    ) -> Tuple[float, float, float]:
        """Рассчитать стоимость позиций и P&L из trades.csv.

        Args:
            investor: Имя инвестора
            account: Счет (low/medium/high)
            current_prices: Dict[ticker] = current_price. Если None, используется последняя цена из trades.csv

        Returns:
            Tuple: (positions_value, realized_pnl, unrealized_pnl)
        """
        investor_path = self._get_investor_path(investor)
        trades_file = investor_path / 'trades.csv'

        positions_value = 0.0
        realized_pnl = 0.0
        unrealized_pnl = 0.0

        if not trades_file.exists():
            return 0.0, 0.0, 0.0

        try:
            # Получить текущие позиции
            positions = self._get_investor_positions(investor, account)

            # Для каждого тикера отслеживать cost basis
            ticker_cost_basis = {}     # {ticker: {total_cost, total_shares, last_price}}

            with open(trades_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['account'] == account:
                        ticker = row['ticker']
                        action = row['action']
                        shares = float(row['shares'])
                        price = float(row['price'])

                        # Инициализировать если не существует
                        if ticker not in ticker_cost_basis:
                            ticker_cost_basis[ticker] = {
                                'total_cost': 0.0,
                                'total_shares': 0.0,
                                'last_price': price
                            }

                        data = ticker_cost_basis[ticker]
                        data['last_price'] = price

                        if action == 'BUY':
                            data['total_cost'] += shares * price
                            data['total_shares'] += shares
                        elif action == 'SELL':
                            # Расчет realized PnL (FIFO метод)
                            if data['total_shares'] > 0:
                                avg_cost = data['total_cost'] / data['total_shares']
                                sell_revenue = shares * price
                                cost_of_sold = shares * avg_cost
                                realized_pnl += sell_revenue - cost_of_sold

                                # Обновить cost basis
                                data['total_cost'] = max(0, data['total_cost'] - cost_of_sold)
                                data['total_shares'] = max(0, data['total_shares'] - shares)

            # Рассчитать positions_value и unrealized_pnl
            for ticker, current_shares in positions.items():
                if current_shares > 0 and ticker in ticker_cost_basis:
                    data = ticker_cost_basis[ticker]

                    # Использовать текущую цену или последнюю цену из trades
                    if current_prices and ticker in current_prices:
                        current_price = current_prices[ticker]
                    else:
                        current_price = data['last_price']

                    # Стоимость позиции
                    position_value = current_shares * current_price
                    positions_value += position_value

                    # Unrealized PnL
                    if data['total_shares'] > 0:
                        avg_cost = data['total_cost'] / data['total_shares']
                        unrealized_pnl += (current_price - avg_cost) * current_shares

        except Exception as exc:
            logging.error(
                "Error calculating positions for %s:%s - %s",
                investor, account, exc
            )

        return positions_value, realized_pnl, unrealized_pnl

    # ==================== РАСЧЕТЫ ====================

    def check_and_calculate_fees(self, at_rebalance: bool = True,
                                 for_investor: Optional[str] = None) -> Dict:
        """Проверить HWM и рассчитать комиссии.

        Args:
            at_rebalance: True если вызывается при ежемесячной ребалансировке,
                         False если при выводе/закрытии счета
            for_investor: Конкретный инвестор (опционально)

        Returns:
            Dict: {investor_name: fee_amount}
        """
        fees = {}
        now = datetime.now(tz=self.ny_timezone)
        registry_updated = False

        investors_to_check = (
            [for_investor] if for_investor else self.investors.keys()
        )

        for investor_name in investors_to_check:
            if investor_name not in self.investors:
                continue

            investor = self.investors[investor_name]

            # Пропустить если инвестор получает комиссию (управляющий)
            if investor.is_fee_receiver:
                continue

            # Проверить условие расчета комиссии в зависимости от контекста
            should_calculate_fee = False
            if at_rebalance:
                # Ежемесячный расчет: проверить, прошел ли месяц с последней комиссии
                last_fee = investor.last_fee_date
                months_passed = (now.year - last_fee.year) * 12 + (now.month - last_fee.month)
                if months_passed >= 1:
                    should_calculate_fee = True
            else:
                # При выводе/закрытии: всегда рассчитывать комиссию
                should_calculate_fee = True

            if not should_calculate_fee:
                continue

            # Рассчитать текущий баланс
            current_balance = self.calculate_investor_balance(investor_name)
            current_value = current_balance['total_value']

            # Проверить HWM
            if current_value > investor.high_watermark:
                profit = current_value - investor.high_watermark
                fee = profit * investor.fee_percent

                if fee > 0:
                    fees[investor_name] = fee
                    logging.info(
                        "Fee for %s: $%.2f (profit: $%.2f, rate: %.1f%%, at_rebalance=%s)",
                        investor_name, fee, profit, investor.fee_percent * 100, at_rebalance
                    )

                    # Обновить дату последней комиссии только при ежемесячном расчете
                    if at_rebalance:
                        investor.last_fee_date = now
                        registry_updated = True

                    # Обновить HWM в любом случае
                    investor.high_watermark = current_value
                    registry_updated = True

        if registry_updated:
            self._save_registry()

        return fees

    def get_account_allocations(self) -> Dict[str, Dict[str, float]]:
        """Получить распределение капитала по счетам.

        Returns:
            Dict: {account: {investor: balance, ..., total: sum}}
        """
        allocations = {
            'low': defaultdict(float),
            'medium': defaultdict(float),
            'high': defaultdict(float)
        }

        active_investors = self._active_investors()
        for investor_name in active_investors:
            balance = self.calculate_investor_balance(investor_name)

            for account in ['low', 'medium', 'high']:
                account_balance = balance[account]['total_value']
                allocations[account][investor_name] = account_balance

        # Добавить totals
        for account in ['low', 'medium', 'high']:
            allocations[account]['total'] = sum(
                v for k, v in allocations[account].items() if k != 'total'
            )

        return allocations

    def calculate_investor_balance(self, name: str) -> Dict:
        """Рассчитать баланс инвестора по всем счетам.

        Returns:
            Dict: {
                'low': {'total_value': X, ...},
                'medium': {...},
                'high': {...},
            'total_value': X
        }
        """
        investor = self.investors.get(name)
        if not investor or investor.status.lower() != 'active':
            logging.info(
                "Skipping balance calculation for inactive investor %s",
                name
            )
            return {
                'low': {
                    'cash': 0.0,
                    'positions_value': 0.0,
                    'total_value': 0.0,
                    'pnl': 0.0
                },
                'medium': {
                    'cash': 0.0,
                    'positions_value': 0.0,
                    'total_value': 0.0,
                    'pnl': 0.0
                },
                'high': {
                    'cash': 0.0,
                    'positions_value': 0.0,
                    'total_value': 0.0,
                    'pnl': 0.0
                },
                'total_value': 0.0
            }

        balance = {
            'low': {
                'cash': 0.0,
                'positions_value': 0.0,
                'total_value': 0.0,
                'pnl': 0.0
            },
            'medium': {
                'cash': 0.0,
                'positions_value': 0.0,
                'total_value': 0.0,
                'pnl': 0.0
            },
            'high': {
                'cash': 0.0,
                'positions_value': 0.0,
                'total_value': 0.0,
                'pnl': 0.0
            },
            'total_value': 0.0
        }

        # Рассчитать каждый счет
        for account in ['low', 'medium', 'high']:
            cash = self._calculate_account_balance(name, account)
            positions_value, realized_pnl, unrealized_pnl = self._calculate_positions_value_and_pnl(
                name, account
            )

            balance[account]['cash'] = cash
            balance[account]['positions_value'] = positions_value
            balance[account]['pnl'] = realized_pnl + unrealized_pnl
            balance[account]['total_value'] = cash + positions_value
            balance['total_value'] += balance[account]['total_value']

        return balance

    def get_all_balances(self) -> Dict:
        """Получить балансы всех инвесторов."""
        balances = {}

        for investor_name in self._active_investors():
            balance = self.calculate_investor_balance(investor_name)

            # Рассчитать общий P&L
            total_pnl = (
                balance.get('low', {}).get('pnl', 0.0) +
                balance.get('medium', {}).get('pnl', 0.0) +
                balance.get('high', {}).get('pnl', 0.0)
            )

            balances[investor_name] = {
                'total_value': balance['total_value'],
                'pnl': total_pnl,
                'accounts': balance
            }

        return balances

    # ==================== ИСТОРИЯ СДЕЛОК ====================

    def distribute_trade_to_investors(self, account: str, action: str,
                                      ticker: str, total_shares: float,
                                      price: float) -> None:
        """Распределить сделку по инвесторам пропорционально.

        Args:
            account: Счет (low/medium/high)
            action: BUY или SELL
            ticker: Тикер
            total_shares: Всего акций
            price: Цена за акцию
        """
        # Получить распределение капитала
        allocations = self.get_account_allocations()
        account_allocations = allocations[account]
        total_capital = account_allocations['total']

        if total_capital <= 0:
            logging.warning(
                "No capital in %s account, skipping trade distribution",
                account
            )
            return

        # Распределить по инвесторам пропорционально
        for investor_name in self._active_investors():
            investor_capital = account_allocations.get(investor_name, 0.0)

            if investor_capital <= 0:
                continue

            # Рассчитать долю инвестора
            share = investor_capital / total_capital
            investor_shares = total_shares * share

            # Записать сделку
            self._record_trade(
                investor_name,
                account,
                action,
                ticker,
                investor_shares,
                price
            )

    def _record_trade(self, investor: str, account: str, action: str,
                     ticker: str, shares: float, price: float) -> None:
        """Записать сделку в trades.csv инвестора."""
        investor_path = self._get_investor_path(investor)
        trades_file = investor_path / 'trades.csv'

        # Рассчитать amount и total_shares_after
        amount = shares * price
        total_shares_after = self._get_total_investor_shares(
            investor, account, ticker
        )

        if action == 'BUY':
            total_shares_after += shares
        elif action == 'SELL':
            total_shares_after -= shares

        timestamp = datetime.now(NY_TIMEZONE)
        file_exists = trades_file.exists()

        try:
            with open(trades_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                if not file_exists:
                    writer.writerow([
                        'date', 'timestamp', 'account', 'action', 'ticker',
                        'shares', 'price', 'amount', 'total_shares_after', 'notes'
                    ])

                writer.writerow([
                    timestamp.strftime('%Y-%m-%d'),
                    timestamp.strftime('%H:%M:%S'),
                    account,
                    action,
                    ticker,
                    f"{shares:.4f}",
                    f"{price:.2f}",
                    f"{amount:.2f}",
                    f"{total_shares_after:.4f}",
                    f"Rebalance - {action} {shares:.4f} shares @ ${price:.2f}"
                ])

            logging.info(
                "Recorded %s for %s: %s %s %.4f @ $%.2f",
                action, investor, account, ticker, shares, price
            )

        except Exception as exc:
            logging.error(
                "Error recording trade for %s: %s",
                investor, exc
            )

    def _get_total_investor_shares(self, investor: str, account: str,
                                   ticker: str) -> float:
        """Получить текущее количество акций инвестора."""
        investor_path = self._get_investor_path(investor)
        trades_file = investor_path / 'trades.csv'

        if not trades_file.exists():
            return 0.0

        total_shares = 0.0

        try:
            with open(trades_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['account'] == account and row['ticker'] == ticker:
                        total_shares = float(row['total_shares_after'])

        except Exception as exc:
            logging.error(
                "Error getting total shares for %s:%s:%s - %s",
                investor, account, ticker, exc
            )

        return total_shares

    # ==================== КОНТРОЛЬНЫЕ СУММЫ ====================

    def verify_balance_integrity(self, trading_client: TradingClient) -> Tuple[bool, str]:
        """Проверить контрольные суммы.

        Returns:
            Tuple: (is_valid, message)
        """
        try:
            # Рассчитать виртуальный баланс
            active_investors = self._active_investors()
            if not active_investors:
                msg = "Balance check skipped: no active investors in registry"
                logging.info(msg)
                return True, msg

            virtual_total = 0.0
            for investor_name in active_investors:
                balance = self.calculate_investor_balance(investor_name)
                virtual_total += balance['total_value']

            # Получить реальный баланс
            account = trading_client.get_account()
            real_total = float(account.equity)

            # Проверить разницу (допуск $1)
            diff = abs(virtual_total - real_total)

            if diff > 1.0:
                msg = (
                    "Виртуальный баланс инвесторов не сходится с балансом счета. "
                    f"Virtual: ${virtual_total:,.2f}, Real equity: ${real_total:,.2f}, Diff: ${diff:,.2f}. "
                    "Проверьте registry, pending операции и trades.csv. Работа остановлена."
                )
                logging.error(msg)
                return False, msg

            msg = f"Balance verified: ${real_total:,.2f}"
            logging.info(msg)
            return True, msg

        except Exception as exc:
            msg = f"Error verifying balance: {str(exc)}"
            logging.error(msg)
            return False, msg

    # ==================== УТИЛИТЫ ====================

    def save_daily_snapshot(self, date: Optional[datetime] = None) -> None:
        """Сохранить ежедневный snapshot балансов.

        Args:
            date: Дата для snapshot
        """
        date = date or datetime.now(NY_TIMEZONE)

        for investor_name in self._active_investors():
            balance = self.calculate_investor_balance(investor_name)
            investor_path = self._get_investor_path(investor_name)
            snapshot_file = investor_path / 'balances_snapshot.csv'

            file_exists = snapshot_file.exists()

            try:
                with open(snapshot_file, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)

                    if not file_exists:
                        writer.writerow([
                            'date', 'account', 'cash', 'positions_value',
                            'total_value', 'pnl', 'cumulative_deposits',
                            'cumulative_withdrawals', 'hwm'
                        ])

                    for account in ['low', 'medium', 'high']:
                        account_data = balance[account]
                        writer.writerow([
                            date.strftime('%Y-%m-%d'),
                            account,
                            f"{account_data.get('cash', 0):.2f}",
                            f"{account_data.get('positions_value', 0):.2f}",
                            f"{account_data['total_value']:.2f}",
                            f"{account_data.get('pnl', 0):.2f}",
                            '0.00',  # TODO: рассчитать из operations.csv
                            '0.00',  # TODO: рассчитать из operations.csv
                            f"{self.investors[investor_name].high_watermark:.2f}"
                        ])

                logging.info(
                    "Saved daily snapshot for %s on %s",
                    investor_name,
                    date.strftime('%Y-%m-%d')
                )

            except Exception as exc:
                logging.error(
                    "Error saving snapshot for %s: %s",
                    investor_name, exc
                )

    def get_investor_summary(self, name: str) -> str:
        """Получить форматированную сводку по инвестору.

        Returns:
            str: HTML formatted summary
        """
        if not self.investor_exists(name):
            return f"❌ Investor '{name}' not found"

        investor = self.investors[name]
        balance = self.calculate_investor_balance(name)

        summary = f"<b>{name}</b>\n\n"
        summary += f"<b>Status:</b> {investor.status}\n"
        summary += f"<b>Created:</b> {investor.creation_date.strftime('%Y-%m-%d')}\n\n"

        summary += "<b>Accounts:</b>\n"
        for account in ['low', 'medium', 'high']:
            account_balance = balance[account]['total_value']
            summary += f"  • {account.upper()}: ${account_balance:,.2f}\n"

        summary += f"\n<b>Total:</b> ${balance['total_value']:,.2f}\n"

        if investor.fee_percent > 0:
            summary += f"<b>Fee:</b> {investor.fee_percent * 100:.1f}%\n"
            summary += f"<b>HWM:</b> ${investor.high_watermark:,.2f}\n"

        return summary
