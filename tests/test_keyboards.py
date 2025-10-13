"""Тесты для модуля keyboards."""
from datetime import datetime, timedelta

from aiogram.types import (
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup
)

from keyboards import main_kb, menu_kb, get_backtest_keyboard


def test_main_kb_structure():
    """Тест структуры основной клавиатуры."""
    assert isinstance(main_kb, ReplyKeyboardMarkup)
    assert main_kb.resize_keyboard is True

    # Проверяем количество рядов
    assert len(main_kb.keyboard) == 2

    # Проверяем текст кнопок в первом ряду
    assert main_kb.keyboard[0][0].text == "📋 Меню"
    assert main_kb.keyboard[0][1].text == "ℹ️ Информация"

    # Проверяем текст кнопки во втором ряду
    assert main_kb.keyboard[1][0].text == "❓ Помощь"


def test_menu_kb_structure():
    """Тест структуры меню клавиатуры."""
    assert isinstance(menu_kb, InlineKeyboardMarkup)

    # Проверяем количество рядов
    assert len(menu_kb.inline_keyboard) == 4

    # Проверяем callback_data кнопок
    assert menu_kb.inline_keyboard[0][0].callback_data == "portfolio_status"
    assert menu_kb.inline_keyboard[1][0].callback_data == "trading_stats"
    assert menu_kb.inline_keyboard[2][0].callback_data == "show_backtest"
    assert menu_kb.inline_keyboard[3][0].callback_data == "settings"

    # Проверяем текст кнопок
    assert menu_kb.inline_keyboard[0][0].text == "💼 Портфель"
    assert menu_kb.inline_keyboard[1][0].text == "📈 Статистика"
    assert menu_kb.inline_keyboard[2][0].text == "📊 Бэктест"
    assert menu_kb.inline_keyboard[3][0].text == "⚙️ Настройки"


def test_get_backtest_keyboard_structure():
    """Тест структуры клавиатуры бэктеста."""
    kb = get_backtest_keyboard()

    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) == 5  # 4 варианта периода + кнопка Назад

    # Проверяем текст кнопок
    assert kb.inline_keyboard[0][0].text == "📊 Последний год"
    assert kb.inline_keyboard[1][0].text == "📈 6 месяцев"
    assert kb.inline_keyboard[2][0].text == "📉 3 месяца"
    assert kb.inline_keyboard[3][0].text == "🔄 Произвольный период"
    assert kb.inline_keyboard[4][0].text == "🔙 Назад"


def test_get_backtest_keyboard_callback_data():
    """Тест callback_data клавиатуры бэктеста."""
    kb = get_backtest_keyboard()
    today = datetime.now()

    # Проверяем формат callback_data для последнего года
    year_ago = (today - timedelta(days=365)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    callback_data_year = kb.inline_keyboard[0][0].callback_data
    assert callback_data_year == f"backtest_{year_ago}_{today_str}"

    # Проверяем формат для 6 месяцев
    six_months_ago = (today - timedelta(days=180)).strftime("%Y-%m-%d")
    callback_data_6m = kb.inline_keyboard[1][0].callback_data
    assert callback_data_6m == f"backtest_{six_months_ago}_{today_str}"

    # Проверяем формат для 3 месяцев
    three_months_ago = (today - timedelta(days=90)).strftime("%Y-%m-%d")
    callback_data_3m = kb.inline_keyboard[2][0].callback_data
    assert callback_data_3m == f"backtest_{three_months_ago}_{today_str}"

    # Проверяем callback_data для произвольного периода
    assert kb.inline_keyboard[3][0].callback_data == "backtest_custom"

    # Проверяем callback_data для кнопки Назад
    assert kb.inline_keyboard[4][0].callback_data == "back_to_main"


def test_get_backtest_keyboard_date_format():
    """Тест правильности формата дат в callback_data."""
    kb = get_backtest_keyboard()

    # Берем callback_data первой кнопки (последний год)
    callback_data = kb.inline_keyboard[0][0].callback_data

    # Извлекаем даты из callback_data
    parts = callback_data.split('_')
    assert len(parts) == 3  # backtest, start_date, end_date

    start_date_str = parts[1]
    end_date_str = parts[2]

    # Проверяем, что даты парсятся корректно
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

    # Проверяем, что разница примерно 365 дней
    delta = (end_date - start_date).days
    assert 364 <= delta <= 366  # Учитываем високосные годы
