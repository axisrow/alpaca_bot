"""Investor management module with functional programming approach."""
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict

import pytz
from alpaca.trading.client import TradingClient

NY_TIMEZONE = pytz.timezone('America/New_York')

# Default allocation
DEFAULT_ALLOCATION = {'low': 0.45, 'medium': 0.35, 'high': 0.20}


def create_investor(
    name: str,
    creation_date: datetime,
    fee_percent: float,
    is_fee_receiver: bool,
    high_watermark: float,
    last_fee_date: datetime,
    status: str
) -> Dict[str, Any]:
    """Create investor dictionary.

    Args:
        name: Investor name
        creation_date: Creation date
        fee_percent: Fee percentage (e.g., 0.2 for 20%)
        is_fee_receiver: Whether this investor receives fees
        high_watermark: High watermark value
        last_fee_date: Last fee calculation date
        status: Status (active, inactive)

    Returns:
        Investor dictionary
    """
    return {
        'name': name,
        'creation_date': creation_date,
        'fee_percent': fee_percent,
        'is_fee_receiver': is_fee_receiver,
        'high_watermark': high_watermark,
        'last_fee_date': last_fee_date,
        'status': status
    }


def create_investor_manager_state(registry_path: str = 'investors_registry.csv') -> Dict[str, Any]:
    """Create investor manager state dictionary.

    Args:
        registry_path: Path to investor registry CSV file

    Returns:
        Investor manager state dictionary
    """
    state = {
        'registry_path': Path(registry_path),
        'investors_dir': Path('data/investors'),
        'investors': {},
        'ny_timezone': NY_TIMEZONE
    }

    _load_registry(state)
    _ensure_investor_directories(state)

    return state


