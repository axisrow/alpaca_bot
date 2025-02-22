from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

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
        [InlineKeyboardButton(text="📊 Портфель", callback_data="portfolio_status")],
        [InlineKeyboardButton(text="📈 Статистика", callback_data="trading_stats")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")]
    ]
)
