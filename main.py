import os
import sys
import time
import datetime
import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
import yfinance as yf
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler

# Загружаем переменные окружения
load_dotenv()

# Проверяем наличие API ключей
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
BASE_URL = "https://paper-api.alpaca.markets"

if not API_KEY or not SECRET_KEY:
    print("Ошибка: отсутствуют API ключи!")
    sys.exit(1)

# Функция для выполнения ребалансировки
def perform_rebalance():
    try:
        print(f"{datetime.datetime.now()}: Начало ребалансировки.")
        # Подключение к Alpaca
        trading_client = TradingClient(api_key=API_KEY, secret_key=SECRET_KEY, paper=True, url_override=BASE_URL)
        
        # Получение списка S&P 500
        pkl_path = "sp500_tickers.pkl"
        if os.path.exists(pkl_path):
            sp500_tickers = pd.read_pickle(pkl_path)
        else:
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            tables = pd.read_html(url)
            sp500_df = tables[0]
            sp500_tickers = sp500_df['Symbol'].tolist()
            pd.to_pickle(sp500_tickers, pkl_path)
        
        # Загрузка данных из yfinance
        data = yf.download(sp500_tickers, period="1y")
        data = data.dropna(axis=1)['Close']
        if data.empty:
            raise ValueError("Нет данных по закрытию акций.")
        
        # Выбор 10 лучших по моментуму
        months = 12
        momentum_returns = data.pct_change(periods=months * 21).iloc[-1]
        top_tickers = momentum_returns.nlargest(10).index.tolist()
        
        # Получаем текущие позиции
        try:
            positions = trading_client.get_all_positions()
            current_positions = {pos.symbol: float(pos.qty) for pos in positions}
        except Exception as e:
            print(f"Ошибка при получении текущих позиций: {e}")
            current_positions = {}
        
        # Закрываем позиции, которых нет в новом списке
        for ticker in list(current_positions.keys()):
            if ticker not in top_tickers:
                try:
                    trading_client.close_position(ticker)
                    print(f"Позиция {ticker} закрыта.")
                except Exception as e:
                    print(f"Ошибка при закрытии позиции {ticker}: {e}")
        
        # Получаем данные аккаунта для расчёта размера позиции
        account = trading_client.get_account()
        cash = float(account.cash)
        if len(top_tickers) == 0:
            raise ValueError("Ошибка: нет тикеров для покупки.")
        
        position_size = cash / len(top_tickers)
        
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
                    print(f"Позиция {ticker} открыта.")
                except Exception as e:
                    print(f"Ошибка при открытии позиции {ticker}: {e}")
        
        # Если выполнение дошло до сюда, считаем, что ребалансировка прошла успешно.
        mark_rebalance_done()
        print(f"{datetime.datetime.now()}: Ребалансировка завершена успешно.")
    except Exception as e:
        print(f"{datetime.datetime.now()}: Общая ошибка ребалансировки: {e}")
        # Можно добавить логирование ошибки или уведомление

# Механизм флага выполнения ребалансировки (используем файл)
def is_rebalance_done():
    try:
        with open("data/last_rebalance.txt", "r") as f:
            last_date = f.read().strip()
            if last_date == datetime.date.today().isoformat():
                return True
    except FileNotFoundError:
        return False
    return False

def mark_rebalance_done():
    with open("data/last_rebalance.txt", "w") as f:
        f.write(datetime.date.today().isoformat())

# Функция-обёртка для повторных попыток, если ребалансировка не выполнена
def rebalance_with_retries(max_retries=5, delay=300):
    attempts = 0
    while attempts < max_retries:
        if is_rebalance_done():
            print("Ребалансировка уже выполнена.")
            break
        print(f"Попытка ребалансировки #{attempts+1}")
        perform_rebalance()
        if is_rebalance_done():
            break
        attempts += 1
        print(f"Ожидание {delay} секунд перед следующей попыткой...")
        time.sleep(delay)
    if not is_rebalance_done():
        print("Ребалансировка не выполнена после максимального количества попыток.")

# Планирование задачи на 10:00 по нью-йоркскому времени
# Для работы с часовыми поясами можно использовать pytz, но для простоты примера будем считать, что сервер настроен на нужный TZ.
scheduler = BlockingScheduler()

@scheduler.scheduled_job('cron', hour=10, minute=0)
def scheduled_rebalance():
    print("Запущена запланированная ребалансировка.")
    rebalance_with_retries()

if __name__ == '__main__':
    try:
        print("Старт планировщика задач.")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Остановка планировщика задач.")