def _load_registry(state: Dict[str, Any]) -> None:
    """Load investor registry from CSV.

    Args:
        state: Investor manager state
    """
    registry_path = state['registry_path']
    if not registry_path.exists():
        logging.warning("Registry file not found: %s", registry_path)
        return

    try:
        with open(registry_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                investor = create_investor(
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
                state['investors'][investor['name']] = investor

        logging.info("Loaded %d investors from registry", len(state['investors']))
    except Exception as exc:
        logging.error("Error loading registry: %s", exc)


def _ensure_investor_directories(state: Dict[str, Any]) -> None:
    """Create directories for all investors.

    Args:
        state: Investor manager state
    """
    investors_dir = state['investors_dir']
    investors_dir.mkdir(parents=True, exist_ok=True)
    for investor_name in state['investors']:
        investor_path = _get_investor_path(state, investor_name)
        investor_path.mkdir(parents=True, exist_ok=True)


def _get_investor_path(state: Dict[str, Any], name: str) -> Path:
    """Get path to investor directory.

    Args:
        state: Investor manager state
        name: Investor name

    Returns:
        Path to investor directory
    """
    return state['investors_dir'] / name


def investor_exists(state: Dict[str, Any], name: str) -> bool:
    """Check if investor exists.

    Args:
        state: Investor manager state
        name: Investor name

    Returns:
        True if investor exists, False otherwise
    """
    return name in state['investors']


# ==================== OPERATIONS ====================

def deposit(
    state: Dict[str, Any],
    name: str,
    amount: float,
    account: Optional[str] = None,
    date: Optional[datetime] = None
) -> List[str]:
    """Create pending deposit operation.

    Args:
        state: Investor manager state
        name: Investor name
        amount: Deposit amount
        account: Specific account or None for default allocation
        date: Operation date

    Returns:
        List of operation IDs
    """
    if not investor_exists(state, name):
        raise ValueError(f"Investor '{name}' not found")

    date = date or datetime.now(NY_TIMEZONE)
    operation_ids = []

    if account:
        # Deposit to specific account
        if account not in DEFAULT_ALLOCATION:
            raise ValueError(f"Invalid account: {account}")

        operation_id = _create_operation(state, name, 'deposit', account, amount, date)
        operation_ids.append(operation_id)
        logging.info(
            "Created deposit operation for %s: %s account, $%.2f",
            name, account, amount
        )
    else:
        # Default allocation
        for acc, percentage in DEFAULT_ALLOCATION.items():
            dep_amount = amount * percentage
            operation_id = _create_operation(state, name, 'deposit', acc, dep_amount, date)
            operation_ids.append(operation_id)
            logging.info(
                "Created deposit operation for %s: %s account, $%.2f",
                name, acc, dep_amount
            )

    return operation_ids


def withdraw(
    state: Dict[str, Any],
    name: str,
    amount: float,
    account: Optional[str] = None,
    date: Optional[datetime] = None
) -> List[str]:
    """Create pending withdrawal operation.

    Args:
        state: Investor manager state
        name: Investor name
        amount: Withdrawal amount
        account: Specific account or None for proportional withdrawal
        date: Operation date

    Returns:
        List of operation IDs
    """
    if not investor_exists(state, name):
        raise ValueError(f"Investor '{name}' not found")

    date = date or datetime.now(NY_TIMEZONE)
    operation_ids = []

    if account:
        # Withdraw from specific account
        if account not in DEFAULT_ALLOCATION:
            raise ValueError(f"Invalid account: {account}")

        # Check balance
        balance = calculate_investor_balance(state, name)
        available = balance[account]['total_value']
        if amount > available:
            raise ValueError(
                f"Insufficient balance on {account}: "
                f"${available:.2f} < ${amount:.2f}"
            )

        operation_id = _create_operation(state, name, 'withdraw', account, amount, date)
        operation_ids.append(operation_id)
        logging.info(
            "Created withdrawal operation for %s: %s account, $%.2f",
            name, account, amount
        )
    else:
        # Proportional withdrawal
        balance = calculate_investor_balance(state, name)
        total_balance = balance['total_value']

        if amount > total_balance:
            raise ValueError(
                f"Insufficient total balance: "
                f"${total_balance:.2f} < ${amount:.2f}"
            )

        for acc, percentage in DEFAULT_ALLOCATION.items():
            withdraw_amount = amount * percentage
            operation_id = _create_operation(state, name, 'withdraw', acc, withdraw_amount, date)
            operation_ids.append(operation_id)
            logging.info(
                "Created withdrawal operation for %s: %s account, $%.2f",
                name, acc, withdraw_amount
            )

    return operation_ids


def _create_operation(
    state: Dict[str, Any],
    investor: str,
    operation_type: str,
    account: str,
    amount: float,
    date: datetime
) -> str:
    """Create operation in investor's operations.csv file.

    Args:
        state: Investor manager state
        investor: Investor name
        operation_type: Operation type (deposit, withdraw, fee)
        account: Account name
        amount: Amount
        date: Operation date

    Returns:
        Operation ID
    """
    investor_path = _get_investor_path(state, investor)
    operations_file = investor_path / 'operations.csv'

    # Generate operation_id
    operation_id = f"{date.strftime('%Y%m%d_%H%M%S')}_{account}"

    # Prepare data
    timestamp = date.strftime('%Y-%m-%d %H:%M:%S')
    status = 'pending'
    balance_after = 0  # Will be updated during process_pending_operations

    # Check if file exists
    file_exists = operations_file.exists()

    try:
        with open(operations_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            # Write header if new file
            if not file_exists:
                writer.writerow([
                    'date', 'timestamp', 'operation', 'account',
                    'amount', 'status', 'balance_after', 'notes'
                ])

            # Write operation row
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

        logging.info("Operation %s created for %s", operation_id, investor)
        return operation_id

    except Exception as exc:
        logging.error("Error creating operation for %s: %s", investor, exc)
        raise


# ==================== PROCESSING OPERATIONS ====================

def process_pending_operations(
    state: Dict[str, Any],
    trading_client: TradingClient
) -> Dict:
    """Process all pending operations during rebalancing.

    Args:
        state: Investor manager state
        trading_client: Alpaca trading client

    Returns:
        Results dictionary
    """
    results = {
        'processed': 0,
        'completed': [],
        'failed': []
    }

    for investor_name in state['investors']:
        investor_results = _process_investor_pending_ops(state, investor_name, trading_client)
        results['processed'] += investor_results['processed']
        results['completed'].extend(investor_results['completed'])
        results['failed'].extend(investor_results['failed'])

    logging.info(
        "Processed pending operations: %d completed, %d failed",
        len(results['completed']),
        len(results['failed'])
    )

    return results


def _process_investor_pending_ops(
    state: Dict[str, Any],
    investor: str,
    trading_client: TradingClient
) -> Dict:
    """Process pending operations for one investor.

    Args:
        state: Investor manager state
        investor: Investor name
        trading_client: Trading client

    Returns:
        Results dictionary
    """
    investor_path = _get_investor_path(state, investor)
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
                    # Update status to completed
                    row['status'] = 'completed'
                    row['balance_after'] = _calculate_account_balance(
                        state, investor, row['account']
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

        # Rewrite file with updated statuses
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


def _calculate_account_balance(state: Dict[str, Any], investor: str, account: str) -> float:
    """Calculate current account balance.

    Args:
        state: Investor manager state
        investor: Investor name
        account: Account name

    Returns:
        Current balance
    """
    investor_path = _get_investor_path(state, investor)
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


# ==================== CALCULATIONS ====================

def check_and_calculate_fees(
    state: Dict[str, Any],
    at_rebalance: bool = True,
    for_investor: Optional[str] = None
) -> Dict:
    """Check HWM and calculate fees.

    Args:
        state: Investor manager state
        at_rebalance: True if called during monthly rebalance
        for_investor: Specific investor name or None for all

    Returns:
        Dictionary mapping investor name to fee amount
    """
    fees = {}
    now = datetime.now(tz=NY_TIMEZONE)

    investors_to_check = (
        [for_investor] if for_investor else state['investors'].keys()
    )

    for investor_name in investors_to_check:
        if investor_name not in state['investors']:
            continue

        investor = state['investors'][investor_name]

        # Skip if investor receives fees (manager)
        if investor['is_fee_receiver']:
            continue

        # Check fee calculation condition
        should_calculate_fee = False
        if at_rebalance:
            # Monthly calculation: check if month has passed since last fee
            last_fee = investor['last_fee_date']
            months_passed = (now.year - last_fee.year) * 12 + (now.month - last_fee.month)
            if months_passed >= 1:
                should_calculate_fee = True
        else:
            # On withdrawal/closure: always calculate fee
            should_calculate_fee = True

        if not should_calculate_fee:
            continue

        # Calculate current balance
        current_balance = calculate_investor_balance(state, investor_name)
        current_value = current_balance['total_value']

        # Check HWM
        if current_value > investor['high_watermark']:
            profit = current_value - investor['high_watermark']
            fee = profit * investor['fee_percent']

            if fee > 0:
                fees[investor_name] = fee
                logging.info(
                    "Fee for %s: $%.2f (profit: $%.2f, rate: %.1f%%, at_rebalance=%s)",
                    investor_name, fee, profit, investor['fee_percent'] * 100, at_rebalance
                )

                # Update last fee date only for monthly calculation
                if at_rebalance:
                    investor['last_fee_date'] = now

                # Update HWM in any case
                investor['high_watermark'] = current_value

    return fees


def get_account_allocations(state: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """Get capital allocation by accounts.

    Args:
        state: Investor manager state

    Returns:
        Dictionary mapping account to investor balances
    """
    allocations = {
        'low': defaultdict(float),
        'medium': defaultdict(float),
        'high': defaultdict(float)
    }

    for investor_name in state['investors']:
        balance = calculate_investor_balance(state, investor_name)

        for account in ['low', 'medium', 'high']:
            account_balance = balance[account]['total_value']
            allocations[account][investor_name] = account_balance

    # Add totals
    for account in ['low', 'medium', 'high']:
        allocations[account]['total'] = sum(
            v for k, v in allocations[account].items() if k != 'total'
        )

    return allocations


def calculate_investor_balance(state: Dict[str, Any], name: str) -> Dict:
    """Calculate investor balance across all accounts.

    Args:
        state: Investor manager state
        name: Investor name

    Returns:
        Balance dictionary
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

    # Calculate each account
    for account in ['low', 'medium', 'high']:
        account_balance = _calculate_account_balance(state, name, account)
        balance[account]['total_value'] = account_balance
        balance['total_value'] += account_balance

    return balance


def get_all_balances(state: Dict[str, Any]) -> Dict:
    """Get balances for all investors.

    Args:
        state: Investor manager state

    Returns:
        Dictionary mapping investor name to balance info
    """
    balances = {}

    for investor_name in state['investors']:
        balance = calculate_investor_balance(state, investor_name)
        balances[investor_name] = {
            'total_value': balance['total_value'],
            'pnl': 0.0,  # TODO: calculate P&L from trades.csv
            'accounts': balance
        }

    return balances


# ==================== TRADE HISTORY ====================

def distribute_trade_to_investors(
    state: Dict[str, Any],
    account: str,
    action: str,
    ticker: str,
    total_shares: float,
    price: float
) -> None:
    """Distribute trade to investors proportionally.

    Args:
        state: Investor manager state
        account: Account name (low/medium/high)
        action: BUY or SELL
        ticker: Ticker symbol
        total_shares: Total number of shares
        price: Price per share
    """
    # Get capital allocation
    allocations = get_account_allocations(state)
    account_allocations = allocations[account]
    total_capital = account_allocations['total']

    if total_capital <= 0:
        logging.warning(
            "No capital in %s account, skipping trade distribution",
            account
        )
        return

    # Distribute to investors proportionally
    for investor_name in state['investors']:
        investor_capital = account_allocations.get(investor_name, 0.0)

        if investor_capital <= 0:
            continue

        # Calculate investor's share
        share = investor_capital / total_capital
        investor_shares = total_shares * share

        # Record trade
        _record_trade(
            state, investor_name, account, action,
            ticker, investor_shares, price
        )


def _record_trade(
    state: Dict[str, Any],
    investor: str,
    account: str,
    action: str,
    ticker: str,
    shares: float,
    price: float
) -> None:
    """Record trade in investor's trades.csv.

    Args:
        state: Investor manager state
        investor: Investor name
        account: Account name
        action: BUY or SELL
        ticker: Ticker symbol
        shares: Number of shares
        price: Price per share
    """
    investor_path = _get_investor_path(state, investor)
    trades_file = investor_path / 'trades.csv'

    # Calculate amount and total_shares_after
    amount = shares * price
    total_shares_after = _get_total_investor_shares(state, investor, account, ticker)

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
        logging.error("Error recording trade for %s: %s", investor, exc)


def _get_total_investor_shares(
    state: Dict[str, Any],
    investor: str,
    account: str,
    ticker: str
) -> float:
    """Get current number of shares for investor.

    Args:
        state: Investor manager state
        investor: Investor name
        account: Account name
        ticker: Ticker symbol

    Returns:
        Total shares
    """
    investor_path = _get_investor_path(state, investor)
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


def get_investor_positions_for_account(state: Dict[str, Any], account_name: str) -> List[str]:
    """Get current positions for account from trades.csv of investors.

    Args:
        state: Investor manager state
        account_name: Account name

    Returns:
        List of ticker symbols with positions
    """
    positions = set()
    for investor_name in state['investors']:
        investor_path = _get_investor_path(state, investor_name)
        trades_file = investor_path / 'trades.csv'

        if not trades_file.exists():
            continue

        try:
            with open(trades_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('account') == account_name:
                        if float(row.get('total_shares_after', 0)) > 0:
                            positions.add(row['ticker'])
        except Exception as exc:
            logging.error(
                "Error reading trades for %s: %s",
                investor_name, exc
            )

    return list(positions)


# ==================== BALANCE VERIFICATION ====================

def verify_balance_integrity(
    state: Dict[str, Any],
    trading_client: TradingClient
) -> Tuple[bool, str]:
    """Verify balance integrity (checksums).

    Args:
        state: Investor manager state
        trading_client: Trading client

    Returns:
        Tuple of (is_valid, message)
    """
    try:
        # Calculate virtual balance
        virtual_total = 0.0
        for investor_name in state['investors']:
            balance = calculate_investor_balance(state, investor_name)
            virtual_total += balance['total_value']

        # Get real balance
        account = trading_client.get_account()
        real_total = float(account.equity)

        # Check difference (tolerance $1)
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


# ==================== UTILITIES ====================

def save_daily_snapshot(state: Dict[str, Any], date: Optional[datetime] = None) -> None:
    """Save daily balance snapshot.

    Args:
        state: Investor manager state
        date: Snapshot date
    """
    date = date or datetime.now(NY_TIMEZONE)

    for investor_name in state['investors']:
        balance = calculate_investor_balance(state, investor_name)
        investor_path = _get_investor_path(state, investor_name)
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
                    investor = state['investors'][investor_name]
                    writer.writerow([
                        date.strftime('%Y-%m-%d'),
                        account,
                        f"{account_data.get('cash', 0):.2f}",
                        f"{account_data.get('positions_value', 0):.2f}",
                        f"{account_data['total_value']:.2f}",
                        f"{account_data.get('pnl', 0):.2f}",
                        '0.00',  # TODO: calculate from operations.csv
                        '0.00',  # TODO: calculate from operations.csv
                        f"{investor['high_watermark']:.2f}"
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


def get_investor_summary(state: Dict[str, Any], name: str) -> str:
    """Get formatted investor summary.

    Args:
        state: Investor manager state
        name: Investor name

    Returns:
        HTML formatted summary
    """
    if not investor_exists(state, name):
        return f"❌ Investor '{name}' not found"

    investor = state['investors'][name]
    balance = calculate_investor_balance(state, name)

    summary = f"<b>{name}</b>\n\n"
    summary += f"<b>Status:</b> {investor['status']}\n"
    summary += f"<b>Created:</b> {investor['creation_date'].strftime('%Y-%m-%d')}\n\n"

    summary += "<b>Accounts:</b>\n"
    for account in ['low', 'medium', 'high']:
        account_balance = balance[account]['total_value']
        summary += f"  • {account.upper()}: ${account_balance:,.2f}\n"

    summary += f"\n<b>Total:</b> ${balance['total_value']:,.2f}\n"

    if investor['fee_percent'] > 0:
        summary += f"<b>Fee:</b> {investor['fee_percent'] * 100:.1f}%\n"
        summary += f"<b>HWM:</b> ${investor['high_watermark']:,.2f}\n"

    return summary
