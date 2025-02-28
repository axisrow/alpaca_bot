import yfinance as yf
import pandas as pd
import logging
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from config import snp500_tickers
from strategy import MomentumStrategy
from alpaca.trading.enums import OrderSide  # для FakeTradingClient

# =======================
# НАСТРОЙКИ БЭКТЕСТА
# =======================
INITIAL_CASH = 100000.0
START_DATE = datetime(2025, 2, 26)
END_DATE = datetime(2025, 2, 28)
REBALANCING_FREQUENCY = 'D'  # Ребалансировка по дням (можно изменить на 'M' для месячной и т.п.)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Фейковые классы для симуляции торгового клиента

class FakePosition:
    def __init__(self, symbol, qty):
        self.symbol = symbol
        self.qty = qty

class FakeAccount:
    def __init__(self, cash):
        self.cash = cash

class FakeTradingClient:
    def __init__(self, initial_cash: float, prices: pd.DataFrame):
        self.cash = initial_cash
        self.positions = {}  # формат: {ticker: qty}
        self.prices = prices
        self.current_date = None
        self.trade_history = []  # Список для записи всех сделок

    def set_current_date(self, date: pd.Timestamp):
        self.current_date = date

    def get_price(self, ticker: str) -> float:
        try:
            price = self.prices[ticker].reindex([self.current_date], method='nearest').iloc[0]
            return price
        except Exception as e:
            raise ValueError(f"Не удалось получить цену для {ticker} на {self.current_date}") from e

    def get_all_positions(self):
        return [FakePosition(ticker, qty) for ticker, qty in self.positions.items()]

    def get_account(self):
        return FakeAccount(self.cash)

    def close_position(self, ticker: str):
        if ticker not in self.positions:
            raise ValueError(f"Позиция по {ticker} отсутствует")
        price = self.get_price(ticker)
        qty = self.positions[ticker]
        proceeds = qty * price
        self.cash += proceeds
        logging.info(f"Фейковый клиент: продана позиция {ticker} ({qty} акций по ${price:.2f}), получено ${proceeds:.2f}")
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

    def submit_order(self, order):
        if order.side == OrderSide.BUY:
            price = self.get_price(order.symbol)
            shares = int(order.notional // price)
            if shares <= 0:
                raise ValueError(f"Недостаточно средств для покупки хотя бы 1 акции {order.symbol}")
            cost = shares * price
            if cost > self.cash:
                raise ValueError(f"Недостаточно наличных для покупки {order.symbol}")
            self.cash -= cost
            self.positions[order.symbol] = self.positions.get(order.symbol, 0) + shares
            logging.info(f"Фейковый клиент: куплено {shares} акций {order.symbol} по ${price:.2f}, затрачено ${cost:.2f}")
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

# Подкласс для бэктеста, переопределяем метод get_signals для работы с историческими данными
class BacktestMomentumStrategy(MomentumStrategy):
    def __init__(self, trading_client, tickers, prices, current_date):
        super().__init__(trading_client, tickers)
        self.prices = prices
        self.current_date = current_date

    def get_signals(self) -> list:
        one_year_ago = self.current_date - timedelta(days=365)
        try:
            price_start = self.prices.reindex([one_year_ago], method='nearest').iloc[0]
            price_end = self.prices.reindex([self.current_date], method='nearest').iloc[0]
        except Exception as e:
            logging.error(f"Ошибка получения цен для расчёта импульса на {self.current_date}: {e}")
            return []
        momentum = (price_end / price_start - 1).nlargest(10)
        return momentum.index.tolist()

def main():
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
                logging.warning(f"Нет данных 'Close' для {ticker}")
        except Exception as e:
            logging.warning(f"Ошибка загрузки данных для {ticker}: {e}")

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
    rebalancing_dates = trading_dates[trading_dates >= START_DATE].to_series().resample(REBALANCING_FREQUENCY).last().dropna()

    # ---------------------------
    # ИНИЦИАЛИЗАЦИЯ КЛИЕНТА, СТРАТЕГИИ И ДОКУМЕНТАЦИЯ ТРАНЗАКЦИЙ
    # ---------------------------
    fake_client = FakeTradingClient(INITIAL_CASH, prices)
    strategy = BacktestMomentumStrategy(fake_client, available_tickers, prices, current_date=rebalancing_dates.index[0])
    portfolio_history = []  # Для сохранения динамики портфеля

    # ---------------------------
    # ЦИКЛ БЭКТЕСТА
    # ---------------------------
    for current_date in rebalancing_dates.index:
        logging.info(f"\n--- Ребалансировка на {current_date.date()} ---")
        fake_client.set_current_date(current_date)
        strategy.current_date = current_date

        try:
            strategy.rebalance()
        except Exception as e:
            logging.error(f"Ошибка при ребалансировке на {current_date.date()}: {e}")

        # Рассчитываем стоимость портфеля на текущую дату
        total_value = fake_client.cash
        for ticker, qty in fake_client.positions.items():
            try:
                price = fake_client.get_price(ticker)
                total_value += qty * price
            except Exception as e:
                logging.warning(f"Не удалось получить цену для {ticker} на {current_date.date()}: {e}")
        logging.info(f"Стоимость портфеля на {current_date.date()}: ${total_value:.2f}")
        portfolio_history.append({'date': current_date, 'portfolio_value': total_value})

    # Финальная оценка портфеля
    final_date = rebalancing_dates.index[-1]
    final_value = fake_client.cash
    for ticker, qty in fake_client.positions.items():
        try:
            price = fake_client.get_price(ticker)
            final_value += qty * price
        except Exception as e:
            logging.warning(f"Не удалось получить цену для {ticker} на {final_date.date()}: {e}")
    logging.info(f"\nФинальная стоимость портфеля на {final_date.date()}: ${final_value:.2f}")

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