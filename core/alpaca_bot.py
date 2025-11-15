"""Trading bot module with functional programming approach."""
import logging
import sys
from datetime import datetime, timedelta, time as dt_time
from typing import Any, Dict, Tuple, List

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

from config import (ENVIRONMENT, SNP500_TICKERS, CUSTOM_TICKERS, REBALANCE_INTERVAL_DAYS)
from .data_loader import get_snp500_tickers, load_market_data
from .rebalance_flag import NY_TIMEZONE
from .utils import run_sync


def create_trading_client(api_key: str, secret_key: str, paper: bool) -> TradingClient:
    """Factory for TradingClient with correct URL.

    Args:
        api_key: API key
        secret_key: Secret key
        paper: Paper trading flag

    Returns:
        TradingClient instance
    """
    url_override = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
    return TradingClient(
        api_key=api_key,
        secret_key=secret_key,
        paper=paper,
        url_override=url_override
    )


def resolve_tickers(tickers_mode: str) -> List[str]:
    """Choose ticker universe based on strategy configuration.

    Args:
        tickers_mode: Ticker mode ('snp500_only', 'all')

    Returns:
        List of tickers
    """
    if tickers_mode == 'snp500_only':
        # Maintain order while deduplicating
        combined = SNP500_TICKERS + CUSTOM_TICKERS
        return list(dict.fromkeys(combined))
    return get_snp500_tickers()


def create_trading_bot_state() -> Dict[str, Any]:
    """Create trading bot state dictionary.

    Returns:
        Trading bot state dictionary
    """
    load_dotenv()

    # Import strategy modules
    import strategies.paper_low as paper_low
    import strategies.paper_medium as paper_medium
    import strategies.paper_high as paper_high
    import strategies.live as live_strategy

    strategy_modules = {
        'paper_low': paper_low,
        'paper_medium': paper_medium,
        'paper_high': paper_high,
        'live': live_strategy
    }

    state = {
        'strategy_modules': strategy_modules,
        'strategies': {},
        'investor_manager_state': None,
        'market_schedule_state': None,
        'portfolio_manager_state': None,
        'rebalance_flag_state': None,
        'telegram_bot_state': None,
        'scheduler': BackgroundScheduler(),
        'awaiting_rebalance_confirmation': False
    }

    _initialize_strategies(state)

    # Initialize other components
    from core.market_schedule import create_market_schedule_state
    from core.portfolio_manager import create_portfolio_manager_state
    from core.rebalance_flag import create_rebalance_flag_state

    # Use first enabled strategy's client
    first_enabled = next((data for _, data in _iter_enabled_strategies(state)), None)
    if not first_enabled:
        logging.error("No enabled strategies configured!")
        sys.exit(1)

    first_client = first_enabled['client']
    state['market_schedule_state'] = create_market_schedule_state(first_client)
    state['portfolio_manager_state'] = create_portfolio_manager_state(
        trading_client=first_client,
        strategy_state=first_enabled.get('state')
    )
    state['rebalance_flag_state'] = create_rebalance_flag_state()

    return state


def _ensure_investor_manager(state: Dict[str, Any]) -> Any:
    """Lazy-create InvestorManager state.

    Args:
        state: Trading bot state

    Returns:
        InvestorManager state
    """
    if not state['investor_manager_state']:
        from core.investor_manager import create_investor_manager_state
        state['investor_manager_state'] = create_investor_manager_state('investors_registry.csv')
        logging.info("InvestorManager initialized")
    return state['investor_manager_state']


