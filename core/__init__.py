"""Core package with bot functions."""
from .telegram_logging import create_telegram_logging_handler
from .rebalance_flag import (
    NY_TIMEZONE,
    create_rebalance_flag_state,
    get_last_rebalance_date,
    has_rebalanced_today,
    write_flag,
    get_countdown_message
)
from .market_schedule import (
    create_market_schedule_state,
    get_current_ny_time,
    check_market_status,
    is_open,
    count_trading_days
)
from .portfolio_manager import (
    create_portfolio_manager_state,
    set_strategy,
    get_current_positions
)
from .alpaca_bot import (
    create_trading_bot_state,
    set_telegram_bot_state,
    start,
    stop,
    execute_rebalance,
    perform_rebalance,
    get_portfolio_status,
    get_trading_stats,
    get_settings,
    calculate_days_until_rebalance,
    get_next_rebalance_date,
    get_rebalance_preview
)
from .telegram_bot import (
    create_telegram_bot_state,
    setup_handlers,
    send_startup_message,
    send_daily_countdown,
    send_daily_countdown_sync,
    send_error_notification,
    send_error_notification_sync,
    send_rebalance_request,
    start as telegram_start,
    stop as telegram_stop
)
from .utils import retry_on_exception, telegram_handler, get_positions, run_sync
from .data_loader import load_market_data, clear_cache, get_snp500_tickers
from .investor_manager import (
    create_investor_manager_state,
    deposit,
    withdraw,
    process_pending_operations,
    check_and_calculate_fees,
    get_account_allocations,
    calculate_investor_balance,
    get_all_balances,
    distribute_trade_to_investors,
    verify_balance_integrity,
    save_daily_snapshot,
    get_investor_summary,
    investor_exists,
    get_investor_positions_for_account
)

__all__ = [
    # Telegram logging
    'create_telegram_logging_handler',
    # Rebalance flag
    'NY_TIMEZONE',
    'create_rebalance_flag_state',
    'get_last_rebalance_date',
    'has_rebalanced_today',
    'write_flag',
    'get_countdown_message',
    # Market schedule
    'create_market_schedule_state',
    'get_current_ny_time',
    'check_market_status',
    'is_open',
    'count_trading_days',
    # Portfolio manager
    'create_portfolio_manager_state',
    'set_strategy',
    'get_current_positions',
    # Trading bot
    'create_trading_bot_state',
    'set_telegram_bot_state',
    'start',
    'stop',
    'execute_rebalance',
    'perform_rebalance',
    'get_portfolio_status',
    'get_trading_stats',
    'get_settings',
    'calculate_days_until_rebalance',
    'get_next_rebalance_date',
    'get_rebalance_preview',
    # Telegram bot
    'telegram_start',
    'telegram_stop',
    'send_startup_message',
    'send_daily_countdown',
    'send_daily_countdown_sync',
    'send_error_notification',
    'send_error_notification_sync',
    'send_rebalance_request',
    # Utils
    'retry_on_exception',
    'telegram_handler',
    'get_positions',
    'run_sync',
    # Data loader
    'load_market_data',
    'clear_cache',
    'get_snp500_tickers',
    # Investor manager
    'create_investor_manager_state',
    'deposit',
    'withdraw',
    'process_pending_operations',
    'check_and_calculate_fees',
    'get_account_allocations',
    'calculate_investor_balance',
    'get_all_balances',
    'distribute_trade_to_investors',
    'verify_balance_integrity',
    'save_daily_snapshot',
    'get_investor_summary',
    'investor_exists',
    'get_investor_positions_for_account'
]
