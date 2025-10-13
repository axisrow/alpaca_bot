"""Основной модуль торгового бота с Telegram интерфейсом."""
import asyncio
import logging
import os
import signal
import sys
from dataclasses import dataclass
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Dict, List, Tuple

import pytz
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce, QueryOrderStatus
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

from config import snp500_tickers, TELEGRAM_BOT_TOKEN, ADMIN_IDS
from handlers import setup_router
from strategy import MomentumStrategy
from utils import retry_on_exception

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('data/trading_bot.log')
    ]
)


@dataclass
class RebalanceFlag:
    """Класс для работы с флагом ребалансировки."""

    flag_path: Path = Path("data/last_rebalance.txt")

    def has_rebalanced_today(self) -> bool:
        """Проверяет, была ли ребалансировка сегодня."""
        if not self.flag_path.exists():
            return False
        return (self.flag_path.read_text(encoding='utf-8').strip() ==
                datetime.now().strftime("%Y-%m-%d"))

    def write_flag(self) -> None:
        """Записывает флаг ребалансировки."""
        self.flag_path.parent.mkdir(parents=True, exist_ok=True)
        self.flag_path.write_text(
            datetime.now().strftime("%Y-%m-%d"),
            encoding='utf-8'
        )


class MarketSchedule:
    """Класс для работы с расписанием рынка."""

    NY_TIMEZONE = pytz.timezone('America/New_York')
    MARKET_OPEN = dt_time(9, 30)
    MARKET_CLOSE = dt_time(16, 0)

    def __init__(self, trading_client: TradingClient):
        """Инициализация с торговым клиентом.

        Args:
            trading_client: Клиент для работы с Alpaca API
        """
        self.trading_client = trading_client

    @property
    def current_ny_time(self) -> datetime:
        """Текущее время в Нью-Йорке."""
        return datetime.now(self.NY_TIMEZONE)

    def check_market_status(self) -> Tuple[bool, str]:
        """Проверяет статус рынка.

        Returns:
            Tuple[bool, str]: Статус открытия рынка и причина
        """
        now = self.current_ny_time
        current_time = now.time()

        if now.weekday() > 4:
            return False, "выходной день (суббота/воскресенье)"

        try:
            clock = self.trading_client.get_clock()
            if clock.is_open:  # type: ignore[attr-defined]
                return True, "рынок открыт"

            if self.MARKET_OPEN <= current_time <= self.MARKET_CLOSE:
                return False, "праздничный день"
            return (False,
                    f"время вне сессии {self.MARKET_OPEN}-{self.MARKET_CLOSE}")

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Ошибка проверки статуса рынка: %s", exc)
            return False, str(exc)

    @property
    def is_open(self) -> bool:
        """Проверяет, открыт ли рынок."""
        is_open, reason = self.check_market_status()
        if not is_open:
            logging.info("Рынок закрыт: %s", reason)
        return is_open


class PortfolioManager:
    """Класс для управления портфелем."""

    def __init__(self, trading_client: TradingClient):
        """Инициализация менеджера портфеля.

        Args:
            trading_client: Клиент для работы с Alpaca API
        """
        self.trading_client = trading_client
        self.strategy = MomentumStrategy(self.trading_client, snp500_tickers)

    @retry_on_exception()
    def get_current_positions(self) -> Dict[str, float]:
        """Получение текущих позиций.

        Returns:
            Dict[str, float]: Словарь позиций {тикер: количество}
        """
        positions = self.trading_client.get_all_positions()
        return {pos.symbol: float(pos.qty) for pos in positions}  # type: ignore[attr-defined]

    def close_positions(self, positions: List[str]) -> None:
        """Закрытие указанных позиций.

        Args:
            positions: Список тикеров для закрытия
        """
        for ticker in positions:
            try:
                self.trading_client.close_position(ticker)
                logging.info("Позиция %s закрыта", ticker)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.error("Ошибка закрытия позиции %s: %s", ticker, exc)

    def open_positions(self, tickers: List[str],
                       cash_per_position: float) -> None:
        """Открытие новых позиций.

        Args:
            tickers: Список тикеров для открытия
            cash_per_position: Размер позиции в долларах
        """
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
                logging.info(
                    "Открыта позиция %s на $%.2f",
                    ticker,
                    cash_per_position
                )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.error("Ошибка открытия позиции %s: %s", ticker, exc)