def _initialize_strategies(state: Dict[str, Any]) -> None:
    """Initialize all enabled trading strategies.

    Args:
        state: Trading bot state
    """
    strategy_modules = state['strategy_modules']

    for strategy_name, module in strategy_modules.items():
        if not module.ENABLED:
            logging.info("Strategy %s is disabled, skipping", strategy_name)
            continue

        try:
            api_key = module.API_KEY
            secret_key = module.SECRET_KEY
            paper = module.PAPER
            top_count = module.TOP_COUNT
            tickers_mode = module.TICKERS

            if not all([api_key, secret_key]):
                logging.error("Missing API keys for strategy %s", strategy_name)
                continue

            trading_client = create_trading_client(api_key, secret_key, paper)
            tickers = resolve_tickers(tickers_mode)

            # Create strategy state based on type
            if strategy_name == 'live':
                from strategies.live import create_live_strategy_state
                strategy_state = create_live_strategy_state(
                    trading_client=trading_client,
                    tickers=tickers,
                    top_count=top_count,
                    investor_manager=_ensure_investor_manager(state)
                )
            else:
                # Paper strategies
                from strategies.base import create_strategy_state
                strategy_state = create_strategy_state(
                    trading_client=trading_client,
                    tickers=tickers,
                    top_count=top_count
                )

            state['strategies'][strategy_name] = {
                'client': trading_client,
                'state': strategy_state,
                'enabled': True,
                'config': {
                    'paper': paper,
                    'top_count': top_count
                }
            }

            if strategy_name == 'live' and state['investor_manager_state']:
                state['strategies'][strategy_name]['investor_manager_state'] = state['investor_manager_state']

            logging.info("Strategy %s initialized successfully", strategy_name)

        except Exception as exc:
            logging.error(
                "Error initializing strategy %s: %s",
                strategy_name,
                exc,
                exc_info=True
            )


def _iter_enabled_strategies(state: Dict[str, Any]):
    """Yield (name, data) for enabled strategies only.

    Args:
        state: Trading bot state

    Yields:
        Tuple of (strategy_name, strategy_data)
    """
    for name, data in state['strategies'].items():
        if data.get('enabled'):
            yield name, data


def set_telegram_bot_state(state: Dict[str, Any], telegram_bot_state: Dict[str, Any]) -> None:
    """Set reference to Telegram bot state.

    Args:
        state: Trading bot state
        telegram_bot_state: Telegram bot state
    """
    state['telegram_bot_state'] = telegram_bot_state


def set_awaiting_rebalance_confirmation(state: Dict[str, Any], value: bool) -> None:
    """Set awaiting rebalance confirmation flag.

    Args:
        state: Trading bot state
        value: Flag value
    """
    state['awaiting_rebalance_confirmation'] = value


def check_market_status(state: Dict[str, Any]) -> Tuple[bool, str]:
    """Check market status.

    Args:
        state: Trading bot state

    Returns:
        Tuple of (is_open, reason)
    """
    from core.market_schedule import check_market_status as check_status
    return check_status(state['market_schedule_state'])


def _check_rebalance_conditions(state: Dict[str, Any]) -> bool:
    """Check if rebalance conditions are met.

    Args:
        state: Trading bot state

    Returns:
        True if all conditions are met, False otherwise
    """
    from core.rebalance_flag import has_rebalanced_today

    if has_rebalanced_today(state['rebalance_flag_state']):
        logging.info("Rebalancing already performed today.")
        return False

    is_open, reason = check_market_status(state)
    if not is_open:
        logging.info("Rebalancing postponed: %s", reason)
        return False

    # Check if trading days have passed since last rebalance
    days_until = calculate_days_until_rebalance(state)
    if days_until > 0:
        logging.info("Rebalancing not required. Days remaining: %d", days_until)
        return False

    return True


def execute_rebalance(state: Dict[str, Any]) -> None:
    """Execute portfolio rebalancing for all strategies.

    Args:
        state: Trading bot state
    """
    try:
        logging.info("Performing portfolio rebalancing for all strategies...")

        for strategy_name, strategy_data in _iter_enabled_strategies(state):
            try:
                logging.info("Rebalancing strategy: %s", strategy_name)

                # Import appropriate rebalance function
                if strategy_name == 'live':
                    from strategies.live import rebalance
                else:
                    from strategies.base import rebalance

                rebalance(strategy_data['state'])
                logging.info("Strategy %s rebalanced successfully", strategy_name)
            except Exception as exc:
                logging.error(
                    "Error rebalancing %s: %s",
                    strategy_name,
                    exc,
                    exc_info=True
                )

        from core.rebalance_flag import write_flag
        write_flag(state['rebalance_flag_state'])
        logging.info("All strategies rebalanced successfully")
    except Exception as exc:
        logging.error("Rebalance failed: %s", exc, exc_info=True)
        telegram_bot_state = state.get('telegram_bot_state')
        if telegram_bot_state:
            from core.telegram_bot import send_error_notification_sync
            send_error_notification_sync(
                telegram_bot_state,
                "Rebalancing Failed",
                f"Error during portfolio rebalancing:\\n<code>{str(exc)}</code>"
            )
        raise


