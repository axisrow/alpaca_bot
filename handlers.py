"""Модуль с обработчиками команд Telegram бота."""
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardRemove


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
            "Введите /help для списка доступных команд.",
            reply_markup=ReplyKeyboardRemove()
        )

    @router.message(Command("help"))
    async def cmd_help(message: Message):
        """Обработчик команды /help."""
        await message.answer(
            "Список доступных команд:\n"
            "/start - Начать работу\n"
            "/help - Показать помощь\n"
            "/check_rebalance - Проверить дни до ребалансировки\n"
            "/info - Информация о боте\n"
            "/portfolio - Состояние портфеля\n"
            "/stats - Торговая статистика\n"
            "/settings - Настройки бота"
        )

    @router.message(Command("check_rebalance"))
    async def cmd_check_rebalance(message: Message):
        """Обработчик команды /check_rebalance."""
        try:
            days_until = trading_bot.calculate_days_until_rebalance()

            if days_until == 0:
                msg = (
                    "⏰ <b>Ребалансировка сегодня!</b>\n\n"
                    "🔄 Портфель будет переформирован на лучшие 10 акций S&P 500\n"
                    "⏱️ Время ребалансировки: 10:00 (NY)"
                )
            else:
                msg = (
                    f"📊 <b>Countdown до ребалансировки</b>\n\n"
                    f"📅 Осталось: <b>{days_until}</b> торговых дней\n"
                    f"📈 Стратегия: Momentum Trading (S&P 500)\n"
                    f"⏱️ Следующая ребалансировка: в течение {days_until} торговых дней"
                )

            await message.answer(msg, parse_mode="HTML")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Ошибка при проверке дней до ребалансировки: %s", exc)
            await message.answer(
                "❌ Ошибка при получении информации о ребалансировке"
            )

    @router.message(Command("info"))
    async def show_info(message: Message):
        """Обработчик команды /info."""
        await message.answer(
            "Торговый бот для автоматической торговли на бирже.\n"
            "Стратегия: Momentum Trading\n"
            "Ребалансировка: ежедневно в 10:00 (NY)\n"
            "Используется API Alpaca Markets"
        )

    @router.message(Command("portfolio"))
    async def show_portfolio(message: Message):
        """Обработчик команды /portfolio."""
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

            await message.answer(msg)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Ошибка при получении данных портфеля: %s", exc)
            await message.answer(
                "❌ Ошибка при получении данных портфеля"
            )

    @router.message(Command("stats"))
    async def show_stats(message: Message):
        """Обработчик команды /stats."""
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
            await message.answer(msg)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Ошибка при получении торговой статистики: %s", exc)
            await message.answer(
                "❌ Ошибка при получении торговой статистики"
            )

    @router.message(Command("settings"))
    async def show_settings(message: Message):
        """Обработчик команды /settings."""
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
            await message.answer(msg)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Ошибка при получении настроек: %s", exc)
            await message.answer("❌ Ошибка при получении настроек")

    @router.message()
    async def echo(message: Message):
        """Обработчик всех остальных сообщений."""
        await message.answer(
            "Используйте кнопки меню или команды для управления ботом.\n"
            "Для помощи введите /help"
        )

    return router
