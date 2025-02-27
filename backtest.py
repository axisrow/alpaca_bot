import pandas as pd
import numpy as np
import yfinance as yf
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta

class BacktestEngine:
    """Класс для выполнения бэктеста торговой стратегии"""
    
    def __init__(self, tickers: List[str], initial_capital: float = 100000):
        self.tickers = tickers
        self.initial_capital = initial_capital
        
    def _load_data(self, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """Загрузка исторических данных"""
        try:
            # Добавляем месяц к начальной дате для расчета моментума
            start = pd.to_datetime(start_date) - pd.DateOffset(months=12)
            end = pd.to_datetime(end_date)
            
            # Загружаем данные небольшими группами чтобы избежать ошибок
            all_data = []
            chunk_size = 100
            for i in range(0, len(self.tickers), chunk_size):
                chunk = self.tickers[i:i + chunk_size]
                data_chunk = yf.download(
                    chunk,
                    start=start.strftime('%Y-%m-%d'),
                    end=end.strftime('%Y-%m-%d'),
                    auto_adjust=True,
                    progress=False  # Отключаем вывод прогресса
                )['Close']
                all_data.append(data_chunk)
            
            # Объединяем все данные
            data = pd.concat(all_data, axis=1)
            
            # Удаляем тикеры с отсутствующими данными
            data = data.dropna(axis=1, thresh=len(data) * 0.9)  # Оставляем только тикеры с 90% данных
            return data
            
        except Exception as e:
            logging.error(f"Ошибка загрузки данных: {e}")
            return None

    def _calculate_momentum(self, data: pd.DataFrame, lookback: int = 252) -> pd.Series:
        """Расчет моментума"""
        return data.pct_change(
            periods=lookback, 
            fill_method=None  # Исправляем предупреждение о fill_method
        ).iloc[-1].sort_values(ascending=False)

    def run(self, start_date: str, end_date: str) -> Dict:
        """Запуск бэктеста"""
        try:
            # Загружаем данные
            data = self._load_data(start_date, end_date)
            if data is None or data.empty:
                raise ValueError("Не удалось загрузить данные")

            # Инициализация переменных
            portfolio_value = self.initial_capital
            positions = {}
            trades_history = []
            daily_returns = []
            max_drawdown = 0
            peak = portfolio_value

            # Создаем временной ряд для ребалансировки (конец каждого месяца)
            dates = pd.date_range(
                start=start_date, 
                end=end_date, 
                freq='BME'  # Исправляем предупреждение о BM
            )

            # Проходим по датам ребалансировки
            for i, date in enumerate(dates):
                # Получаем данные до текущей даты
                current_data = data.loc[:date]
                
                # Рассчитываем моментум и получаем топ-10 акций
                momentum = self._calculate_momentum(current_data)
                top_tickers = momentum.head(10).index.tolist()

                # Закрываем старые позиции
                for ticker in list(positions.keys()):
                    if ticker not in top_tickers:
                        try:
                            close_price = current_data[ticker].iloc[-1]
                            trade_pnl = (close_price - positions[ticker]['entry_price']) * positions[ticker]['shares']
                            portfolio_value += trade_pnl
                            trades_history.append({
                                'date': date,
                                'ticker': ticker,
                                'type': 'SELL',
                                'pnl': trade_pnl
                            })
                            del positions[ticker]
                        except Exception as e:
                            logging.warning(f"Ошибка при закрытии позиции {ticker}: {e}")

                # Открываем новые позиции
                cash_per_position = portfolio_value / len(top_tickers) if top_tickers else 0
                for ticker in top_tickers:
                    if ticker not in positions:
                        try:
                            entry_price = current_data[ticker].iloc[-1]
                            shares = cash_per_position / entry_price
                            positions[ticker] = {
                                'entry_price': entry_price,
                                'shares': shares
                            }
                        except Exception as e:
                            logging.warning(f"Ошибка при открытии позиции {ticker}: {e}")

                # Рассчитываем стоимость портфеля и доходность
                try:
                    current_value = sum(
                        current_data[ticker].iloc[-1] * pos['shares']
                        for ticker, pos in positions.items()
                    )
                    daily_return = (current_value - portfolio_value) / portfolio_value
                    daily_returns.append(daily_return)
                    portfolio_value = current_value

                    # Обновляем максимальную просадку
                    peak = max(peak, portfolio_value)
                    drawdown = (peak - portfolio_value) / peak
                    max_drawdown = min(-drawdown, max_drawdown)
                except Exception as e:
                    logging.warning(f"Ошибка при расчете стоимости портфеля: {e}")

            # Рассчитываем метрики
            total_return = (portfolio_value - self.initial_capital) / self.initial_capital * 100
            sharpe_ratio = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252) if daily_returns else 0
            win_trades = len([t for t in trades_history if t.get('pnl', 0) > 0])
            total_trades = len(trades_history)

            return {
                'total_return': total_return,
                'sharpe_ratio': sharpe_ratio,
                'max_drawdown': max_drawdown * 100,
                'final_value': portfolio_value,
                'trades_count': total_trades,
                'winning_trades': win_trades
            }

        except Exception as e:
            logging.error(f"Ошибка при выполнении бэктеста: {e}")
            return None