def request_rebalance_confirmation_sync(state: Dict[str, Any]) -> None:
    """Request rebalance confirmation from admins (sync wrapper).

    Args:
        state: Trading bot state
    """
    telegram_bot_state = state.get('telegram_bot_state')
    if not telegram_bot_state:
        logging.warning("Telegram bot not available, executing rebalance directly")
        execute_rebalance(state)
        return

    try:
        from core.telegram_bot import send_rebalance_request
        run_sync(send_rebalance_request(telegram_bot_state), timeout=30)
    except Exception as exc:
        logging.error("Error requesting rebalance confirmation: %s", exc)
        # Fallback: execute rebalance anyway
        logging.info("Executing rebalance as fallback")
        execute_rebalance(state)


def perform_rebalance(state: Dict[str, Any]) -> None:
    """Perform portfolio rebalancing.

    Args:
        state: Trading bot state
    """
    if not _check_rebalance_conditions(state):
        return

    # In local environment, request confirmation; otherwise execute directly
    if ENVIRONMENT == "local":
        request_rebalance_confirmation_sync(state)
    else:
        execute_rebalance(state)


def perform_daily_task(state: Dict[str, Any]) -> None:
    """Perform daily task: send countdown and rebalance if needed.

    Args:
        state: Trading bot state
    """
    telegram_bot_state = state.get('telegram_bot_state')
    if telegram_bot_state:
        from core.telegram_bot import send_daily_countdown_sync
        send_daily_countdown_sync(telegram_bot_state)
    perform_rebalance(state)


def save_daily_investor_snapshots(state: Dict[str, Any]) -> None:
    """Save daily investor account snapshots.

    Args:
        state: Trading bot state
    """
    try:
        investor_manager_state = state.get('investor_manager_state')
        if investor_manager_state:
            from core.investor_manager import save_daily_snapshot
            now_ny = datetime.now(NY_TIMEZONE)
            save_daily_snapshot(investor_manager_state, now_ny)
            logging.info("Daily investor snapshots saved")
    except Exception as exc:
        logging.error("Error saving investor snapshots: %s", exc)


def start(state: Dict[str, Any]) -> None:
    """Start the bot.

    Args:
        state: Trading bot state
    """
    logging.info("=== Starting trading bot ===")
    is_open, reason = check_market_status(state)
    now_ny = datetime.now(NY_TIMEZONE)
    logging.info("Current time (NY): %s", now_ny.strftime('%Y-%m-%d %H:%M:%S %Z'))
    logging.info("Market status: %s%s",
                 'open' if is_open else 'closed',
                 f" (Reason: {reason})" if not is_open else "")

    # Pre-load market data
    try:
        logging.info("Pre-loading market data for all strategies...")
        load_market_data()
        logging.info("Market data pre-loaded successfully")
    except Exception as exc:
        logging.error("Error pre-loading market data: %s", exc, exc_info=True)

    scheduler = state['scheduler']
    if not scheduler.running:
        scheduler.start()
        scheduler.add_job(
            lambda: perform_daily_task(state),
            'cron',
            day_of_week='mon-fri',
            hour=10,
            minute=0,
            timezone=NY_TIMEZONE
        )
        # Add daily snapshot job for investors (after market close)
        if state['investor_manager_state']:
            scheduler.add_job(
                lambda: save_daily_investor_snapshots(state),
                'cron',
                hour=16,
                minute=30,
                timezone=NY_TIMEZONE,
                id='daily_investor_snapshots'
            )
            logging.info("Daily investor snapshot job scheduled")
    else:
        logging.info("Scheduler already running")

    if is_open:
        logging.info("Starting initial rebalancing...")
        perform_rebalance(state)


