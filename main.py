from pathlib import Path
from functools import wraps
import os
import sys
import time
import signal
from datetime import datetime, time as dt_time
import logging
from dataclasses import dataclass
import pytz
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
import yfinance as yf
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from typing import List, Dict, Tuple
from handlers import setup_router  # Исправленный импорт

import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from config import sp500_tickers, TELEGRAM_BOT_TOKEN

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('data/trading_bot.log')
    ]
)

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

@dataclass
class RebalanceFlag:
    """Класс для работы с флагом ребалансировки"""
    flag_path: Path = Path("data/last_rebalance.txt")

    def has_rebalanced_today(self) -> bool:
        """Проверяет, была ли ребалансировка сегодня"""
        if not self.flag_path.exists():
            return False
        return self.flag_path.read_text().strip() == datetime.now().strftime("%Y-%m-%d")

    def write_flag(self) -> None:
        """Записывает флаг ребалансировки"""
        self.flag_path.parent.mkdir(parents=True, exist_ok=True)
        self.flag_path.write_text(datetime.now().strftime("%Y-%m-%d"))

class MarketSchedule:
    """Класс для работы с расписанием рынка"""
    NY_TIMEZONE = pytz.timezone('America/New_York')
    MARKET_OPEN = dt_time(9, 30)
    MARKET_CLOSE = dt_time(16, 0)

    def __init__(self, trading_client: TradingClient):
        self.trading_client = trading_client

    @property
    def current_ny_time(self) -> datetime:
        """Текущее время в Нью-Йорке"""
        return datetime.now(self.NY_TIMEZONE)

    def check_market_status(self) -> Tuple[bool, str]:
        """Проверяет статус рынка"""
        now = self.current_ny_time
        current_time = now.time()

        if now.weekday() > 4:
            return False, "выходной день (суббота/воскресенье)"

        try:
            clock = self.trading_client.get_clock()
            if clock.is_open:
                return True, "рынок открыт"

            if self.MARKET_OPEN <= current_time <= self.MARKET_CLOSE:
                return False, "праздничный день"
            return False, f"время вне сессии {self.MARKET_OPEN}-{self.MARKET_CLOSE}"

        except Exception as e:
            logging.error(f"Ошибка проверки статуса рынка: {e}")
            return False, str(e)

    @property
    def is_open(self) -> bool:
        """Проверяет, открыт ли рынок"""
        is_open, reason = self.check_market_status()
        if not is_open:
            logging.info(f"Рынок закрыт: {reason}")
        return is_open

class PortfolioManager:
    """Класс для управления портфелем"""
    def __init__(self, trading_client: TradingClient):
        self.trading_client = trading_client

    @retry_on_exception()
    def get_momentum_tickers(self) -> List[str]:
        """Получение топ-10 акций по моментуму"""
        data = yf.download(sp500_tickers, period="1y", timeout=30)
        if 'Close' not in data.columns:
            raise KeyError("Столбец 'Close' отсутствует в данных")

        momentum_returns = (
            data['Close']
            .dropna(axis=1)
            .pct_change(periods=12 * 21)
            .iloc[-1]
            .nlargest(10)
        )
        return momentum_returns.index.tolist()

    @retry_on_exception()
    def get_current_positions(self) -> Dict[str, float]:
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
                    notional=cash_per_position,
                    side=OrderSide.BUY,
                    type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY
                )
                self.trading_client.submit_order(order)
                logging.info(f"Открыта позиция {ticker} на ${cash_per_position:.2f}")
            except Exception as e:
                logging.error(f"Ошибка открытия позиции {ticker}: {e}")

