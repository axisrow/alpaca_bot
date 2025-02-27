import yfinance as yf
import logging
from datetime import datetime
import time
from typing import List, Dict
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
from functools import wraps

def retry_on_exception(retries: int = 3, delay: int = 1):
    """Декоратор для повторных попыток выполнения функции при исключении"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == retries - 1:
                        raise
                    logging.warning(f"Попытка {attempt + 1} не удалась: {e}")
                    time.sleep(delay)
            return None
        return wrapper
    return decorator

class MomentumStrategy:
    """Класс реализующий торговую стратегию на основе моментума"""
    
    def __init__(self, trading_client: TradingClient, tickers: List[str]):
        self.trading_client = trading_client
        self.tickers = tickers
        
    @retry_on_exception() 
    def get_signals(self) -> List[str]:
        """Получение торговых сигналов - топ-10 акций по моментуму"""
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
        """Получение текущих позиций"""
        positions = self.trading_client.get_all_positions()
        return {pos.symbol: float(pos.qty) for pos in positions}

    def close_positions(self, positions: List[str]) -> None:
        """Закрытие указанных позиций"""
        for ticker in positions:
            try:
                self.trading_client.close_position(ticker)
                logging.info(f"Позиция {ticker} закрыта")
            except Exception as e:
                logging.error(f"Ошибка закрытия позиции {ticker}: {e}")

    def open_positions(self, tickers: List[str], cash_per_position: float) -> None:
        """Открытие новых позиций"""
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
                logging.info(f"Открыта позиция {ticker} на ${cash_per_position:.2f}")
            except Exception as e:
                logging.error(f"Ошибка открытия позиции {ticker}: {e}")

    def rebalance(self) -> None:
        """Ребалансировка портфеля"""
        try:
            logging.info("Начало ребалансировки портфеля")
            
            # Получаем сигналы торговой стратегии
            top_tickers = self.get_signals()
            logging.info(f"Топ-10 акций по моментуму: {', '.join(top_tickers)}")
            
            # Получаем текущие позиции
            current_positions = self.get_positions()
            logging.info(f"Текущие позиции: {current_positions}")
            
            # Определяем позиции для закрытия и открытия
            positions_to_close = [ticker for ticker in current_positions if ticker not in top_tickers]
            positions_to_open = [ticker for ticker in top_tickers if ticker not in current_positions]
            
            logging.info(f"Позиции для закрытия: {positions_to_close}")
            logging.info(f"Позиции для открытия: {positions_to_open}")
            
            # Закрываем ненужные позиции
            if positions_to_close:
                self.close_positions(positions_to_close)
                time.sleep(5)
            
            # Открываем новые позиции
            if positions_to_open:
                account = self.trading_client.get_account()
                available_cash = float(account.cash)
                if available_cash <= 0:
                    logging.warning(f"Недостаточно средств: ${available_cash}")
                    return
                    
                position_size = available_cash / len(positions_to_open)
                if position_size < 1:
                    logging.warning(f"Размер позиции слишком мал: ${position_size}")
                    return
                    
                self.open_positions(positions_to_open, position_size)
            
            logging.info("Ребалансировка выполнена успешно")
            
        except Exception as e:
            logging.error(f"Ошибка при ребалансировке: {e}", exc_info=True)
