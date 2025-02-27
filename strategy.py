from typing import List
import yfinance as yf
from functools import wraps
import time
import logging
from abc import ABC, abstractmethod

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

class TradingStrategy(ABC):
    """Абстрактный базовый класс для торговых стратегий"""
    
    @abstractmethod
    def get_momentum_tickers(self) -> List[str]:
        """Получение списка тикеров для торговли"""
        pass
    
    @abstractmethod
    def calculate_position_sizes(self, available_cash: float, num_positions: int) -> float:
        """Расчет размеров позиций"""
        pass

class MomentumStrategy(TradingStrategy):
    """Класс реализующий торговую стратегию на основе моментума"""
    
    def __init__(self, tickers: List[str], lookback_periods: int = 252, top_n: int = 10):
        self.tickers = tickers
        self.lookback_periods = lookback_periods  # ~ 1 год торговых дней
        self.top_n = top_n
    
    @retry_on_exception()
    def get_momentum_tickers(self) -> List[str]:
        """
        Получение топ-N акций по моментуму
        
        Returns:
            List[str]: Список тикеров с наилучшим моментумом
        """
        data = yf.download(self.tickers, period="1y", timeout=30)
        if 'Close' not in data.columns:
            raise KeyError("Столбец 'Close' отсутствует в данных")

        momentum_returns = (
            data['Close']
            .dropna(axis=1)
            .pct_change(periods=12 * 21)  # ~12 месяцев, учитывая ~21 торговый день в месяце
            .iloc[-1]
            .nlargest(self.top_n)
        )
        return momentum_returns.index.tolist()
    
    def calculate_position_sizes(self, available_cash: float, num_positions: int) -> float:
        """
        Расчет размера позиции для каждой акции
        
        Args:
            available_cash (float): Доступные средства
            num_positions (int): Количество позиций
            
        Returns:
            float: Размер одной позиции
        """
        if num_positions <= 0:
            return 0
        return available_cash / num_positions