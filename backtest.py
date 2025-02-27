import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import logging
from datetime import datetime, timedelta
from typing import List, Dict
from config import sp500_tickers
import yfinance as yf
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce

class BacktestTradingClient:
    """Имитация TradingClient для бэктестинга"""
    def __init__(self):
        self.positions = {}
        self.cash = 0
        
    def get_all_positions(self):
        class Position:
            def __init__(self, symbol, qty):
                self.symbol = symbol
                self.qty = qty
        return [Position(symbol, qty) for symbol, qty in self.positions.items()]
        
    def close_position(self, symbol):
        if symbol in self.positions:
            del self.positions[symbol]
            
    def get_account(self):
        class Account:
            def __init__(self, cash):
                self.cash = cash
        return Account(self.cash)
        
    def submit_order(self, order):
        self.positions[order['symbol']] = order['notional']
        self.cash -= order['notional']

class MomentumStrategy:
    """Класс реализующий торговую стратегию на основе моментума"""
    
    def __init__(self, trading_client: BacktestTradingClient, data: pd.DataFrame):
        self.trading_client = trading_client
        self.data = data
        
    def get_signals(self, current_date: pd.Timestamp) -> List[str]:
        """Получение торговых сигналов - топ-10 акций по моментуму"""
        historical_data = self.data[self.data.index <= current_date]
        momentum_returns = (
            historical_data
            .pct_change(periods=len(historical_data)-1, fill_method=None)
            .iloc[-1]
            .nlargest(10)
        )
        return momentum_returns.index.tolist()

    def get_positions(self) -> Dict[str, float]:
        """Получение текущих позиций"""
        positions = self.trading_client.get_all_positions()
        return {pos.symbol: float(pos.qty) for pos in positions}

    def rebalance(self, current_date: pd.Timestamp) -> None:
        """Ребалансировка портфеля"""
        try:
            # Получаем сигналы торговой стратегии
            top_tickers = self.get_signals(current_date)
            
            # Получаем текущие позиции
            current_positions = self.get_positions()
            
            # Определяем позиции для закрытия и открытия
            positions_to_close = [ticker for ticker in current_positions if ticker not in top_tickers]
            positions_to_open = [ticker for ticker in top_tickers if ticker not in current_positions]
            
            # Закрываем ненужные позиции
            for ticker in positions_to_close:
                self.trading_client.close_position(ticker)
            
            # Открываем новые позиции
            if positions_to_open:
                account = self.trading_client.get_account()
                available_cash = float(account.cash)
                if available_cash <= 0:
                    return
                    
                position_size = available_cash / len(positions_to_open)
                if position_size < 1:
                    return
                    
                for ticker in positions_to_open:
                    order = {
                        'symbol': ticker,
                        'notional': position_size
                    }
                    self.trading_client.submit_order(order)
            
        except Exception as e:
            logging.error(f"Ошибка при ребалансировке: {e}")

