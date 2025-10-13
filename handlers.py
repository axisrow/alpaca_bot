"""Модуль с обработчиками команд Telegram бота."""
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from keyboards import main_kb, menu_kb


def setup_router(trading_bot):
    """Настройка роутера с доступом к TradingBot.

    Args:
        trading_bot: Экземпляр торгового бота

    Returns:
        Router: Настроенный роутер с обработчиками
    """
    router = Router()

    @router.message(Command("start"))
    async def cmd_start(message: Message):
        """Обработчик команды /start."""
        await message.answer(
            "Привет! Я ваш торговый бот-помощник.\n"
            "Используйте меню для управления торговлей.",
            reply_markup=main_kb
        )

    @router.message(Command("help"))
    async def cmd_help(message: Message):
        """Обработчик команды /help."""
        await message.answer(
            "Список доступных команд:\n"
            "/start - Начать работу\n"
            "/help - Показать помощь\n\n"
            "Через меню доступны функции:\n"
            "📊 Портфель - просмотр текущих позиций\n"
            "📈 Статистика - просмотр торговой статистики\n"
            "⚙️ Настройки - настройка параметров бота"
        )

    @router.message(F.text == "📋 Меню")
    async def show_menu(message: Message):
        """Обработчик кнопки 'Меню'."""
        await message.answer(
            "Выберите действие:",
            reply_markup=menu_kb
        )

    @router.message(F.text == "ℹ️ Информация")
    async def show_info(message: Message):
        """Обработчик кнопки 'Информация'."""
        await message.answer(
            "Торговый бот для автоматической торговли на бирже.\n"
            "Стратегия: Momentum Trading\n"
            "Ребалансировка: ежедневно в 10:00 (NY)\n"
            "Используется API Alpaca Markets"
        )

    @router.callback_query(F.data == "portfolio_status")
    async def show_portfolio(callback: CallbackQuery):
        """Обработчик кнопки 'Портфель'."""
        await callback.answer()
        try:
            # Получаем данные о портфеле из TradingBot
            positions, account, account_pnl = trading_bot.get_portfolio_status()

            # Проверяем, что данные получены корректно
            if not account:
                raise ValueError("Не удалось получить данные аккаунта")

            # Формируем сообщение
            msg = "Статус портфеля:\n\n"

            if positions:
                msg += "Позиции:\n"
                for symbol, qty in positions.items():
                    # Получаем рыночную стоимость позиции
                    all_positions = trading_bot.trading_client.get_all_positions()
                    position = next((p for p in all_positions
                                     if p.symbol == symbol), None)
                    if position:
                        value = float(position.market_value)
                        msg += (f"{symbol} – {float(qty):.2f} шт. "
                                f"(${value:.2f})\n")
                    else:
                        msg += (f"{symbol} – {float(qty):.2f} шт. "
                                f"(нет данных о стоимости)\n")
            else:
                msg += "Позиции: нет открытых позиций\n"

            msg += "\nПротфель:\n"
            msg += f"Итого: {float(account.portfolio_value):.2f}\n"
            msg += f"\nP&L: ${account_pnl:.2f}"

            await callback.message.answer(msg)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Ошибка при получении данных портфеля: %s", exc)
            await callback.message.answer(
                "❌ Ошибка при получении данных портфеля"
            )

    @router.callback_query(F.data == "trading_stats")
    async def show_stats(callback: CallbackQuery):
        """Обработчик кнопки 'Статистика'."""
        await callback.answer()
        try:
            # Получаем статистику из TradingBot
            stats = trading_bot.get_trading_stats()

            # Проверяем, что статистика получена
            if not stats:
                raise ValueError("Статистика недоступна")

            msg = "Торговая статистика:\n"
            msg += f"Сделок за сегодня: {stats.get('trades_today', 0)}\n"
            msg += f"Прибыль/убыток: ${stats.get('pnl', 0.0):.2f}\n"
            msg += f"Win rate: {stats.get('win_rate', 0.0):.2f}%"
            await callback.message.answer(msg)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Ошибка при получении торговой статистики: %s", exc)
            await callback.message.answer(
                "❌ Ошибка при получении торговой статистики"
            )

    @router.callback_query(F.data == "settings")
    async def show_settings(callback: CallbackQuery):
        """Обработчик кнопки 'Настройки'."""
        await callback.answer()
        try:
            # Получаем настройки из TradingBot
            settings = trading_bot.get_settings()

            # Проверяем, что настройки получены
            if not settings:
                raise ValueError("Настройки недоступны")

            msg = "Настройки бота:\n"
            msg += (f"- Время ребалансировки: "
                    f"{settings.get('rebalance_time', 'не задано')}\n")
            msg += (f"- Количество позиций: "
                    f"{settings.get('positions_count', 0)}\n")
            msg += f"- Режим: {settings.get('mode', 'не задан')}"
            await callback.message.answer(msg)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Ошибка при получении настроек: %s", exc)
            await callback.message.answer("❌ Ошибка при получении настроек")

    @router.message()
    async def echo(message: Message):
        """Обработчик всех остальных сообщений."""
        await message.answer(
            "Используйте кнопки меню или команды для управления ботом.\n"
            "Для помощи введите /help"
        )

    return router
