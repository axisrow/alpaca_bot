"""Base momentum strategy class."""
import logging
import time
from typing import List, Tuple, cast

import pandas as pd
from alpaca.common.exceptions import APIError
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from core.data_loader import load_market_data
from core.utils import retry_on_exception


class BaseMomentumStrategy:
    """Base class implementing momentum-based trading strategy.

    Subclasses should define:
    - API_KEY: Alpaca API key
    - SECRET_KEY: Alpaca secret key
    - PAPER: Paper trading flag (True/False)
    - TOP_COUNT: Number of top stocks to hold
    - ENABLED: Strategy enabled flag
    - TICKERS: Ticker universe ('snp500_only', 'all', etc.)
    """

    # Default configuration (should be overridden in subclasses)
    API_KEY = ""
    SECRET_KEY = ""
    PAPER = True
    TOP_COUNT = 50
    ENABLED = True
    TICKERS = 'snp500_only'

    def __init__(self, trading_client: TradingClient, tickers: List[str], top_count: int = 50):
        """Initialize strategy.

        Args:
            trading_client: Alpaca API client
            tickers: List of tickers to analyze
            top_count: Number of top stocks to select
        """
        self.trading_client = trading_client
        self.tickers = tickers
        self.top_count = top_count
        self.data_client: StockHistoricalDataClient | None = None

    @staticmethod
    def _is_pdt_error(exc: Exception) -> bool:
        """Detect Alpaca PDT protection error."""
        msg = str(exc).lower()
        return "pattern day trading" in msg or "40310100" in msg

    def _get_data_client(self) -> StockHistoricalDataClient:
        """Create or return market data client bound to strategy keys."""
        if self.data_client is None:
            self.data_client = StockHistoricalDataClient(self.API_KEY, self.SECRET_KEY)
        return self.data_client

    def _preload_last_prices(self, tickers: List[str]) -> dict[str, float]:
        """Return latest market prices for provided tickers (best-effort, real-time)."""
        if not tickers:
            return {}

        prices: dict[str, float] = {}
        try:
            client = self._get_data_client()
            request = StockLatestTradeRequest(symbol_or_symbols=tickers)
            trades = client.get_stock_latest_trade(request)
            for symbol in tickers:
                trade = trades.get(symbol)
                if trade:
                    price = float(getattr(trade, 'price', 0.0) or 0.0)
                    if price > 0:
                        prices[symbol] = price
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.warning(
                "Failed bulk latest price lookup for %d tickers: %s",
                len(tickers),
                exc
            )

        # Fallback per-ticker for any missing entries
        for symbol in tickers:
            if symbol in prices:
                continue
            try:
                client = self._get_data_client()
                request = StockLatestTradeRequest(symbol_or_symbols=symbol)
                trade = client.get_stock_latest_trade(request)
                if symbol in trade:
                    price = float(getattr(trade[symbol], 'price', 0.0) or 0.0)
                    if price > 0:
                        prices[symbol] = price
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.warning("Failed price lookup for %s: %s", symbol, exc)

        return prices

    def _filter_tradable_tickers(self, tickers: List[str]) -> List[str]:
        """Отфильтровать тикеры, доступные к торговле (active + tradable)."""
        tradable: List[str] = []
        skipped: List[Tuple[str, str]] = []

        for ticker in tickers:
            try:
                asset = self.trading_client.get_asset(ticker)
                raw_status = getattr(asset, 'status', 'active')
                status = raw_status.lower() if isinstance(raw_status, str) else 'active'
                raw_tradable = getattr(asset, 'tradable', True)
                tradable_flag = bool(raw_tradable)

                if not tradable_flag:
                    skipped.append((ticker, 'not_tradable'))
                    continue

                if status != 'active':
                    skipped.append((ticker, status or 'inactive'))
                    continue

                tradable.append(ticker)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.warning(
                    "Skip %s: failed to fetch asset status (%s)",
                    ticker, exc
                )
                skipped.append((ticker, 'lookup_failed'))

        if skipped:
            logging.warning(
                "Skipping %d non-tradable assets: %s",
                len(skipped),
                [(t, s) for t, s in skipped]
            )

        return tradable

    @retry_on_exception()
    def get_signals(self) -> List[str]:
        """Get trading signals - top N stocks by momentum from self.tickers only.

        Returns:
            List[str]: List of tickers with highest momentum
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

        # Filter to only tickers in self.tickers, then get top_count
        momentum_filtered = momentum[momentum.index.isin(self.tickers)]
        return (momentum_filtered
                .nlargest(self.top_count)  # type: ignore[attr-defined]
                .index
                .tolist())

    def close_positions(self, positions: List[str]) -> None:
        """Close specified positions.

        Args:
            positions: List of tickers to close
        """
        failed_closures = []
        for ticker in positions:
            try:
                self.trading_client.close_position(ticker)
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

    def open_positions(self, tickers: List[str],
                       cash_per_position: float) -> None:
        """Open new positions.

        Args:
            tickers: List of tickers to open
            cash_per_position: Position size in dollars
        """
        price_lookup = self._preload_last_prices(tickers)
        failed_opens = []
        for ticker in tickers:
            try:
                asset = self.trading_client.get_asset(ticker)
                fractionable_flag = bool(getattr(asset, 'fractionable', True))

                if fractionable_flag:
                    order = MarketOrderRequest(
                        symbol=ticker,
                        notional=round(cash_per_position, 2),
                        side=OrderSide.BUY,
                        type=OrderType.MARKET,
                        time_in_force=TimeInForce.DAY
                    )
                else:
                    price = price_lookup.get(ticker, 0.0)
                    qty = int(cash_per_position // price) if price > 0 else 0
                    if price <= 0 or qty <= 0:
                        logging.warning(
                            "Skipping %s: cannot place whole-share order (price=%.2f, cash=%.2f)",
                            ticker,
                            price,
                            cash_per_position
                        )
                        failed_opens.append((ticker, "no_qty_for_whole_share"))
                        continue

                    order = MarketOrderRequest(
                        symbol=ticker,
                        qty=qty,
                        side=OrderSide.BUY,
                        type=OrderType.MARKET,
                        time_in_force=TimeInForce.DAY
                    )
                self.trading_client.submit_order(order)
                logging.info(
                    "Opened position %s using %s (cash target $%.2f, price %.2f)",
                    ticker,
                    "notional" if fractionable_flag else f"qty={order.qty}",  # type: ignore[attr-defined]
                    cash_per_position,
                    price_lookup.get(ticker, 0.0)
                )
            except APIError as exc:
                if self._is_pdt_error(exc):
                    logging.warning(
                        "Order for %s blocked by PDT protection; skipping ticker",
                        ticker
                    )
                    failed_opens.append((ticker, "PDT protection"))
                    continue
                logging.error(
                    "Error opening position %s: %s",
                    ticker,
                    exc,
                    exc_info=True
                )
                failed_opens.append((ticker, str(exc)))
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

    def rebalance(self) -> None:
        """Rebalance portfolio."""
        try:
            logging.info("Starting portfolio rebalancing")

            # Get trading strategy signals
            top_tickers = self.get_signals()
            logging.info("Top %d stocks by momentum: %s", self.top_count, ', '.join(top_tickers))
            if not top_tickers:
                logging.warning("No tickers returned for strategy, skipping rebalance")
                return

            top_tickers = self._filter_tradable_tickers(top_tickers)
            if not top_tickers:
                logging.warning("No tradable tickers after filtering, stopping rebalance")
                return
            price_lookup = self._preload_last_prices(top_tickers)
            asset_cache = {}
            for ticker in top_tickers:
                try:
                    asset_cache[ticker] = self.trading_client.get_asset(ticker)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logging.warning("Failed to fetch asset profile for %s: %s", ticker, exc)
                    asset_cache[ticker] = None

            # Get current positions
            positions_raw = self.trading_client.get_all_positions()
            current_positions = {
                pos.symbol: float(pos.qty)
                for pos in positions_raw
            }
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
                self.close_positions(positions_to_close)
                time.sleep(5)

            # Refresh current positions after closing
            refreshed_positions = {
                pos.symbol: pos
                for pos in self.trading_client.get_all_positions()
            }

            account = self.trading_client.get_account()  # type: ignore[no-untyped-call]
            portfolio_value = float(
                getattr(
                    account,
                    'portfolio_value',
                    getattr(account, 'equity', 0.0)
                )
            )
            if portfolio_value <= 0:
                logging.warning("Portfolio value not available for rebalancing")
                return

            target_value = portfolio_value / len(top_tickers)
            if target_value <= 0:
                logging.warning("Target value per ticker is non-positive")
                return

            tolerance = 1.0  # Skip tiny adjustments
            failed_adjustments = []
            for ticker in top_tickers:
                asset = asset_cache.get(ticker)
                fractionable_flag = bool(getattr(asset, 'fractionable', True)) if asset else True
                price = price_lookup.get(ticker, 0.0)
                position = refreshed_positions.get(ticker)
                current_value = float(getattr(position, 'market_value', 0)) if position else 0.0
                current_shares = float(getattr(position, 'qty', 0) or 0) if position else 0.0
                difference = target_value - current_value

                if abs(difference) <= tolerance:
                    continue

                side = OrderSide.BUY if difference > 0 else OrderSide.SELL
                order: MarketOrderRequest | None

                if fractionable_flag:
                    order = MarketOrderRequest(
                        symbol=ticker,
                        notional=round(abs(difference), 2),
                        side=side,
                        type=OrderType.MARKET,
                        time_in_force=TimeInForce.DAY
                    )
                else:
                    if price <= 0:
                        logging.warning(
                            "Skip %s: missing price for whole-share adjustment",
                            ticker
                        )
                        failed_adjustments.append((ticker, "no_price_for_whole_share"))
                        continue

                    target_shares = int(target_value // price)
                    delta_shares = target_shares - current_shares
                    if abs(delta_shares) < 1:
                        continue

                    side = OrderSide.BUY if delta_shares > 0 else OrderSide.SELL
                    order = MarketOrderRequest(
                        symbol=ticker,
                        qty=int(abs(delta_shares)),
                        side=side,
                        type=OrderType.MARKET,
                        time_in_force=TimeInForce.DAY
                    )
                try:
                    self.trading_client.submit_order(order)
                    logging.info(
                        "Adjusted %s by %s using %s (target $%.2f, price %.2f)",
                        ticker,
                        side.name,
                        "notional" if fractionable_flag else f"qty={order.qty}",  # type: ignore[attr-defined]
                        target_value,
                        price
                    )
                except APIError as exc:
                    if self._is_pdt_error(exc):
                        logging.warning(
                            "Adjustment for %s blocked by PDT protection; skipping ticker",
                            ticker
                        )
                        failed_adjustments.append((ticker, "PDT protection"))
                        continue
                    raise

            if failed_adjustments:
                logging.warning(
                    "Skipped %d adjustment(s) due to PDT: %s",
                    len(failed_adjustments),
                    failed_adjustments
                )

            logging.info("Portfolio rebalancing completed successfully")

        except APIError as exc:
            if self._is_pdt_error(exc):
                # Если PDT все же всплыл вне точечной обработки
                logging.warning("Rebalance encountered PDT protection: %s", exc)
            else:
                logging.error("Error during rebalancing: %s", exc, exc_info=True)
                raise
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error during rebalancing: %s", exc, exc_info=True)