def stop(state: Dict[str, Any]) -> None:
    """Stop scheduler.

    Args:
        state: Trading bot state
    """
    scheduler = state['scheduler']
    if scheduler.running:
        scheduler.shutdown(wait=True)
        logging.info("Scheduler stopped")


def get_portfolio_status(state: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], float, float]:
    """Get detailed portfolio data from all strategies.

    Args:
        state: Trading bot state

    Returns:
        Tuple of (positions_by_strategy, total_portfolio_value, total_pnl)
    """
    try:
        positions_by_strategy = {}
        total_portfolio_value = 0.0
        total_pnl = 0.0

        for strategy_name, strategy_data in _iter_enabled_strategies(state):
            try:
                client = strategy_data['client']

                # Get positions
                all_positions = client.get_all_positions()
                positions = {pos.symbol: float(pos.qty) for pos in all_positions}

                # Get account
                account = client.get_account()
                portfolio_value = float(getattr(account, 'portfolio_value', 0))

                # Calculate P&L
                pnl = sum(float(getattr(pos, 'unrealized_pl', 0)) for pos in all_positions)

                positions_by_strategy[strategy_name] = {
                    'positions': positions,
                    'portfolio_value': portfolio_value,
                    'pnl': pnl,
                    'all_positions': {p.symbol: p for p in all_positions}
                }

                total_portfolio_value += portfolio_value
                total_pnl += pnl

            except Exception as exc:
                logging.error("Error retrieving data for %s: %s", strategy_name, exc)
                positions_by_strategy[strategy_name] = {
                    'positions': {},
                    'portfolio_value': 0.0,
                    'pnl': 0.0,
                    'all_positions': {}
                }

        return positions_by_strategy, total_portfolio_value, total_pnl

    except Exception as exc:
        logging.error("Error retrieving portfolio data: %s", exc)
        return {}, 0.0, 0.0


def get_trading_stats(state: Dict[str, Any]) -> Dict[str, float]:
    """Get real trading statistics from all strategies.

    Args:
        state: Trading bot state

    Returns:
        Aggregated trading statistics
    """
    try:
        total_trades_today = 0
        total_pnl = 0.0

        today = datetime.now(NY_TIMEZONE).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        for strategy_name, strategy_data in _iter_enabled_strategies(state):
            try:
                client = strategy_data['client']

                # Get trades for today
                request = GetOrdersRequest(
                    status=QueryOrderStatus.CLOSED,
                    after=today
                )
                trades = client.get_orders(filter=request)
                total_trades_today += len(trades)

                # Calculate P&L
                positions = client.get_all_positions()
                pnl = sum(float(getattr(pos, 'unrealized_pl', 0)) for pos in positions)
                total_pnl += pnl

            except Exception as exc:
                logging.error("Error retrieving stats for %s: %s", strategy_name, exc)

        return {
            "trades_today": total_trades_today,
            "pnl": total_pnl,
            "win_rate": 0.0  # Simplified version
        }
    except Exception as exc:
        logging.error("Error retrieving trading statistics: %s", exc)
        return {"trades_today": 0, "pnl": 0.0, "win_rate": 0.0}


def get_settings(state: Dict[str, Any]) -> Dict[str, Any]:
    """Get bot settings.

    Args:
        state: Trading bot state

    Returns:
        Settings dictionary
    """
    strategies_info = {}

    for strategy_name, strategy_data in _iter_enabled_strategies(state):
        config = strategy_data['config']
        strategies_info[strategy_name] = {
            'positions_count': config.get('top_count', 10),
            'mode': 'Paper Trading' if config.get('paper', True) else 'Live Trading',
            'enabled': True
        }

    return {
        "rebalance_time": "10:00 NY",
        "strategies": strategies_info
    }


