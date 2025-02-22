from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from keyboards import main_kb, menu_kb

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
    # Здесь нужно получить данные о портфеле из TradingBot
    await callback.message.answer(
        "Статус портфеля:\n"
        "Позиции: ...\n"
        "Баланс: ...\n"
        "P&L: ..."
    )

@router.callback_query(F.data == "trading_stats")
async def show_stats(callback: CallbackQuery):
    await callback.answer()
    # Здесь нужно получить торговую статистику
    await callback.message.answer(
        "Торговая статистика:\n"
        "Сделок за сегодня: ...\n"
        "Прибыль/убыток: ...\n"
        "Win rate: ..."
    )

@router.callback_query(F.data == "settings")
async def show_settings(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "Настройки бота:\n"
        "- Время ребалансировки: 10:00 NY\n"
        "- Количество позиций: 10\n"
        "- Режим: Paper Trading"
    )

@router.message()
async def echo(message: Message):
    await message.answer(
        "Используйте кнопки меню или команды для управления ботом.\n"
        "Для помощи введите /help"
    )
