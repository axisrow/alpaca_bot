import os
import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
import yfinance as yf
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# API ключи
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
BASE_URL = "https://paper-api.alpaca.markets"

print(BASE_URL)

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

# Выбор 10 лучших по моментуму
months = 12
momentum_returns = data.pct_change(periods=months * 21).iloc[-1]
top_tickers = momentum_returns.nlargest(10).index.tolist()

# Получаем текущие позиции
current_positions = {pos.symbol: float(pos.qty) for pos in trading_client.get_all_positions()}

# Закрываем позиции, которых нет в новом списке
for ticker in current_positions:
    if ticker not in top_tickers:
        trading_client.close_position(ticker)

# Пересчитываем размер позиции
account = trading_client.get_account()
cash = float(account.cash)
position_size = cash / len(top_tickers)

# Исполнение ордеров
for ticker in top_tickers:
    if ticker not in current_positions:  # Покупаем только новые позиции
        order = MarketOrderRequest(
            symbol=ticker,
            notional=position_size,  # Указываем сумму, а не количество акций
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY
        )
        trading_client.submit_order(order)

print("Ребалансировка завершена.")