def calculate_days_until_rebalance(state: Dict[str, Any]) -> int:
    """Calculate trading days until rebalancing.

    Args:
        state: Trading bot state

    Returns:
        Remaining trading days (0 if time to rebalance)
    """
    from core.rebalance_flag import get_last_rebalance_date
    from core.market_schedule import count_trading_days

    last_date = get_last_rebalance_date(state['rebalance_flag_state'])
    if last_date is None:
        return 0  # Time to rebalance if never done before

    today = datetime.now(NY_TIMEZONE)
    trading_days_passed = count_trading_days(last_date, today)

    return max(0, REBALANCE_INTERVAL_DAYS - trading_days_passed)


def get_next_rebalance_date(state: Dict[str, Any]) -> datetime:
    """Get the exact date of next rebalancing.

    Args:
        state: Trading bot state

    Returns:
        Next rebalance date in NY timezone
    """
    from core.rebalance_flag import get_last_rebalance_date

    last_date = get_last_rebalance_date(state['rebalance_flag_state'])
    if last_date is None:
        # If never rebalanced, next rebalance is today
        return datetime.now(NY_TIMEZONE)

    # Start from the last rebalance date and count forward trading days
    current = last_date.date()
    trading_days = (
        current + timedelta(days=i)
        for i in range(1, 365)
        if (current + timedelta(days=i)).weekday() < 5
    )
    next_date = next(
        d for idx, d in enumerate(trading_days)
        if idx == REBALANCE_INTERVAL_DAYS - 1
    )

    return NY_TIMEZONE.localize(datetime.combine(next_date, dt_time(10, 0)))


def calculate_total_close_value(positions_to_close: list, positions_dict: Dict[str, Any]) -> float:
    """Calculate total market value of positions to close.

    Args:
        positions_to_close: List of position symbols to close
        positions_dict: Dictionary of position objects keyed by symbol

    Returns:
        Total market value of positions to close
    """
    total_close_value = 0.0
    for symbol in positions_to_close:
        pos_info = positions_dict.get(symbol)
        if pos_info:
            market_value = float(getattr(pos_info, 'market_value', 0))
            total_close_value += market_value
    return total_close_value


def get_rebalance_preview(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Get a preview of what would happen in rebalancing (dry-run) for all strategies.

    Args:
        state: Trading bot state

    Returns:
        Rebalance plan for each strategy
    """
    previews = {}

    for strategy_name, strategy_data in _iter_enabled_strategies(state):
        client = strategy_data['client']
        strategy_state = strategy_data['state']

        try:
            # Get current positions
            all_positions = client.get_all_positions()
            current_positions = {pos.symbol: float(pos.qty) for pos in all_positions}
            positions_dict = {p.symbol: p for p in all_positions}

            # Get account
            account = client.get_account()
            available_cash = float(getattr(account, 'cash', 0))

            # Get top N by momentum
            if strategy_name == 'live':
                from strategies.live import get_signals
            else:
                from strategies.base import get_signals

            top_tickers = get_signals(strategy_state)

            # Calculate what would change
            positions_to_close = list(set(current_positions.keys()) - set(top_tickers))
            positions_to_open = list(set(top_tickers) - set(current_positions.keys()))

            # Calculate position size
            position_size = 0.0
            if positions_to_open:
                # Calculate total cash that will be available after closing positions
                total_close_value = calculate_total_close_value(positions_to_close, positions_dict)
                total_cash_after_close = available_cash + total_close_value
                if total_cash_after_close > 0:
                    position_size = total_cash_after_close / len(positions_to_open)

            previews[strategy_name] = {
                "current_positions": current_positions,
                "positions_dict": positions_dict,
                "top_tickers": top_tickers,
                "top_count": strategy_data['config'].get('top_count', 10),
                "positions_to_close": positions_to_close,
                "positions_to_open": positions_to_open,
                "available_cash": available_cash,
                "position_size": position_size
            }

        except Exception as exc:
            logging.error("Error previewing rebalance for %s: %s", strategy_name, exc)
            previews[strategy_name] = {
                "error": str(exc),
                "current_positions": {},
                "positions_dict": {},
                "top_tickers": [],
                "top_count": strategy_data['config'].get('top_count', 10),
                "positions_to_close": [],
                "positions_to_open": [],
                "available_cash": 0.0,
                "position_size": 0.0
            }

    return previews
