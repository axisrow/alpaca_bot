__all__ = ['main_kb', 'menu_kb', 'get_backtest_keyboard']

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta

# Основная клавиатура
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Меню"), KeyboardButton(text="ℹ️ Информация")],
        [KeyboardButton(text="❓ Помощь")]
    ],
    resize_keyboard=True
)

# Инлайн клавиатура для меню
menu_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="💼 Портфель", callback_data="portfolio_status")],
        [InlineKeyboardButton(text="📈 Статистика", callback_data="trading_stats")],
        [InlineKeyboardButton(text="📊 Бэктест", callback_data="show_backtest")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")]
        
    ]
)

def get_backtest_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для бэктестинга"""
    today = datetime.now()
    year_ago = (today - timedelta(days=365)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Последний год",
                    callback_data=f"backtest_{year_ago}_{today_str}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📈 6 месяцев",
                    callback_data=f"backtest_{(today - timedelta(days=180)).strftime('%Y-%m-%d')}_{today_str}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📉 3 месяца",
                    callback_data=f"backtest_{(today - timedelta(days=90)).strftime('%Y-%m-%d')}_{today_str}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Произвольный период",
                    callback_data="backtest_custom"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Назад",
                    callback_data="back_to_main"
                )
            ]
        ]
    )
