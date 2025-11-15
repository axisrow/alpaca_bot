"""Portfolio manager module with functional programming approach."""
import logging
from typing import Any, Dict

from alpaca.trading.client import TradingClient


def create_portfolio_manager_state(
    trading_client: TradingClient,
    strategy_state: Any = None
) -> Dict[str, Any]:
    """Create portfolio manager state dictionary.

    Args:
        trading_client: Alpaca API client
        strategy_state: Optional strategy state

    Returns:
        Portfolio manager state dictionary
    """
    return {
        'trading_client': trading_client,
        'strategy_state': strategy_state
    }


def set_strategy(state: Dict[str, Any], strategy_state: Any) -> None:
    """Attach or update the active strategy reference.

    Args:
        state: Portfolio manager state
        strategy_state: Strategy state to attach
    """
    state['strategy_state'] = strategy_state


def get_current_positions(state: Dict[str, Any]) -> Dict[str, float]:
    """Return a symbol -> quantity mapping for current holdings.

    Args:
        state: Portfolio manager state

    Returns:
        Dictionary mapping symbol to quantity
    """
    trading_client = state.get('trading_client')
    if not trading_client:
        logging.warning("PortfolioManager trading client is not configured")
        return {}

    try:
        raw_positions = trading_client.get_all_positions() or []
    except Exception as exc:
        logging.error("Failed to fetch current positions: %s", exc)
        return {}

    positions: Dict[str, float] = {}
    for position in raw_positions:
        symbol = getattr(position, 'symbol', None)
        if not symbol:
            continue
        qty_raw = getattr(position, 'qty', 0)
        try:
            positions[symbol] = float(qty_raw)
        except (TypeError, ValueError):
            logging.debug("Invalid quantity for %s: %s", symbol, qty_raw)
            positions[symbol] = 0.0
    return positions
