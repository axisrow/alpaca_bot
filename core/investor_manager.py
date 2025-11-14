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

    def process_pending_operations(self, trading_client: TradingClient) -> Dict:
        """Обработать все pending операции при ребалансировке.

        Args:
            trading_client: Alpaca trading client

        Returns:
            Dict: Результаты обработки
        """
        results = {
            'processed': 0,
            'completed': [],
            'failed': []
        }

        for investor_name in self.investors:
            investor_results = self._process_investor_pending_ops(
                investor_name, trading_client
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

    def _process_investor_pending_ops(self, investor: str,
                                      trading_client: TradingClient) -> Dict:
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
        """Рассчитать текущий баланс счета."""
        investor_path = self._get_investor_path(investor)
        operations_file = investor_path / 'operations.csv'

        balance = 0.0

        if not operations_file.exists():
            return balance

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
                "Error calculating balance for %s:%s - %s",
                investor, account, exc
            )

        return balance

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

                    # Обновить HWM в любом случае
                    investor.high_watermark = current_value

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

        for investor_name in self.investors:
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
            account_balance = self._calculate_account_balance(name, account)
            balance[account]['total_value'] = account_balance
            balance['total_value'] += account_balance

        return balance

    def get_all_balances(self) -> Dict:
        """Получить балансы всех инвесторов."""
        balances = {}

        for investor_name in self.investors:
            balance = self.calculate_investor_balance(investor_name)
            balances[investor_name] = {
                'total_value': balance['total_value'],
                'pnl': 0.0,  # TODO: рассчитать PnL из trades.csv
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
        for investor_name in self.investors:
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
            virtual_total = 0.0
            for investor_name in self.investors:
                balance = self.calculate_investor_balance(investor_name)
                virtual_total += balance['total_value']

            # Получить реальный баланс
            account = trading_client.get_account()
            real_total = float(account.equity)

            # Проверить разницу (допуск $1)
            diff = abs(virtual_total - real_total)

            if diff > 1.0:
                msg = (
                    f"Balance mismatch! Virtual: ${virtual_total:,.2f}, "
                    f"Real: ${real_total:,.2f}, Diff: ${diff:,.2f}"
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

        for investor_name in self.investors:
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
