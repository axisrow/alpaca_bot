from pathlib import Path
from functools import wraps
import os
import sys
import time
import signal
from datetime import datetime, time as dt_time, timedelta
import logging
from dataclasses import dataclass
import pytz
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
import yfinance as yf
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
from typing import List, Dict, Tuple, Optional

from config import sp500_tickers

import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, CallbackQuery
from aiogram import F
from handlers import router
from config import TELEGRAM_BOT_TOKEN

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
        self._setup_logging()
        self._load_environment()
        self.trading_client = self._setup_trading_client()
        self.market_schedule = MarketSchedule(self.trading_client)
        self.portfolio_manager = PortfolioManager(self.trading_client)
        self.rebalance_flag = RebalanceFlag()
        self.scheduler = BlockingScheduler()
        self.should_run = True
        
        # Установка обработчиков сигналов
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Обработчик сигналов для корректного завершения"""
        logging.info("Получен сигнал завершения. Останавливаем бота...")
        self.should_run = False
        if self.scheduler.running:
            self.scheduler.shutdown()
        sys.exit(0)

    @staticmethod
    def _setup_logging():
        """Настройка логирования"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('data/trading_bot.log')
            ]
        )

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
            
            # 1. Получение топ-10 акций по моментуму
            top_tickers = self.portfolio_manager.get_momentum_tickers()
            logging.info(f"Топ-10 акций по моментуму: {', '.join(top_tickers)}")
            
            # 2. Получение текущих позиций
            try:
                current_positions = self.portfolio_manager.get_current_positions()
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
                self.rebalance_flag.write_flag()
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
            self.rebalance_flag.write_flag()
            
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

class TelegramBot:
    def __init__(self, trading_bot: TradingBot):
        self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
        self.dp = Dispatcher()
        self.trading_bot = trading_bot
        self.should_run = True
        self.setup_handlers()

    async def stop(self):
        """Остановка Telegram бота"""
        logging.info("Останавливаем Telegram бота...")
        self.should_run = False
        await self.bot.session.close()

    def setup_handlers(self):
        @self.dp.callback_query(F.data == "portfolio_status")
        async def show_portfolio(callback: CallbackQuery):
            await callback.answer()
            try:
                positions = self.trading_bot.portfolio_manager.get_current_positions()
                account = self.trading_bot.trading_client.get_account()
                
                msg = "📊 Статус портфеля:\n\n"
                total_positions_value = 0
                
                if positions:
                    # Получаем все позиции одним запросом
                    all_positions = self.trading_bot.trading_client.get_all_positions()
                    positions_dict = {p.symbol: p for p in all_positions}
                    
                    for symbol, qty in positions.items():
                        if symbol in positions_dict:
                            position = positions_dict[symbol]
                            position_value = float(position.market_value)
                            total_positions_value += position_value
                            msg += f"• {symbol}: {qty:.2f} шт. (${position_value:.2f})\n"
                else:
                    msg += "Открытых позиций нет\n"
                
                equity = float(account.equity)
                cash = float(account.cash)
                
                msg += f"\n💰 Доступные средства: ${cash:.2f}\n"
                msg += f"📈 Общая стоимость позиций: ${total_positions_value:.2f}\n"
                msg += f"💵 Эквити: ${equity:.2f}\n"
                msg += f"📊 P&L за сегодня: ${float(account.equity) - float(account.last_equity):.2f}"
                
                await callback.message.answer(msg)
            except Exception as e:
                logging.error(f"Ошибка при получении данных портфеля: {e}")
                await callback.message.answer("❌ Ошибка при получении данных портфеля")

        @self.dp.callback_query(F.data == "trading_stats")
        async def show_stats(callback: CallbackQuery):
            await callback.answer()
            try:
                account = self.trading_bot.trading_client.get_account()
                
                equity = float(account.equity)
                cash = float(account.cash)
                pnl = float(account.equity) - float(account.last_equity)
                pnl_percentage = (pnl / float(account.last_equity)) * 100 if float(account.last_equity) != 0 else 0
                
                # Получаем общую стоимость позиций
                total_positions_value = 0
                all_positions = self.trading_bot.trading_client.get_all_positions()
                
                for position in all_positions:
                    total_positions_value += float(position.market_value)
                
                msg = "📈 Торговая статистика:\n\n"
                msg += f"💵 Общий баланс (эквити): ${equity:.2f}\n"
                msg += f"💰 Доступные средства: ${cash:.2f}\n"
                msg += f"📊 Стоимость позиций: ${total_positions_value:.2f}\n"
                msg += f"📈 P&L сегодня: ${pnl:.2f} ({pnl_percentage:.2f}%)\n"
                msg += f"🏁 Начальный баланс дня: ${float(account.last_equity):.2f}"
                
                await callback.message.answer(msg)
            except Exception as e:
                error_msg = f"Ошибка при получении статистики: {str(e)}"
                logging.error(error_msg)
                await callback.message.answer("❌ Ошибка при получении статистики")

        @self.dp.callback_query(F.data == "settings")
        async def show_settings(callback: CallbackQuery):
            await callback.answer()
            msg = "⚙️ Настройки бота:\n\n"
            msg += f"🕙 Время ребалансировки: 10:00 NY\n"
            msg += f"📊 Количество позиций: 10\n"
            msg += f"🏦 Режим: Paper Trading\n"
            msg += f"🌎 Рынок: {'открыт' if self.trading_bot.market_schedule.is_open else 'закрыт'}"
            
            await callback.message.answer(msg)

        # Добавляем роутер с базовыми командами
        self.dp.include_router(router)

    async def start(self):
        """Запуск Telegram бота"""
        logging.info("=== Запуск Telegram бота ===")
        
        # Установка команд бота
        await self.bot.set_my_commands([
            BotCommand(command="start", description="Начать работу"),
            BotCommand(command="help", description="Помощь"),
        ])
        
        # Запуск бота
        await self.dp.start_polling(self.bot)

if __name__ == '__main__':
    # Создаем экземпляры ботов
    trading_bot = TradingBot()
    telegram_bot = TelegramBot(trading_bot)
    
    async def shutdown(signal, loop):
        """Корректное завершение работы"""
        logging.info(f"Получен сигнал завершения: {signal.name}")
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        
        # Останавливаем торгового бота
        trading_bot.should_run = False
        if trading_bot.scheduler.running:
            trading_bot.scheduler.shutdown()
        
        # Останавливаем телеграм бота
        await telegram_bot.stop()
        
        # Отменяем все оставшиеся задачи
        [task.cancel() for task in tasks]
        logging.info(f"Отмена {len(tasks)} задач")
        await asyncio.gather(*tasks, return_exceptions=True)
        loop.stop()

    async def main():
        # Установка обработчиков сигналов
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(shutdown(s, loop))
            )
        
        # Запуск ботов
        trading_task = asyncio.create_task(
            asyncio.to_thread(trading_bot.start)
        )
        telegram_task = asyncio.create_task(
            telegram_bot.start()
        )
        
        try:
            await asyncio.gather(trading_task, telegram_task)
        except asyncio.CancelledError:
            logging.info("Задачи отменены")
        finally:
            loop.stop()
    
    # Запускаем асинхронное выполнение
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Получен сигнал завершения работы")
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")
    finally:
        logging.info("Боты остановлены")