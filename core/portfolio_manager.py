"""Portfolio manager module."""
import logging
from typing import Any, Dict

from alpaca.trading.client import TradingClient


class PortfolioManager:
    """Lightweight helper for inspecting current portfolio state."""

    def __init__(self, trading_client: TradingClient, strategy: Any | None = None):
        """Initialize manager with default client and optional strategy."""
        self.trading_client = trading_client
        self.strategy = strategy

    def set_strategy(self, strategy: Any) -> None:
        """Attach or update the active strategy reference."""
        self.strategy = strategy

    def get_current_positions(self) -> Dict[str, float]:
        """Return a symbol -> quantity mapping for current holdings."""
        if not self.trading_client:
            logging.warning("PortfolioManager trading client is not configured")
            return {}

        try:
            raw_positions = self.trading_client.get_all_positions() or []
        except Exception as exc:  # pylint: disable=broad-exception-caught
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
