"""Momentum strategy for live account with investor management."""
import logging
import time
from typing import List, cast, TYPE_CHECKING, Optional

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

if TYPE_CHECKING:
    from core.investor_manager import InvestorManager

class LiveStrategy:
    """Class implementing momentum-based trading strategy for live account with investor management."""

    # Strategy configuration
    API_KEY = config.ALPACA_API_KEY_LIVE
    SECRET_KEY = config.ALPACA_SECRET_KEY_LIVE
    PAPER = True
    TOP_COUNT = 50
    ENABLED = True
    TICKERS = 'all'  # SNP500 + MEDIUM + CUSTOM tickers

    def __init__(self, trading_client: TradingClient, tickers: List[str],
                 top_count: int = 50,
                 investor_manager: Optional['InvestorManager'] = None):
        """Initialize strategy.

        Args:
            trading_client: Alpaca API client
            tickers: List of tickers to analyze
            top_count: Number of top stocks to select (default: 50)
            investor_manager: InvestorManager instance for investor operations
        """
        self.trading_client = trading_client
        self.data_client = StockHistoricalDataClient(self.API_KEY, self.SECRET_KEY)
        self.tickers = tickers
        self.top_count = top_count
        self.investor_manager = investor_manager

    @retry_on_exception()
    def get_signals(self) -> List[str]:
        """Get trading signals - top N stocks by momentum from self.tickers only.

        Returns:
            List[str]: List of tickers with highest momentum
        """
        try:
            data = load_market_data()
        except Exception:  # pylint: disable=broad-exception-caught
            raise

        if data is None or data.empty:  # type: ignore[union-attr]
            raise KeyError("'Close' column not found in data")
        if 'Close' not in data.columns.get_level_values(0):  # type: ignore[attr-defined]
            raise KeyError("'Close' column not found in data")

        data = cast(pd.DataFrame, data)  # type: ignore[assignment]
        # Calculate momentum for all tickers: (last_price / first_price - 1)
        close_prices = data.xs('Close', level=0, axis=1)  # type: ignore[attr-defined]
        momentum = (close_prices.iloc[-1] / close_prices.iloc[0] - 1)  # type: ignore[attr-defined]
        # Filter to only tickers in self.tickers, then get top_count
        momentum = cast(pd.Series, momentum)  # type: ignore[assignment]
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
                self.trading_client.submit_order(order)
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

    def rebalance(self) -> None:
        """Rebalance portfolio with investor accounts."""
        try:
            logging.info("Starting LiveStrategy portfolio rebalancing with investors")

            # 1. Обработать pending операции
            if self.investor_manager:
                logging.info("Processing pending investor operations")
                pending_results = self.investor_manager.process_pending_operations()
                logging.info(
                    "Processed %d pending operations",
                    pending_results.get('processed', 0)
                )

            # 2. Получить распределение капитала по счетам
            if self.investor_manager:
                allocations = self.investor_manager.get_account_allocations()
            else:
                # Fallback без investor_manager
                account_info = self.trading_client.get_account()
                total_equity = float(getattr(account_info, 'equity', 0))
                allocations = {
                    'low': {'total': total_equity * 0.45},
                    'medium': {'total': total_equity * 0.35},
                    'high': {'total': total_equity * 0.20}
                }

            # 3. Ребалансировать каждый виртуальный счет
            for account_name in ['low', 'medium', 'high']:
                account_capital = allocations[account_name]['total']

                if account_capital <= 0:
                    logging.info("No capital in %s account, skipping", account_name)
                    continue

                logging.info(
                    "Rebalancing %s account with capital $%.2f",
                    account_name, account_capital
                )

                # Получить тикеры для счета
                account_tickers = self._get_account_tickers(account_name)

                # Рассчитать top N по momentum
                top_tickers = self._calculate_signals(account_tickers)
                logging.info(
                    "Top %d stocks for %s: %s",
                    self.top_count, account_name, ', '.join(top_tickers[:5])
                )

                # Получить текущие позиции (из trades.csv инвесторов если есть)
                if self.investor_manager:
                    current_positions = self._get_investor_positions(account_name)
                else:
                    current_positions = get_positions(self.trading_client)

                # Определить какие позиции закрыть и открыть
                top_tickers_set = set(top_tickers)
                current_positions_set = set(current_positions)

                positions_to_close = list(current_positions_set - top_tickers_set)
                positions_to_open = list(top_tickers_set - current_positions_set)

                logging.info(
                    "Account %s: close %d, open %d positions",
                    account_name, len(positions_to_close), len(positions_to_open)
                )

                # Закрыть ненужные позиции
                if positions_to_close:
                    self._close_account_positions(account_name, positions_to_close)
                    time.sleep(2)

                # Открыть новые позиции
                if positions_to_open:
                    position_size = account_capital / len(positions_to_open)
                    if position_size < 1:
                        logging.warning(
                            "Position size too small for %s: $%.2f",
                            account_name, position_size
                        )
                        continue

                    self._open_account_positions(
                        account_name, positions_to_open, position_size
                    )

            # 4. Проверить контрольные суммы
            if self.investor_manager:
                is_valid, msg = self.investor_manager.verify_balance_integrity(
                    self.trading_client
                )
                if not is_valid:
                    logging.error("Balance integrity check failed: %s", msg)
                    raise ValueError(msg)

            # 5. Сохранить snapshot
            if self.investor_manager:
                from datetime import datetime
                import pytz
                ny_tz = pytz.timezone('America/New_York')
                self.investor_manager.save_daily_snapshot(
                    datetime.now(ny_tz)
                )

            logging.info("LiveStrategy portfolio rebalancing completed successfully")

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error during rebalancing: %s", exc, exc_info=True)
            raise

    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

    def _get_account_tickers(self, account_name: str) -> List[str]:
        """Получить тикеры для конкретного счета."""
        if account_name == 'low':
            # Консервативный: SNP500
            return config.SNP500_TICKERS[:100]
        elif account_name == 'medium':
            # Умеренный: MEDIUM_TICKERS
            return config.MEDIUM_TICKERS
        else:  # high
            # Агрессивный: HIGH_TICKERS
            return config.HIGH_TICKERS

    def _calculate_signals(self, tickers: List[str]) -> List[str]:
        """Рассчитать top N по momentum для списка тикеров из tickers."""
        # Загружаем все данные, но фильтруем по переданным tickers
        try:
            data = load_market_data()
        except Exception as exc:
            logging.error("Error loading market data: %s", exc)
            return tickers[:self.top_count]  # Fallback

        if data is None or data.empty or 'Close' not in data.columns.get_level_values(0):  # type: ignore
            logging.warning("No data for signals calculation")
            return tickers[:self.top_count]

        data = cast(pd.DataFrame, data)  # type: ignore
        try:
            # Calculate momentum for all tickers, but select only from provided tickers
            momentum = (data.xs('Close', level=0, axis=1)  # type: ignore[attr-defined]
                        .dropna(axis='columns')  # type: ignore
                        .pct_change(periods=len(data)-1)  # type: ignore
                        .iloc[-1])  # type: ignore
            # Filter to only tickers in the provided list, then get top_count
            momentum = cast(pd.Series, momentum)  # type: ignore[assignment]
            momentum_filtered = momentum[momentum.index.isin(tickers)]
            return (momentum_filtered
                    .nlargest(self.top_count)  # type: ignore
                    .index
                    .tolist())
        except Exception as exc:
            logging.error("Error calculating signals: %s", exc)
            return tickers[:self.top_count]

    def _get_investor_positions(self, account_name: str) -> List[str]:
        """Получить текущие позиции счета из trades.csv инвесторов."""
        if not self.investor_manager:
            return []

        positions = set()
        for investor_name in self.investor_manager.investors:
            investor_path = self.investor_manager._get_investor_path(investor_name)
            trades_file = investor_path / 'trades.csv'

            if not trades_file.exists():
                continue

            try:
                import csv
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

    def _close_account_positions(self, account_name: str,
                                positions: List[str]) -> None:
        """Закрыть позиции счета."""
        snapshot = {
            pos.symbol: float(pos.qty)
            for pos in self.trading_client.get_all_positions()
        }
        for ticker in positions:
            try:
                total_shares = snapshot.get(ticker, 0.0)
                self.trading_client.close_position(ticker)
                logging.info(
                    "Closed %s position from %s account",
                    ticker, account_name
                )

                # Записать SELL в trades.csv инвесторов
                if self.investor_manager:
                    # Получить текущую цену
                    try:
                        request = StockBarsRequest(
                            symbol_or_symbols=[ticker],
                            timeframe=TimeFrame.Minute,  # type: ignore
                            limit=1
                        )
                        bars = self.data_client.get_stock_bars(request)
                        price = float(bars[ticker][-1].close) if bars and ticker in bars else 0.0  # type: ignore
                    except Exception:  # pylint: disable=broad-exception-caught
                        price = 0.0

                    if total_shares > 0:
                        self.investor_manager.distribute_trade_to_investors(
                            account_name, 'SELL', ticker,
                            total_shares, price
                        )

            except Exception as exc:
                logging.error(
                    "Error closing %s from %s: %s",
                    ticker, account_name, exc
                )

    def _open_account_positions(self, account_name: str,
                               tickers: List[str],
                               cash_per_position: float) -> None:
        """Открыть новые позиции на счете."""
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
                order_response = self.trading_client.submit_order(order)
                logging.info(
                    "Opened %s in %s account for $%.2f",
                    ticker, account_name, cash_per_position
                )

                # Записать BUY в trades.csv инвесторов
                if self.investor_manager:
                    # Дождаться исполнения и получить реальную цену
                    price = cash_per_position
                    shares = 1.0
                    if order_response and order_response.id:  # type: ignore
                        try:
                            max_attempts = 10
                            for _ in range(max_attempts):
                                order_status = self.trading_client.get_order_by_id(order_response.id)  # type: ignore
                                if order_status and order_status.filled_avg_price:  # type: ignore
                                    price = float(order_status.filled_avg_price)  # type: ignore
                                    shares = float(order_status.filled_qty or 1)  # type: ignore
                                    break
                                time.sleep(0.5)
                        except Exception:  # pylint: disable=broad-exception-caught
                            pass

                    if shares > 0:
                        self.investor_manager.distribute_trade_to_investors(
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
