"""Momentum strategy for live account with investor management."""
import logging
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

import config
from core.data_loader import load_market_data
from core.utils import retry_on_exception, get_positions

# Strategy configuration constants
API_KEY = config.ALPACA_API_KEY_LIVE
SECRET_KEY = config.ALPACA_SECRET_KEY_LIVE
PAPER = True
TOP_COUNT = 50
ENABLED = True
TICKERS = 'all'  # SNP500 + MEDIUM + CUSTOM tickers


def get_config():
    """Get strategy configuration.

    Returns:
        dict: Strategy configuration
    """
    from strategies.base import create_strategy_config
    return create_strategy_config(
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        paper=PAPER,
        top_count=TOP_COUNT,
        enabled=ENABLED,
        tickers_mode=TICKERS
    )


def create_live_strategy_state(
    trading_client: TradingClient,
    tickers: List[str],
    top_count: int = 50,
    investor_manager: Optional[Any] = None
) -> Dict[str, Any]:
    """Create live strategy state dictionary.

    Args:
        trading_client: Alpaca API client
        tickers: List of tickers to analyze
        top_count: Number of top stocks to select
        investor_manager: InvestorManager state for investor operations

    Returns:
        Strategy state dictionary
    """
    return {
        'trading_client': trading_client,
        'data_client': StockHistoricalDataClient(API_KEY, SECRET_KEY),
        'tickers': tickers,
        'top_count': top_count,
        'investor_manager': investor_manager
    }


@retry_on_exception()
def get_signals(state: Dict[str, Any]) -> List[str]:
    """Get trading signals - top N stocks by momentum from state['tickers'] only.

    Args:
        state: Strategy state dictionary

    Returns:
        List of tickers with highest momentum
    """
    try:
        data = load_market_data()
    except Exception:
        raise

    if data is None or data.empty:  # type: ignore
        raise KeyError("'Close' column not found in data")
    if 'Close' not in data.columns.get_level_values(0):  # type: ignore
        raise KeyError("'Close' column not found in data")

    data = pd.DataFrame(data)  # type: ignore
    # Calculate momentum for all tickers: (last_price / first_price - 1)
    close_prices = data.xs('Close', level=0, axis=1)  # type: ignore
    momentum = (close_prices.iloc[-1] / close_prices.iloc[0] - 1)  # type: ignore

    # Filter to only tickers in state['tickers'], then get top_count
    momentum = pd.Series(momentum)  # type: ignore
    momentum_filtered = momentum[momentum.index.isin(state['tickers'])]
    return (momentum_filtered
            .nlargest(state['top_count'])  # type: ignore
            .index
            .tolist())


def close_positions(state: Dict[str, Any], positions: List[str]) -> None:
    """Close specified positions.

    Args:
        state: Strategy state dictionary
        positions: List of tickers to close
    """
    trading_client = state['trading_client']
    failed_closures = []

    for ticker in positions:
        try:
            trading_client.close_position(ticker)
            logging.info("Position %s closed", ticker)
        except Exception as exc:
            logging.error(
                "Error closing position %s: %s",
                ticker,
                exc,
                exc_info=True
            )
            failed_closures.append((ticker, str(exc)))

    if failed_closures:
        logging.warning(
            "Failed to close %d position(s): %s",
            len(failed_closures),
            [(t, e.split('\n')[0]) for t, e in failed_closures]
        )


def open_positions(
    state: Dict[str, Any],
    tickers: List[str],
    cash_per_position: float
) -> None:
    """Open new positions.

    Args:
        state: Strategy state dictionary
        tickers: List of tickers to open
        cash_per_position: Position size in dollars
    """
    trading_client = state['trading_client']
    failed_opens = []

    for ticker in tickers:
        try:
            order = MarketOrderRequest(
                symbol=ticker,
                notional=round(cash_per_position, 2),
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                time_in_force=TimeInForce.DAY
            )
            trading_client.submit_order(order)
            logging.info(
                "Opened position %s for $%.2f",
                ticker,
                cash_per_position
            )
        except Exception as exc:
            logging.error(
                "Error opening position %s: %s",
                ticker,
                exc,
                exc_info=True
            )
            failed_opens.append((ticker, str(exc)))

    if failed_opens:
        logging.warning(
            "Failed to open %d position(s): %s",
            len(failed_opens),
            [(t, e.split('\n')[0]) for t, e in failed_opens]
        )


