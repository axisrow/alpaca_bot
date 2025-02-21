import os
import sys
import time
import signal
from datetime import datetime, time as dt_time, timedelta
import logging
import pytz
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
import yfinance as yf
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
from typing import List, Dict, Tuple

from config import sp500_tickers

def has_rebalanced_today(flag_path="data/last_rebalance.txt"):
    if os.path.exists(flag_path):
        with open(flag_path, "r") as f:
            last_date = f.read().strip()
        if last_date == datetime.now().strftime("%Y-%m-%d"):
            return True
    return False

def write_rebalance_flag(flag_path="data/last_rebalance.txt"):
    with open(flag_path, "w") as f:
        f.write(datetime.now().strftime("%Y-%m-%d"))

class MarketSchedule:
    """Класс для работы с расписанием рынка"""
    NY_TIMEZONE = pytz.timezone('America/New_York')
    MARKET_OPEN = dt_time(9, 30)
    MARKET_CLOSE = dt_time(16, 0)

    def __init__(self, trading_client: TradingClient):
        self.trading_client = trading_client

    def check_market_status(self) -> Tuple[bool, str]:
        """
        Проверяет статус рынка и возвращает кортеж (is_open, reason)
        is_open: bool - открыт ли рынок
        reason: str - причина, если рынок закрыт
        """
        now = datetime.now(self.NY_TIMEZONE)
        current_time = now.time()

        # Если выходной
        if now.weekday() > 4:
            return False, "выходной день (суббота/воскресенье)"

        try:
            clock = self.trading_client.get_clock()
            # Если рынок открыт, то все хорошо
            if clock.is_open:
                return True, "рынок открыт"
            else:
                # Если текущее время входит в торговую сессию, но рынок все равно закрыт,
                # то считаем, что это праздничный день
                if self.MARKET_OPEN <= current_time <= self.MARKET_CLOSE:
                    return False, "праздничный день"
                else:
                    return False, f"время за пределами торговой сессии {self.MARKET_OPEN}-{self.MARKET_CLOSE}"
        except Exception as e:
            logging.error(f"Ошибка при проверке состояния рынка: {e}")
            return False, f"ошибка проверки статуса рынка: {str(e)}"

    def is_market_open(self) -> bool:
        """Проверяет, открыт ли рынок"""
        is_open, reason = self.check_market_status()
        if not is_open:
            logging.info(f"Рынок закрыт: {reason}")
        return is_open