class TradingBot:
    """Основной класс торгового бота."""

    def __init__(self):
        """Инициализация торгового бота."""
        self._load_environment()
        self.trading_client = self._setup_trading_client()
        self.market_schedule = MarketSchedule(self.trading_client)
        self.portfolio_manager = PortfolioManager(self.trading_client)
        self.rebalance_flag = RebalanceFlag()
        self.scheduler = BackgroundScheduler()

    def _load_environment(self) -> None:
        """Загрузка переменных окружения."""
        load_dotenv()
        self.api_key = os.getenv("ALPACA_API_KEY")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY")
        self.base_url = "https://paper-api.alpaca.markets"

        if not self.api_key or not self.secret_key:
            logging.error("Отсутствуют API ключи!")
            sys.exit(1)

    def _setup_trading_client(self) -> TradingClient:
        """Создание клиента для торговли.

        Returns:
            TradingClient: Настроенный клиент Alpaca
        """
        return TradingClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=True,
            url_override=self.base_url
        )

    def perform_rebalance(self) -> None:
        """Выполнение ребалансировки портфеля."""
        if self.rebalance_flag.has_rebalanced_today():
            logging.info("Ребалансировка уже произведена сегодня.")
            return

        is_open, reason = self.market_schedule.check_market_status()
        if not is_open:
            logging.info("Ребалансировка отложена: %s", reason)
            return

        # Вызываем ребалансировку напрямую через стратегию
        self.portfolio_manager.strategy.rebalance()
        self.rebalance_flag.write_flag()

    def start(self) -> None:
        """Запуск бота."""
        logging.info("=== Запуск торгового бота ===")
        is_open, reason = self.market_schedule.check_market_status()
        now_ny = datetime.now(MarketSchedule.NY_TIMEZONE)
        logging.info(
            "Текущее время (NY): %s",
            now_ny.strftime('%Y-%m-%d %H:%M:%S %Z')
        )
        logging.info("Статус рынка: %s", 'открыт' if is_open else 'закрыт')
        if not is_open:
            logging.info("Причина: %s", reason)
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

    def stop(self) -> None:
        """Остановка планировщика."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logging.info("Планировщик остановлен")

    def get_portfolio_status(self) -> Tuple[Dict[str, float], object, float]:
        """Получение детальных данных о портфеле.

        Returns:
            Tuple: (позиции, аккаунт, P&L)
        """
        try:
            positions = self.portfolio_manager.get_current_positions()
            account = self.trading_client.get_account()
            all_positions = self.trading_client.get_all_positions()
            account_pnl = sum(float(pos.unrealized_pl)  # type: ignore[attr-defined]
                              for pos in all_positions)

            return positions, account, account_pnl

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Ошибка при получении данных портфеля: %s", exc)
            return {}, None, 0

    def get_trading_stats(self) -> Dict[str, float]:
        """Получение реальной торговой статистики.

        Returns:
            Dict[str, float]: Статистика торговли
        """
        try:
            # Получаем все сделки за сегодня
            today = datetime.now(MarketSchedule.NY_TIMEZONE).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            # Используем GetOrdersRequest для фильтрации
            request = GetOrdersRequest(
                status=QueryOrderStatus.CLOSED,
                after=today
            )
            trades = self.trading_client.get_orders(filter=request)
            trades_today = len(trades)

            # Считаем реальный P&L
            positions = self.trading_client.get_all_positions()
            total_pnl = sum(float(pos.unrealized_pl) for pos in positions)  # type: ignore[attr-defined]

            return {
                "trades_today": trades_today,
                "pnl": total_pnl,
                "win_rate": 0.0  # Упрощенная версия, win_rate требует анализа истории
            }
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Ошибка при получении торговой статистики: %s", exc)
            return {"trades_today": 0, "pnl": 0.0, "win_rate": 0.0}

    def get_settings(self) -> Dict[str, object]:
        """Получение настроек бота.

        Returns:
            Dict[str, object]: Словарь настроек
        """
        return {
            "rebalance_time": "10:00 NY",
            "positions_count": 10,
            "mode": "Paper Trading"
        }


class TelegramBot:
    """Класс для Telegram бота."""

    def __init__(self, trading_bot: TradingBot):
        """Инициализация Telegram бота.

        Args:
            trading_bot: Экземпляр торгового бота
        """
        assert TELEGRAM_BOT_TOKEN is not None, "TELEGRAM_BOT_TOKEN must be set"
        self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
        self.dp = Dispatcher()
        self.trading_bot = trading_bot
        self.router = setup_router(self.trading_bot)
        self.setup_handlers()

    async def stop(self) -> None:
        """Остановка Telegram бота."""
        logging.info("Останавливаем Telegram бот...")
        await self.dp.stop_polling()
        await self.bot.session.close()
        logging.info("Telegram бот остановлен")

    def setup_handlers(self) -> None:
        """Настройка обработчиков команд."""
        self.dp.include_router(self.router)

    async def send_startup_message(self) -> None:
        """Отправка сообщения администраторам при запуске бота."""
        if not ADMIN_IDS:
            logging.info("Список администраторов пуст, уведомления не отправлены")
            return

        # Получаем информацию о состоянии бота
        now_ny = datetime.now(MarketSchedule.NY_TIMEZONE)
        is_open, reason = self.trading_bot.market_schedule.check_market_status()

        message = (
            "🤖 <b>Бот запущен</b>\n\n"
            f"⏰ Время (NY): {now_ny.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"📊 Статус рынка: {'🟢 Открыт' if is_open else '🔴 Закрыт'}\n"
        )

        if not is_open:
            message += f"💬 Причина: {reason}\n"

        message += (
            f"\n⚙️ Режим: {self.trading_bot.get_settings()['mode']}\n"
            f"📅 Ребалансировка: {self.trading_bot.get_settings()['rebalance_time']}\n"
            f"📈 Позиций: {self.trading_bot.get_settings()['positions_count']}\n"
        )

        # Отправляем сообщение каждому администратору
        for admin_id in ADMIN_IDS:
            try:
                await self.bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode="HTML"
                )
                logging.info("Стартовое сообщение отправлено администратору %s", admin_id)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.error(
                    "Ошибка отправки сообщения администратору %s: %s",
                    admin_id,
                    exc
                )

    async def start(self) -> None:
        """Запуск Telegram бота."""
        logging.info("=== Запуск Telegram бота ===")
        await self.bot.set_my_commands([
            BotCommand(command="start", description="Начать работу"),
            BotCommand(command="help", description="Помощь"),
        ])
        await self.dp.start_polling(self.bot)


async def main() -> None:
    """Основная функция программы."""
    trading_bot = TradingBot()
    telegram_bot = TelegramBot(trading_bot)

    # Запуск торгового бота (запускает планировщик)
    trading_bot.start()

    # Отправка стартового сообщения администраторам
    await telegram_bot.send_startup_message()

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


async def shutdown(trading_bot: TradingBot,
                   telegram_bot: TelegramBot) -> None:
    """Корректное завершение всех компонентов.

    Args:
        trading_bot: Экземпляр торгового бота
        telegram_bot: Экземпляр Telegram бота
    """
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
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logging.error("Критическая ошибка: %s", exc, exc_info=True)
    finally:
        logging.info("Программа завершена")