def _get_account_tickers(account_name: str) -> List[str]:
    """Get tickers for specific account.

    Args:
        account_name: Account name ('low', 'medium', 'high')

    Returns:
        List of tickers for the account
    """
    if account_name == 'low':
        # Conservative: SNP500
        return config.SNP500_TICKERS[:100]
    elif account_name == 'medium':
        # Moderate: MEDIUM_TICKERS
        return config.MEDIUM_TICKERS
    else:  # high
        # Aggressive: HIGH_TICKERS
        return config.HIGH_TICKERS


def _calculate_signals(tickers: List[str], top_count: int) -> List[str]:
    """Calculate top N by momentum for list of tickers.

    Args:
        tickers: List of tickers to analyze
        top_count: Number of top stocks

    Returns:
        List of top tickers by momentum
    """
    try:
        data = load_market_data()
    except Exception as exc:
        logging.error("Error loading market data: %s", exc)
        return tickers[:top_count]  # Fallback

    if data is None or data.empty or 'Close' not in data.columns.get_level_values(0):  # type: ignore
        logging.warning("No data for signals calculation")
        return tickers[:top_count]

    data = pd.DataFrame(data)  # type: ignore
    try:
        # Calculate momentum for all tickers, but select only from provided tickers
        momentum = (data.xs('Close', level=0, axis=1)  # type: ignore
                    .dropna(axis='columns')  # type: ignore
                    .pct_change(periods=len(data)-1)  # type: ignore
                    .iloc[-1])  # type: ignore
        # Filter to only tickers in the provided list, then get top_count
        momentum = pd.Series(momentum)  # type: ignore
        momentum_filtered = momentum[momentum.index.isin(tickers)]
        return (momentum_filtered
                .nlargest(top_count)  # type: ignore
                .index
                .tolist())
    except Exception as exc:
        logging.error("Error calculating signals: %s", exc)
        return tickers[:top_count]


def _get_investor_positions(investor_manager_state: Any, account_name: str) -> List[str]:
    """Get current positions of account from trades.csv of investors.

    Args:
        investor_manager_state: InvestorManager state
        account_name: Account name

    Returns:
        List of position tickers
    """
    if not investor_manager_state:
        return []

    # Import here to avoid circular dependency
    from core.investor_manager import get_investor_positions_for_account
    return get_investor_positions_for_account(investor_manager_state, account_name)


def _close_account_positions(
    state: Dict[str, Any],
    account_name: str,
    positions: List[str]
) -> None:
    """Close positions for account.

    Args:
        state: Strategy state
        account_name: Account name
        positions: List of tickers to close
    """
    trading_client = state['trading_client']
    data_client = state['data_client']
    investor_manager = state.get('investor_manager')

    for ticker in positions:
        try:
            trading_client.close_position(ticker)
            logging.info(
                "Closed %s position from %s account",
                ticker, account_name
            )

            # Record SELL in trades.csv of investors
            if investor_manager:
                # Get current price
                try:
                    request = StockBarsRequest(
                        symbol_or_symbols=[ticker],
                        timeframe=TimeFrame.Minute,  # type: ignore
                        limit=1
                    )
                    bars = data_client.get_stock_bars(request)
                    price = float(bars[ticker][-1].close) if bars and ticker in bars else 0.0  # type: ignore
                except Exception:
                    price = 0.0

                # Get total shares for account
                positions_list = trading_client.get_all_positions()  # type: ignore
                total_shares = 0.0
                for pos in positions_list:
                    if pos.symbol == ticker:  # type: ignore
                        total_shares = float(pos.qty)  # type: ignore
                        break

                if total_shares > 0:
                    from core.investor_manager import distribute_trade_to_investors
                    distribute_trade_to_investors(
                        investor_manager,
                        account_name, 'SELL', ticker,
                        total_shares, price
                    )

        except Exception as exc:
            logging.error(
                "Error closing %s from %s: %s",
                ticker, account_name, exc
            )


