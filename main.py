import os
import sys
import time
import datetime
import logging
import pandas as pd
import requests
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
import yfinance as yf
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)

# Загрузка переменных окружения
load_dotenv()

# Проверка наличия API ключей
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
BASE_URL = "https://paper-api.alpaca.markets"

if not API_KEY or not SECRET_KEY:
    logging.error("Отсутствуют API ключи!")
    sys.exit(1)

def perform_rebalance():
    try:
        logging.info("Начало ребалансировки.")

        # Подключение к Alpaca
        try:
            trading_client = TradingClient(
                api_key=API_KEY,
                secret_key=SECRET_KEY,
                paper=True,
                url_override=BASE_URL
            )
        except Exception as e:
            logging.error(f"Ошибка при подключении к Alpaca: {e}")
            return

        # Получение списка S&P 500
        pkl_path = "sp500_tickers.pkl"
        try:
            if os.path.exists(pkl_path):
                sp500_tickers = pd.read_pickle(pkl_path)
            else:
                url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
                tables = pd.read_html(url)
                sp500_df = tables[0]
                sp500_tickers = sp500_df['Symbol'].tolist()
                pd.to_pickle(sp500_tickers, pkl_path)
        except (FileNotFoundError, pd.errors.UnpicklingError) as e:
            logging.error(f"Ошибка при чтении файла с тикерами: {e}")
            return
        except ValueError as e:
            logging.error(f"Ошибка парсинга HTML страницы с тикерами: {e}")
            return
        except Exception as e:
            logging.error(f"Неизвестная ошибка при получении списка S&P 500: {e}")
            return

        # Загрузка данных из yfinance
        try:
            # Параметр timeout помогает отлавливать зависания
            data = yf.download(sp500_tickers, period="1y", timeout=30)
            if 'Close' not in data.columns:
                raise KeyError("Столбец 'Close' отсутствует в загруженных данных.")
            data = data.dropna(axis=1)['Close']
            if data.empty:
                raise ValueError("Загруженные данные пусты.")
        except (requests.exceptions.RequestException, TimeoutError) as e:
            logging.error(f"Ошибка сетевого запроса при загрузке данных с yfinance: {e}")
            return
        except Exception as e:
            logging.error(f"Ошибка при загрузке данных с yfinance: {e}")
            return

        # Выбор 10 лучших по моментуму
        try:
            months = 12
            momentum_returns = data.pct_change(periods=months * 21).iloc[-1]
            top_tickers = momentum_returns.nlargest(10).index.tolist()
            if not top_tickers:
                raise ValueError("Не удалось определить топ тикеров для покупки.")
        except ZeroDivisionError as e:
            logging.error(f"Деление на ноль при расчёте моментума: {e}")
            return
        except Exception as e:
            logging.error(f"Ошибка при вычислении моментум доходностей: {e}")
            return

        # Получение текущих позиций
        try:
            positions = trading_client.get_all_positions()
            current_positions = {pos.symbol: float(pos.qty) for pos in positions}
        except Exception as e:
            logging.error(f"Ошибка при получении текущих позиций: {e}")
            current_positions = {}

        # Закрытие позиций, которых нет в новом списке
        for ticker in list(current_positions.keys()):
            if ticker not in top_tickers:
                try:
                    trading_client.close_position(ticker)
                    logging.info(f"Позиция {ticker} закрыта.")
                except Exception as e:
                    logging.error(f"Ошибка при закрытии позиции {ticker}: {e}")

        # Получение данных аккаунта для расчёта размера позиции
        try:
            account = trading_client.get_account()
            cash = float(account.cash)
        except Exception as e:
            logging.error(f"Ошибка при получении данных аккаунта: {e}")
            return

        # Проверка деления на ноль
        if len(top_tickers) == 0:
            logging.error("Ошибка: нет тикеров для покупки.")
            return

        try:
            position_size = cash / len(top_tickers)
        except ZeroDivisionError as e:
            logging.error(f"Деление на ноль при расчёте размера позиции: {e}")
            return

        # Исполнение ордеров для новых позиций
        for ticker in top_tickers:
            if ticker not in current_positions:
                try:
                    order = MarketOrderRequest(
                        symbol=ticker,
                        notional=position_size,
                        side=OrderSide.BUY,
                        type=OrderType.MARKET,
                        time_in_force=TimeInForce.DAY
                    )
                    trading_client.submit_order(order)
                    logging.info(f"Позиция {ticker} открыта.")
                except Exception as e:
                    logging.error(f"Ошибка при открытии позиции {ticker}: {e}")

        # Фиксируем успешное выполнение ребалансировки
        mark_rebalance_done()
        logging.info("Ребалансировка завершена успешно.")

    except Exception as e:
        logging.error(f"Общая ошибка ребалансировки: {e}")

def is_rebalance_done():
    try:
        with open("data/last_rebalance.txt", "r") as f:
            last_date = f.read().strip()
            if last_date == datetime.date.today().isoformat():
                return True
    except FileNotFoundError:
        return False
    except Exception as e:
        logging.error(f"Ошибка при проверке файла статуса ребалансировки: {e}")
    return False

def mark_rebalance_done():
    try:
        with open("data/last_rebalance.txt", "w") as f:
            f.write(datetime.date.today().isoformat())
    except Exception as e:
        logging.error(f"Ошибка при записи статуса ребалансировки: {e}")

def rebalance_with_retries(max_retries=5, delay=300):
    attempts = 0
    while attempts < max_retries:
        if is_rebalance_done():
            logging.info("Ребалансировка уже выполнена.")
            break
        logging.info(f"Попытка ребалансировки #{attempts + 1}")
        perform_rebalance()
        if is_rebalance_done():
            break
        attempts += 1
        logging.info(f"Ожидание {delay} секунд перед следующей попыткой...")
        time.sleep(delay)
    if not is_rebalance_done():
        logging.error("Ребалансировка не выполнена после максимального количества попыток.")

# Планировщик задач
scheduler = BlockingScheduler()

@scheduler.scheduled_job('cron', hour=10, minute=0)
def scheduled_rebalance():
    logging.info("Запущена запланированная ребалансировка.")
    rebalance_with_retries()

if __name__ == '__main__':
    try:
        logging.info("Старт планировщика задач.")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Остановка планировщика задач.")
    except Exception as e:
        logging.error(f"Неожиданная ошибка планировщика: {e}")