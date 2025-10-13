"""Модуль с торговыми стратегиями."""
import logging
import time
from typing import Dict, List

import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from utils import retry_on_exception


class MomentumStrategy:
    """Класс реализующий торговую стратегию на основе моментума."""

    def __init__(self, trading_client: TradingClient, tickers: List[str]):
        """Инициализация стратегии.

        Args:
            trading_client: Клиент для работы с Alpaca API
            tickers: Список тикеров для торговли
        """
        self.trading_client = trading_client
        self.tickers = tickers

    @retry_on_exception()
    def get_signals(self) -> List[str]:
        """Получение торговых сигналов - топ-10 акций по моментуму.

        Returns:
            List[str]: Список тикеров с наивысшим моментумом
        """
        data = yf.download(self.tickers, period="1y", timeout=30)
        if 'Close' not in data.columns:
            raise KeyError("Столбец 'Close' отсутствует в данных")

        momentum_returns = (
            data['Close']
            .dropna(axis=1)
            .pct_change(periods=len(data)-1)
            .iloc[-1]
            .nlargest(10)
        )
        return momentum_returns.index.tolist()

    @retry_on_exception()
    def get_positions(self) -> Dict[str, float]:
        """Получение текущих позиций.

        Returns:
            Dict[str, float]: Словарь текущих позиций
        """
        positions = self.trading_client.get_all_positions()
        return {pos.symbol: float(pos.qty) for pos in positions}

    def close_positions(self, positions: List[str]) -> None:
        """Закрытие указанных позиций.

        Args:
            positions: Список тикеров для закрытия
        """
        for ticker in positions:
            try:
                self.trading_client.close_position(ticker)
                logging.info("Позиция %s закрыта", ticker)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.error("Ошибка закрытия позиции %s: %s", ticker, exc)

    def open_positions(self, tickers: List[str],
                       cash_per_position: float) -> None:
        """Открытие новых позиций.

        Args:
            tickers: Список тикеров для открытия
            cash_per_position: Размер позиции в долларах
        """
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
                    "Открыта позиция %s на $%.2f",
                    ticker,
                    cash_per_position
                )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.error("Ошибка открытия позиции %s: %s", ticker, exc)

    def rebalance(self) -> None:
        """Ребалансировка портфеля."""
        try:
            logging.info("Начало ребалансировки портфеля")

            # Получаем сигналы торговой стратегии
            top_tickers = self.get_signals()
            logging.info("Топ-10 акций по моментуму: %s", ', '.join(top_tickers))

            # Получаем текущие позиции
            current_positions = self.get_positions()
            logging.info("Текущие позиции: %s", current_positions)

            # Определяем позиции для закрытия и открытия
            positions_to_close = [
                ticker for ticker in current_positions
                if ticker not in top_tickers
            ]
            positions_to_open = [
                ticker for ticker in top_tickers
                if ticker not in current_positions
            ]

            logging.info("Позиции для закрытия: %s", positions_to_close)
            logging.info("Позиции для открытия: %s", positions_to_open)

            # Закрываем ненужные позиции
            if positions_to_close:
                self.close_positions(positions_to_close)
                time.sleep(5)

            # Открываем новые позиции
            if positions_to_open:
                account = self.trading_client.get_account()
                available_cash = float(account.cash)
                if available_cash <= 0:
                    logging.warning(
                        "Недостаточно средств: $%.2f",
                        available_cash
                    )
                    return

                position_size = available_cash / len(positions_to_open)
                if position_size < 1:
                    logging.warning(
                        "Размер позиции слишком мал: $%.2f",
                        position_size
                    )
                    return

                self.open_positions(positions_to_open, position_size)

            logging.info("Ребалансировка выполнена успешно")

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Ошибка при ребалансировке: %s", exc, exc_info=True)