class TradingBot:
    """Основной класс торгового бота"""
    def __init__(self):
        self.setup_logging()
        self.load_environment()
        self.trading_client = self.setup_trading_client()
        self.market_schedule = MarketSchedule(self.trading_client)
        self.scheduler = BlockingScheduler()
        self.should_run = True
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame):
        """Обработчик сигналов для корректного завершения"""
        logging.info("Получен сигнал завершения. Останавливаем бота...")
        self.should_run = False
        if self.scheduler.running:
            self.scheduler.shutdown()
        sys.exit(0)

    @staticmethod
    def setup_logging():
        """Настройка логирования"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('data/trading_bot.log')
            ]
        )

    def load_environment(self):
        """Загрузка переменных окружения"""
        load_dotenv()
        self.api_key = os.getenv("ALPACA_API_KEY")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY")
        self.base_url = "https://paper-api.alpaca.markets"

        if not self.api_key or not self.secret_key:
            logging.error("Отсутствуют API ключи!")
            sys.exit(1)

    def setup_trading_client(self) -> TradingClient:
        """Создание клиента для торговли"""
        return TradingClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=True,
            url_override=self.base_url
        )

    def get_momentum_tickers(self) -> List[str]:
        """Получение топ-10 акций по моментуму"""
        data = yf.download(sp500_tickers, period="1y", timeout=30)
        if 'Close' not in data.columns:
            raise KeyError("Столбец 'Close' отсутствует в данных")
        
        data = data.dropna(axis=1)['Close']
        momentum_returns = data.pct_change(periods=12 * 21).iloc[-1]
        return momentum_returns.nlargest(10).index.tolist()

    def get_current_positions(self) -> Dict[str, float]:
        """Получение текущих позиций"""
        positions = self.trading_client.get_all_positions()
        return {pos.symbol: float(pos.qty) for pos in positions}

    def close_positions(self, positions_to_close: List[str]):
        """Закрытие указанных позиций"""
        for ticker in positions_to_close:
            try:
                self.trading_client.close_position(ticker)
                logging.info(f"Позиция {ticker} закрыта")
            except Exception as e:
                logging.error(f"Ошибка при закрытии позиции {ticker}: {e}")

    def open_positions(self, tickers: List[str], position_size: float):
        """Открытие новых позиций"""
        for ticker in tickers:
            try:
                order = MarketOrderRequest(
                    symbol=ticker,
                    notional=position_size,
                    side=OrderSide.BUY,
                    type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY
                )
                self.trading_client.submit_order(order)
                logging.info(f"Позиция {ticker} открыта")
            except Exception as e:
                logging.error(f"Ошибка при открытии позиции {ticker}: {e}")

    def perform_rebalance(self):
        """Выполнение ребалансировки портфеля"""
        if has_rebalanced_today():
            logging.info("Ребалансировка уже произведена сегодня.")
            return

        is_open, reason = self.market_schedule.check_market_status()
        if not is_open:
            logging.info(f"Ребалансировка отложена: {reason}")
            return

        try:
            logging.info("Начало ребалансировки портфеля")
            
            # 1. Получение топ-10 акций по моментуму
            top_tickers = self.get_momentum_tickers()
            logging.info(f"Топ-10 акций по моментуму: {', '.join(top_tickers)}")
            
            # 2. Получение текущих позиций
            try:
                current_positions = self.get_current_positions()
                logging.info(f"Текущие позиции: {current_positions}")
            except Exception as e:
                logging.error(f"Ошибка при получении текущих позиций: {e}")
                return

            # 3. Определяем позиции для закрытия (те, которых нет в топ-10)
            positions_to_close = [ticker for ticker in current_positions if ticker not in top_tickers]
            positions_to_open = [ticker for ticker in top_tickers if ticker not in current_positions]

            logging.info(f"Позиции для закрытия: {', '.join(positions_to_close) if positions_to_close else 'нет'}")
            logging.info(f"Позиции для открытия: {', '.join(positions_to_open) if positions_to_open else 'нет'}")

            # Если изменений нет, выходим
            if not positions_to_close and not positions_to_open:
                logging.info("Изменений в позициях нет. Ребалансировка не требуется.")
                write_rebalance_flag()
                return

            # 4. Закрываем ненужные позиции
            if positions_to_close:
                for ticker in positions_to_close:
                    try:
                        self.trading_client.close_position(ticker)
                        logging.info(f"Позиция {ticker} закрыта")
                    except Exception as e:
                        logging.error(f"Ошибка при закрытии позиции {ticker}: {e}")

                # Ждем обновления баланса
                time.sleep(5)

            # 5. Открываем новые позиции
            if positions_to_open:
                # Проверяем доступные средства
                account = self.trading_client.get_account()
                available_cash = float(account.cash)
                
                if available_cash <= 0:
                    logging.warning(f"Недостаточно средств для открытия новых позиций. Доступные средства: ${available_cash}")
                    return

                position_size = available_cash / len(positions_to_open)
                
                if position_size < 1:
                    logging.warning(f"Размер позиции слишком мал: ${position_size}")
                    return

                logging.info(f"Открытие {len(positions_to_open)} новых позиций, размер каждой: ${position_size:.2f}")
                
                for ticker in positions_to_open:
                    try:
                        order = MarketOrderRequest(
                            symbol=ticker,
                            notional=position_size,
                            side=OrderSide.BUY,
                            type=OrderType.MARKET,
                            time_in_force=TimeInForce.DAY
                        )
                        self.trading_client.submit_order(order)
                        logging.info(f"Позиция {ticker} открыта на сумму ${position_size:.2f}")
                    except Exception as e:
                        logging.error(f"Ошибка при открытии позиции {ticker}: {e}")

            logging.info("Ребалансировка выполнена успешно")
            write_rebalance_flag()
            
        except Exception as e:
            logging.error(f"Ошибка при ребалансировке: {e}")

    def start(self):
        """Запуск бота"""
        logging.info("=== Запуск торгового бота ===")
        
        # Проверка состояния рынка
        is_open, reason = self.market_schedule.check_market_status()
        now_ny = datetime.now(MarketSchedule.NY_TIMEZONE)
        
        logging.info(f"Текущее время (NY): {now_ny.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logging.info(f"Статус рынка: {'открыт' if is_open else 'закрыт'}")
        if not is_open:
            logging.info(f"Причина: {reason}")

        # Планирование ребалансировки на 10:00 (NY) в будние дни
        self.scheduler.add_job(
            self.perform_rebalance,
            'cron',
            day_of_week='mon-fri',
            hour=10,
            minute=0,
            timezone=MarketSchedule.NY_TIMEZONE
        )
        
        # Первичная проверка сразу, если рынок открыт
        if is_open:
            logging.info("Запуск первичной ребалансировки...")
            self.perform_rebalance()
        
        try:
            logging.info("Планировщик запущен")
            while self.should_run:
                try:
                    self.scheduler.start()
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logging.error(f"Ошибка в планировщике: {e}")
                    time.sleep(60)  # Подождем минуту перед повторной попыткой
        except Exception as e:
            logging.error(f"Критическая ошибка: {e}")
        finally:
            logging.info("Бот остановлен")
            if self.scheduler.running:
                self.scheduler.shutdown()

if __name__ == '__main__':
    bot = TradingBot()
    bot.start()