class MomentumBacktest:
    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.data = None
        self.spy_data = None
        
    def load_data(self, start_date: str) -> None:
        """Загрузка исторических данных с запасом в 1 год"""
        logging.info("Загрузка исторических данных...")
        
        # Добавляем год для расчета моментума
        from dateutil.parser import parse
        extended_start = (parse(start_date) - timedelta(days=365)).strftime('%Y-%m-%d')
        
        self.data = yf.download(sp500_tickers, start=extended_start)['Close']
        self.spy_data = yf.download('SPY', start=extended_start)['Close']
        
    def simulate_trades(self, start_date: str, end_date: str, rebalance_period: int = 21) -> None:
        """Симуляция торговли"""
        logging.info(f"Симуляция торговли за период {start_date} - {end_date}")
        
        # Фильтруем данные по указанному периоду
        mask = (self.data.index >= start_date) & (self.data.index <= end_date)
        trading_data = self.data[mask]
        
        # Инициализация для каждого периода
        trading_client = BacktestTradingClient()
        trading_client.cash = self.initial_capital
        strategy = MomentumStrategy(trading_client, self.data)
        self.portfolio_history = []
        
        # Симуляция торговли
        dates = trading_data.index
        rebalance_dates = dates[::rebalance_period]
        
        for date in rebalance_dates:
            # Расчет текущей стоимости портфеля
            portfolio_value = trading_client.cash
            current_prices = trading_data.loc[date]
            
            for symbol, qty in trading_client.positions.items():
                if symbol in current_prices:
                    portfolio_value += qty * current_prices[symbol]
            
            # Ребалансировка
            strategy.rebalance(date)
            
            self.portfolio_history.append({
                'date': date,
                'portfolio_value': portfolio_value
            })

    def plot_results(self) -> None:
        """Построение графика результатов"""
        df = pd.DataFrame(self.portfolio_history)
        df.set_index('date', inplace=True)
        
        # Добавляем бенчмарк (S&P 500)
        benchmark = pd.DataFrame(self.portfolio_history)
        benchmark.set_index('date', inplace=True)
        benchmark['SPY'] = benchmark['portfolio_value'].iloc[0] * (1 + self.spy_returns)
        
        plt.figure(figsize=(12, 6))
        plt.plot(df.index, df['portfolio_value'], label='Стратегия')
        plt.plot(benchmark.index, benchmark['SPY'], label='S&P 500', alpha=0.7)
        plt.title('Результаты бэктеста стратегии моментума')
        plt.xlabel('Дата')
        plt.ylabel('Стоимость портфеля')
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.savefig('backtest_results.png')
        plt.close()
        
    def calculate_metrics(self) -> Dict:
        """Расчет метрик производительности"""
        df = pd.DataFrame(self.portfolio_history)
        returns = df['portfolio_value'].pct_change()
        
        return {
            'Начальный капитал': self.initial_capital,
            'Конечный капитал': df['portfolio_value'].iloc[-1],
            'Общая доходность': (df['portfolio_value'].iloc[-1] / self.initial_capital - 1) * 100,
            'Годовая доходность': returns.mean() * 252 * 100,
            'Волатильность': returns.std() * np.sqrt(252) * 100,
            'Коэффициент Шарпа': (returns.mean() * 252) / (returns.std() * np.sqrt(252)),
            'Максимальная просадка': self.calculate_max_drawdown(df['portfolio_value']) * 100
        }
    
    @staticmethod
    def calculate_max_drawdown(equity_curve: pd.Series) -> float:
        """Расчет максимальной просадки"""
        rolling_max = equity_curve.expanding().max()
        drawdowns = equity_curve / rolling_max - 1
        return drawdowns.min()
        
    def run(self, start_date: str, end_date: str) -> Dict:
        """Запуск бэктеста"""
        # Получаем доходность SPY для сравнения
        spy_mask = (self.spy_data.index >= start_date) & (self.spy_data.index <= end_date)
        self.spy_returns = self.spy_data[spy_mask].pct_change()
        
        self.simulate_trades(start_date, end_date)
        self.plot_results()
        
        return self.calculate_metrics()

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    backtest = MomentumBacktest(initial_capital=100000)
    
    # Тестируем на разных периодах
    periods = [
        ('2020-01-01', '2021-01-01'),
        ('2021-01-01', '2022-01-01'),
        ('2022-01-01', '2023-01-01'),
        ('2023-01-01', '2024-01-01')
    ]
    
    # Загружаем данные один раз с запасом в год до начала первого периода
    earliest_start = min(start for start, _ in periods)
    backtest.load_data(earliest_start)
    
    # Запускаем бэктест для каждого периода
    for start_date, end_date in periods:
        print(f"\nРезультаты бэктеста за период {start_date} - {end_date}:")
        metrics = backtest.run(start_date, end_date)
        for metric, value in metrics.items():
            print(f"{metric}: {value:.2f}")
