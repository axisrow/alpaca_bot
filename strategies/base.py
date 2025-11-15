"""Base momentum strategy module with functional programming approach."""
import logging
import time
from typing import List, Dict, Any, cast

import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from core.data_loader import load_market_data
from core.utils import retry_on_exception, get_positions


# Strategy configuration type
StrategyConfig = Dict[str, Any]


def create_strategy_config(
    api_key: str,
    secret_key: str,
    paper: bool = True,
    top_count: int = 50,
    enabled: bool = True,
    tickers_mode: str = 'snp500_only'
) -> StrategyConfig:
    """Create strategy configuration dictionary.

    Args:
        api_key: Alpaca API key
        secret_key: Alpaca secret key
        paper: Paper trading flag
        top_count: Number of top stocks to hold
        enabled: Strategy enabled flag
        tickers_mode: Ticker universe mode

    Returns:
        Strategy configuration dictionary
    """
    return {
        'api_key': api_key,
        'secret_key': secret_key,
        'paper': paper,
        'top_count': top_count,
        'enabled': enabled,
        'tickers_mode': tickers_mode
    }


def create_strategy_state(
    trading_client: TradingClient,
    tickers: List[str],
    top_count: int = 50
) -> Dict[str, Any]:
    """Create strategy state dictionary.

    Args:
        trading_client: Alpaca API client
        tickers: List of tickers to analyze
        top_count: Number of top stocks to select

    Returns:
        Strategy state dictionary
    """
    return {
        'trading_client': trading_client,
        'tickers': tickers,
        'top_count': top_count
    }


@retry_on_exception()
def get_signals(state: Dict[str, Any]) -> List[str]:
    """Get trading signals - top N stocks by momentum.

    Args:
        state: Strategy state dictionary

    Returns:
        List of tickers with highest momentum
    """
    data = load_market_data()

    if data is None or data.empty:  # type: ignore[union-attr]
        raise KeyError("'Close' column not found in data")
    if 'Close' not in data.columns.get_level_values(0):  # type: ignore[attr-defined]
        raise KeyError("'Close' column not found in data")

    data = cast(pd.DataFrame, data)  # type: ignore[assignment]
    # Calculate momentum for all tickers: (last_price / first_price - 1)
    close_prices = data.xs('Close', level=0, axis=1)  # type: ignore[attr-defined]
    momentum = close_prices.iloc[-1] / close_prices.iloc[0] - 1  # type: ignore[attr-defined]

    # Cast to Series for type safety
    momentum = cast(pd.Series, momentum)  # type: ignore[assignment]

    # Filter to only tickers in state['tickers'], then get top_count
    momentum_filtered = momentum[momentum.index.isin(state['tickers'])]
    return (momentum_filtered
            .nlargest(state['top_count'])  # type: ignore[attr-defined]
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
        except Exception as exc:  # pylint: disable=broad-exception-caught
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
        except Exception as exc:  # pylint: disable=broad-exception-caught
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


def rebalance(state: Dict[str, Any]) -> None:
    """Rebalance portfolio.

    Args:
        state: Strategy state dictionary
    """
    try:
        logging.info("Starting portfolio rebalancing")

        # Get trading strategy signals
        top_tickers = get_signals(state)
        logging.info("Top %d stocks by momentum: %s", state['top_count'], ', '.join(top_tickers))

        # Get current positions
        current_positions = get_positions(state['trading_client'])
        logging.info("Current positions: %s", current_positions)

        # Determine positions to close and open
        top_tickers_set = set(top_tickers)
        current_positions_set = set(current_positions)

        positions_to_close = list(current_positions_set - top_tickers_set)
        positions_to_open = list(top_tickers_set - current_positions_set)

        logging.info("Positions to close: %s", positions_to_close)
        logging.info("Positions to open: %s", positions_to_open)

        # Close unneeded positions
        if positions_to_close:
            close_positions(state, positions_to_close)
            time.sleep(5)

        # Open new positions
        if positions_to_open:
            account = state['trading_client'].get_account()  # type: ignore[no-untyped-call]
            cash_value = getattr(account, 'cash', 0.0)  # type: ignore[attr-defined]
            available_cash = float(cast(float, cash_value))  # type: ignore[arg-type]
            if available_cash <= 0:
                logging.warning("Insufficient funds: $%.2f", available_cash)
                return

            position_size = available_cash / len(positions_to_open)
            if position_size < 1:
                logging.warning(
                    "Position size too small: $%.2f",
                    position_size
                )
                return

            open_positions(state, positions_to_open, position_size)

        logging.info("Portfolio rebalancing completed successfully")

    except Exception as exc:  # pylint: disable=broad-exception-caught
        logging.error("Error during rebalancing: %s", exc, exc_info=True)