def _open_account_positions(
    state: Dict[str, Any],
    account_name: str,
    tickers: List[str],
    cash_per_position: float
) -> None:
    """Open new positions for account.

    Args:
        state: Strategy state
        account_name: Account name
        tickers: List of tickers to open
        cash_per_position: Position size in dollars
    """
    trading_client = state['trading_client']
    investor_manager = state.get('investor_manager')
    failed_opens = []

    for ticker in tickers:
        try:
            order = MarketOrderRequest(
                symbol=ticker,
                notional=round(cash_per_position, 2),
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                time_in_force=TimeInForce.DAY
            )
            order_response = trading_client.submit_order(order)
            logging.info(
                "Opened %s in %s account for $%.2f",
                ticker, account_name, cash_per_position
            )

            # Record BUY in trades.csv of investors
            if investor_manager:
                # Wait for execution and get real price
                price = cash_per_position
                shares = 1.0
                if order_response and order_response.id:  # type: ignore
                    try:
                        max_attempts = 10
                        for _ in range(max_attempts):
                            order_status = trading_client.get_order_by_id(order_response.id)  # type: ignore
                            if order_status and order_status.filled_avg_price:  # type: ignore
                                price = float(order_status.filled_avg_price)  # type: ignore
                                shares = float(order_status.filled_qty or 1)  # type: ignore
                                break
                            time.sleep(0.5)
                    except Exception:
                        pass

                if shares > 0:
                    from core.investor_manager import distribute_trade_to_investors
                    distribute_trade_to_investors(
                        investor_manager,
                        account_name, 'BUY', ticker,
                        shares, price
                    )

        except Exception as exc:
            logging.error(
                "Error opening %s in %s: %s",
                ticker, account_name, exc
            )
            failed_opens.append((ticker, str(exc)))

    if failed_opens:
        logging.warning(
            "Failed to open %d position(s) in %s: %s",
            len(failed_opens),
            account_name,
            [(t, e.split('\n')[0]) for t, e in failed_opens]
        )


def rebalance(state: Dict[str, Any]) -> None:
    """Rebalance portfolio with investor accounts.

    Args:
        state: Strategy state dictionary
    """
    try:
        logging.info("Starting LiveStrategy portfolio rebalancing with investors")
        trading_client = state['trading_client']
        investor_manager = state.get('investor_manager')
        top_count = state['top_count']

        # 1. Process pending operations
        if investor_manager:
            logging.info("Processing pending investor operations")
            from core.investor_manager import process_pending_operations
            pending_results = process_pending_operations(
                investor_manager,
                trading_client
            )
            logging.info(
                "Processed %d pending operations",
                pending_results.get('processed', 0)
            )

        # 2. Get capital allocation by accounts
        if investor_manager:
            from core.investor_manager import get_account_allocations
            allocations = get_account_allocations(investor_manager)
        else:
            # Fallback without investor_manager
            account_info = trading_client.get_account()
            total_equity = float(getattr(account_info, 'equity', 0))
            allocations = {
                'low': {'total': total_equity * 0.45},
                'medium': {'total': total_equity * 0.35},
                'high': {'total': total_equity * 0.20}
            }

        # 3. Rebalance each virtual account
        for account_name in ['low', 'medium', 'high']:
            account_capital = allocations[account_name]['total']

            if account_capital <= 0:
                logging.info("No capital in %s account, skipping", account_name)
                continue

            logging.info(
                "Rebalancing %s account with capital $%.2f",
                account_name, account_capital
            )

            # Get tickers for account
            account_tickers = _get_account_tickers(account_name)

            # Calculate top N by momentum
            top_tickers = _calculate_signals(account_tickers, top_count)
            logging.info(
                "Top %d stocks for %s: %s",
                top_count, account_name, ', '.join(top_tickers[:5])
            )

            # Get current positions (from trades.csv of investors if available)
            if investor_manager:
                current_positions = _get_investor_positions(investor_manager, account_name)
            else:
                current_positions = get_positions(trading_client)

            # Determine which positions to close and open
            top_tickers_set = set(top_tickers)
            current_positions_set = set(current_positions)

            positions_to_close = list(current_positions_set - top_tickers_set)
            positions_to_open = list(top_tickers_set - current_positions_set)

            logging.info(
                "Account %s: close %d, open %d positions",
                account_name, len(positions_to_close), len(positions_to_open)
            )

            # Close unneeded positions
            if positions_to_close:
                _close_account_positions(state, account_name, positions_to_close)
                time.sleep(2)

            # Open new positions
            if positions_to_open:
                position_size = account_capital / len(positions_to_open)
                if position_size < 1:
                    logging.warning(
                        "Position size too small for %s: $%.2f",
                        account_name, position_size
                    )
                    continue

                _open_account_positions(
                    state, account_name, positions_to_open, position_size
                )

        # 4. Verify balance integrity
        if investor_manager:
            from core.investor_manager import verify_balance_integrity
            is_valid, msg = verify_balance_integrity(
                investor_manager,
                trading_client
            )
            if not is_valid:
                logging.error("Balance integrity check failed: %s", msg)
                raise ValueError(msg)

        # 5. Save snapshot
        if investor_manager:
            import pytz
            from core.investor_manager import save_daily_snapshot
            ny_tz = pytz.timezone('America/New_York')
            save_daily_snapshot(
                investor_manager,
                datetime.now(ny_tz)
            )

        logging.info("LiveStrategy portfolio rebalancing completed successfully")

    except Exception as exc:
        logging.error("Error during rebalancing: %s", exc, exc_info=True)
        raise
