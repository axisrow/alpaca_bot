"""Модуль для бэктестинга торговой стратегии."""
import logging
from datetime import datetime, timedelta
from typing import Dict, List

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from alpaca.trading.enums import OrderSide

from config import snp500_tickers
from strategy import MomentumStrategy

# =======================
# НАСТРОЙКИ БЭКТЕСТА
# =======================
INITIAL_CASH = 100000.0
START_DATE = datetime(2025, 3, 1)
END_DATE = datetime(2025, 3, 3)
# Ребалансировка по дням (можно изменить на 'M' для месячной и т.п.)
REBALANCING_FREQUENCY = 'D'

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


class FakePosition:
    """Фейковая позиция для симуляции."""

    def __init__(self, symbol: str, qty: float):
        """Инициализация позиции.

        Args:
            symbol: Тикер
            qty: Количество акций
        """
        self.symbol = symbol
        self.qty = qty


class FakeAccount:
    """Фейковый аккаунт для симуляции."""

    def __init__(self, cash: float):
        """Инициализация аккаунта.

        Args:
            cash: Наличные средства
        """
        self.cash = cash


class FakeTradingClient:
    """Фейковый торговый клиент для симуляции."""

    def __init__(self, initial_cash: float, prices: pd.DataFrame):
        """Инициализация клиента.

        Args:
            initial_cash: Начальный капитал
            prices: DataFrame с историческими ценами
        """
        self.cash = initial_cash
        self.positions: Dict[str, float] = {}
        self.prices = prices
        self.current_date = None
        self.trade_history: List[Dict] = []

    def set_current_date(self, date: pd.Timestamp) -> None:
        """Установка текущей даты для симуляции.

        Args:
            date: Дата для установки
        """
        self.current_date = date

    def get_price(self, ticker: str) -> float:
        """Получение цены для тикера на текущую дату.

        Args:
            ticker: Тикер

        Returns:
            float: Цена акции
        """
        try:
            price = self.prices[ticker].reindex(
                [self.current_date],
                method='nearest'
            ).iloc[0]
            return float(price)
        except Exception as exc:
            raise ValueError(
                f"Не удалось получить цену для {ticker} "
                f"на {self.current_date}"
            ) from exc

    def get_all_positions(self) -> List[FakePosition]:
        """Получение всех позиций.

        Returns:
            List[FakePosition]: Список позиций
        """
        return [FakePosition(ticker, qty)
                for ticker, qty in self.positions.items()]

    def get_account(self) -> FakeAccount:
        """Получение информации об аккаунте.

        Returns:
            FakeAccount: Информация об аккаунте
        """
        return FakeAccount(self.cash)

    def close_position(self, ticker: str) -> None:
        """Закрытие позиции.

        Args:
            ticker: Тикер для закрытия
        """
        if ticker not in self.positions:
            raise ValueError(f"Позиция по {ticker} отсутствует")
        price = self.get_price(ticker)
        qty = self.positions[ticker]
        proceeds = qty * price
        self.cash += proceeds
        logging.info(
            "Фейковый клиент: продана позиция %s (%s акций по $%.2f), "
            "получено $%.2f",
            ticker,
            qty,
            price,
            proceeds
        )
        # Запись сделки на продажу
        self.trade_history.append({
            'date': self.current_date,
            'symbol': ticker,
            'side': 'SELL',
            'shares': qty,
            'price': price,
            'total': proceeds
        })
        del self.positions[ticker]

    def submit_order(self, order) -> None:
        """Отправка ордера на исполнение.

        Args:
            order: Ордер для исполнения
        """
        if order.side == OrderSide.BUY:
            price = self.get_price(order.symbol)
            shares = int(order.notional // price)
            if shares <= 0:
                raise ValueError(
                    f"Недостаточно средств для покупки хотя бы 1 акции "
                    f"{order.symbol}"
                )
            cost = shares * price
            if cost > self.cash:
                raise ValueError(
                    f"Недостаточно наличных для покупки {order.symbol}"
                )
            self.cash -= cost
            self.positions[order.symbol] = (
                self.positions.get(order.symbol, 0) + shares
            )
            logging.info(
                "Фейковый клиент: куплено %s акций %s по $%.2f, "
                "затрачено $%.2f",
                shares,
                order.symbol,
                price,
                cost
            )
            # Запись сделки на покупку
            self.trade_history.append({
                'date': self.current_date,
                'symbol': order.symbol,
                'side': 'BUY',
                'shares': shares,
                'price': price,
                'total': cost
            })
        else:
            raise NotImplementedError("Поддерживаются только ордера на покупку")


class BacktestMomentumStrategy(MomentumStrategy):
    """Подкласс стратегии для бэктеста с историческими данными."""

    def __init__(
        self,
        trading_client,
        tickers: List[str],
        prices: pd.DataFrame,
        current_date: pd.Timestamp
    ):
        """Инициализация стратегии для бэктеста.

        Args:
            trading_client: Торговый клиент
            tickers: Список тикеров
            prices: DataFrame с историческими ценами
            current_date: Текущая дата для симуляции
        """
        super().__init__(trading_client, tickers)
        self.prices = prices
        self.current_date = current_date

    def get_signals(self) -> List[str]:
        """Получение сигналов на основе исторических данных.

        Returns:
            List[str]: Список тикеров с наивысшим моментумом
        """
        one_year_ago = self.current_date - timedelta(days=365)
        try:
            price_start = self.prices.reindex(
                [one_year_ago],
                method='nearest'
            ).iloc[0]
            price_end = self.prices.reindex(
                [self.current_date],
                method='nearest'
            ).iloc[0]
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error(
                "Ошибка получения цен для расчёта импульса на %s: %s",
                self.current_date,
                exc
            )
            return []
        momentum = (price_end / price_start - 1).nlargest(10)
        return momentum.index.tolist()


def main() -> None:  # pylint: disable=too-many-locals,too-many-statements
    """Основная функция бэктестинга."""
    # ---------------------------
    # ЗАГРУЗКА И ПОДГОТОВКА ДАННЫХ
    # ---------------------------
    data_start = START_DATE - timedelta(days=370)
    logging.info("Загрузка исторических данных с yfinance...")
    data = yf.download(snp500_tickers,
                       start=data_start.strftime("%Y-%m-%d"),
                       end=END_DATE.strftime("%Y-%m-%d"),
                       group_by='ticker',
                       progress=False)

    # Извлекаем данные 'Close' для каждого тикера
    close_data = {}
    for ticker in snp500_tickers:
        try:
            ticker_df = data[ticker]
            if 'Close' in ticker_df.columns:
                close_data[ticker] = ticker_df['Close']
            else:
                logging.warning("Нет данных 'Close' для %s", ticker)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.warning("Ошибка загрузки данных для %s: %s", ticker, exc)

    prices = pd.DataFrame(close_data)
    if prices.empty:
        logging.error("Не удалось загрузить данные ни для одного тикера.")
        return
    prices.sort_index(inplace=True)
    prices.index = pd.to_datetime(prices.index)

    available_tickers = list(prices.columns)
    if not available_tickers:
        logging.error("Нет доступных тикеров для бэктеста.")
        return

    trading_dates = prices.index
    rebalancing_dates = (
        trading_dates[trading_dates >= START_DATE]
        .to_series()
        .resample(REBALANCING_FREQUENCY)
        .last()
        .dropna()
    )

    # ---------------------------
    # ИНИЦИАЛИЗАЦИЯ КЛИЕНТА, СТРАТЕГИИ И ДОКУМЕНТАЦИЯ ТРАНЗАКЦИЙ
    # ---------------------------
    fake_client = FakeTradingClient(INITIAL_CASH, prices)
    strategy = BacktestMomentumStrategy(
        fake_client,
        available_tickers,
        prices,
        current_date=rebalancing_dates.index[0]
    )
    portfolio_history: List[Dict] = []

    # ---------------------------
    # ЦИКЛ БЭКТЕСТА
    # ---------------------------
    for current_date in rebalancing_dates.index:
        logging.info("\n--- Ребалансировка на %s ---", current_date.date())
        fake_client.set_current_date(current_date)
        strategy.current_date = current_date

        try:
            strategy.rebalance()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error(
                "Ошибка при ребалансировке на %s: %s",
                current_date.date(),
                exc
            )

        # Рассчитываем стоимость портфеля на текущую дату
        total_value = fake_client.cash
        for ticker, qty in fake_client.positions.items():
            try:
                price = fake_client.get_price(ticker)
                total_value += qty * price
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.warning(
                    "Не удалось получить цену для %s на %s: %s",
                    ticker,
                    current_date.date(),
                    exc
                )
        logging.info(
            "Стоимость портфеля на %s: $%.2f",
            current_date.date(),
            total_value
        )
        portfolio_history.append({
            'date': current_date,
            'portfolio_value': total_value
        })

    # Финальная оценка портфеля
    final_date = rebalancing_dates.index[-1]
    final_value = fake_client.cash
    for ticker, qty in fake_client.positions.items():
        try:
            price = fake_client.get_price(ticker)
            final_value += qty * price
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.warning(
                "Не удалось получить цену для %s на %s: %s",
                ticker,
                final_date.date(),
                exc
            )
    logging.info(
        "\nФинальная стоимость портфеля на %s: $%.2f",
        final_date.date(),
        final_value
    )

    # ---------------------------
    # ВИЗУАЛИЗАЦИЯ ДОХОДНОСТИ ПОРТФЕЛЯ
    # ---------------------------
    portfolio_df = pd.DataFrame(portfolio_history)
    portfolio_df.set_index('date', inplace=True)
    plt.figure(figsize=(10, 6))
    plt.plot(portfolio_df.index, portfolio_df['portfolio_value'], marker='o')
    plt.title("Динамика стоимости портфеля")
    plt.xlabel("Дата")
    plt.ylabel("Стоимость портфеля, $")
    plt.grid(True)
    plt.savefig("data/portfolio_performance.png")
    plt.show()
    logging.info("График динамики портфеля сохранён как portfolio_performance.png")

    # ---------------------------
    # СОХРАНЕНИЕ ИСТОРИИ СДЕЛОК В CSV
    # ---------------------------
    trades_df = pd.DataFrame(fake_client.trade_history)
    trades_df.to_csv("data/trades_history.csv", index=False)
    logging.info("История сделок сохранена в файл data/trades_history.csv")


if __name__ == "__main__":
    main()