class TradingBot:
    """Основной класс торгового бота"""
    def __init__(self):
        self._load_environment()
        self.trading_client = self._setup_trading_client()
        self.market_schedule = MarketSchedule(self.trading_client)
        self.portfolio_manager = PortfolioManager(self.trading_client)
        self.rebalance_flag = RebalanceFlag()
        self.scheduler = BackgroundScheduler()

    def _load_environment(self):
        """Загрузка переменных окружения"""
        load_dotenv()
        self.api_key = os.getenv("ALPACA_API_KEY")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY")
        self.base_url = "https://paper-api.alpaca.markets"

        if not self.api_key or not self.secret_key:
            logging.error("Отсутствуют API ключи!")
            sys.exit(1)

    def _setup_trading_client(self) -> TradingClient:
        """Создание клиента для торговли"""
        return TradingClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=True,
            url_override=self.base_url
        )

    def perform_rebalance(self):
        """Выполнение ребалансировки портфеля"""
        if self.rebalance_flag.has_rebalanced_today():
            logging.info("Ребалансировка уже произведена сегодня.")
            return

        is_open, reason = self.market_schedule.check_market_status()
        if not is_open:
            logging.info(f"Ребалансировка отложена: {reason}")
            return

        try:
            logging.info("Начало ребалансировки портфеля")
            top_tickers = self.portfolio_manager.get_momentum_tickers()
            logging.info(f"Топ-10 акций по моментуму: {', '.join(top_tickers)}")
            
            current_positions = self.portfolio_manager.get_current_positions()
            logging.info(f"Текущие позиции: {current_positions}")
            
            positions_to_close = [ticker for ticker in current_positions if ticker not in top_tickers]
            positions_to_open = [ticker for ticker in top_tickers if ticker not in current_positions]
            
            logging.info(f"Позиции для закрытия: {positions_to_close}")
            logging.info(f"Позиции для открытия: {positions_to_open}")
            
            if positions_to_close:
                self.portfolio_manager.close_positions(positions_to_close)
                time.sleep(5)
            
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
                self.portfolio_manager.open_positions(positions_to_open, position_size)
            
            logging.info("Ребалансировка выполнена успешно")
            self.rebalance_flag.write_flag()
        except Exception as e:
            logging.error(f"Ошибка при ребалансировке: {e}", exc_info=True)

    def start(self):
        """Запуск бота"""
        logging.info("=== Запуск торгового бота ===")
        is_open, reason = self.market_schedule.check_market_status()
        now_ny = datetime.now(MarketSchedule.NY_TIMEZONE)
        logging.info(f"Текущее время (NY): {now_ny.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logging.info(f"Статус рынка: {'открыт' if is_open else 'закрыт'}")
        if not is_open:
            logging.info(f"Причина: {reason}")
        if not self.scheduler.running:
            self.scheduler.add_job(
                self.perform_rebalance,
                'cron',
                day_of_week='mon-fri',
                hour=10,
                minute=0,
                timezone=MarketSchedule.NY_TIMEZONE
            )
            self.scheduler.start()
            logging.info("Планировщик запущен")
        else:
            logging.info("Планировщик уже запущен")
        if is_open:
            logging.info("Запуск первичной ребалансировки...")
            self.perform_rebalance()

    def stop(self):
        """Остановка планировщика"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logging.info("Планировщик остановлен")

    def get_portfolio_status(self):
        """Получение данных о портфеле"""
        try:
            positions = self.portfolio_manager.get_current_positions()
            account = self.trading_client.get_account()
            pnl = float(account.equity) - float(account.last_equity)
            return positions, account, pnl
        except Exception as e:
            logging.error(f"Ошибка при получении данных портфеля: {e}")
            return {}, None, 0

    def get_trading_stats(self):
        """Получение торговой статистики"""
        try:
            # Здесь можно добавить реальную логику, например, запрос истории сделок
            trades_today = 5  # Замените на реальные данные
            pnl = 150.0       # Замените на реальные данные
            win_rate = 60.0   # Замените на реальные данные
            return {
                "trades_today": trades_today,
                "pnl": pnl,
                "win_rate": win_rate
            }
        except Exception as e:
            logging.error(f"Ошибка при получении торговой статистики: {e}")
            return {"trades_today": 0, "pnl": 0.0, "win_rate": 0.0}

    def get_settings(self):
        """Получение настроек бота"""
        return {
            "rebalance_time": "10:00 NY",
            "positions_count": 10,
            "mode": "Paper Trading"
        }

class TelegramBot:
    """Класс для Telegram бота"""
    def __init__(self, trading_bot: TradingBot):
        self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
        self.dp = Dispatcher()
        self.trading_bot = trading_bot
        self.router = setup_router(self.trading_bot)
        self.setup_handlers()

    async def stop(self):
        """Остановка Telegram бота"""
        logging.info("Останавливаем Telegram бот...")
        await self.dp.stop_polling()
        await self.dp.wait_closed()
        await self.bot.session.close()
        logging.info("Telegram бот остановлен")

    def setup_handlers(self):
        """Настройка обработчиков команд"""
        self.dp.include_router(self.router)  # Предполагается, что router настроен корректно

    async def start(self):
        """Запуск Telegram бота"""
        logging.info("=== Запуск Telegram бота ===")
        await self.bot.set_my_commands([
            BotCommand(command="start", description="Начать работу"),
            BotCommand(command="help", description="Помощь"),
        ])
        await self.dp.start_polling(self.bot)

async def main():
    """Основная функция программы"""
    trading_bot = TradingBot()
    telegram_bot = TelegramBot(trading_bot)

    # Запуск торгового бота (запускает планировщик)
    trading_bot.start()

    # Запуск Telegram бота в асинхронной задаче
    telegram_task = asyncio.create_task(telegram_bot.start())

    # Настройка обработчиков сигналов
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(shutdown(trading_bot, telegram_bot))
        )

    try:
        await telegram_task
    except asyncio.CancelledError:
        logging.info("Telegram task cancelled")

async def shutdown(trading_bot, telegram_bot):
    """Корректное завершение всех компонентов"""
    logging.info("Shutting down...")
    trading_bot.stop()
    await telegram_bot.stop()
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    logging.info("Shutdown complete")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Получен сигнал завершения работы (KeyboardInterrupt)")
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}", exc_info=True)
    finally:
        logging.info("Программа завершена")