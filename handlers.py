from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from keyboards import main_kb, menu_kb
import logging

def setup_router(trading_bot):
    """Настройка роутера с доступом к TradingBot"""
    router = Router()

    @router.message(Command("start"))
    async def cmd_start(message: Message):
        await message.answer(
            "Привет! Я ваш торговый бот-помощник.\n"
            "Используйте меню для управления торговлей.",
            reply_markup=main_kb
        )

    @router.message(Command("help"))
    async def cmd_help(message: Message):
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
        await message.answer(
            "Выберите действие:",
            reply_markup=menu_kb
        )

    @router.message(F.text == "ℹ️ Информация")
    async def show_info(message: Message):
        await message.answer(
            "Торговый бот для автоматической торговли на бирже.\n"
            "Стратегия: Momentum Trading\n"
            "Ребалансировка: ежедневно в 10:00 (NY)\n"
            "Используется API Alpaca Markets"
        )

    @router.callback_query(F.data == "portfolio_status")
    async def show_portfolio(callback: CallbackQuery):
        await callback.answer()
        try:
            # Получаем данные о портфеле из TradingBot
            positions, account, pnl = trading_bot.get_portfolio_status()
            
            # Проверяем, что данные получены корректно
            if not account:
                raise ValueError("Не удалось получить данные аккаунта")

            # Формируем сообщение
            msg = "Статус портфеля:\n\n"
            
            if positions:
                msg += "Позиции:\n"
                for symbol, qty in positions.items():
                    # Получаем рыночную стоимость позиции
                    position = next((p for p in trading_bot.trading_client.get_all_positions() 
                                   if p.symbol == symbol), None)
                    if position:
                        value = float(position.market_value)
                        msg += f"{symbol} – {float(qty):.2f} шт. (${value:.2f})\n"
                    else:
                        msg += f"{symbol} – {float(qty):.2f} шт. (нет данных о стоимости)\n"
            else:
                msg += "Позиции: нет открытых позиций\n"
            
            msg += "\nПротфель:\n"
            msg += f"Оценка: {float(account.portfolio_value):.2f} euro\n"
            msg += f"Эквити: {float(account.equity):.2f} euro\n"
            msg += f"\nP&L: ${pnl:.2f} euro"
            
            await callback.message.answer(msg)
        except Exception as e:
            logging.error(f"Ошибка при получении данных портфеля: {e}")
            await callback.message.answer("❌ Ошибка при получении данных портфеля")

    @router.callback_query(F.data == "trading_stats")
    async def show_stats(callback: CallbackQuery):
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
        except Exception as e:
            logging.error(f"Ошибка при получении торговой статистики: {e}")
            await callback.message.answer("❌ Ошибка при получении торговой статистики")

    @router.callback_query(F.data == "settings")
    async def show_settings(callback: CallbackQuery):
        await callback.answer()
        try:
            # Получаем настройки из TradingBot
            settings = trading_bot.get_settings()
            
            # Проверяем, что настройки получены
            if not settings:
                raise ValueError("Настройки недоступны")
                
            msg = "Настройки бота:\n"
            msg += f"- Время ребалансировки: {settings.get('rebalance_time', 'не задано')}\n"
            msg += f"- Количество позиций: {settings.get('positions_count', 0)}\n"
            msg += f"- Режим: {settings.get('mode', 'не задан')}"
            await callback.message.answer(msg)
        except Exception as e:
            logging.error(f"Ошибка при получении настроек: {e}")
            await callback.message.answer("❌ Ошибка при получении настроек")

    @router.message()
    async def echo(message: Message):
        await message.answer(
            "Используйте кнопки меню или команды для управления ботом.\n"
            "Для помощи введите /help"
        )

    return router