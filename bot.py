import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from handlers import router
from config import TELEGRAM_BOT_TOKEN

async def main():
    # Включаем логирование 
    logging.basicConfig(level=logging.INFO)
    
    # Инициализируем бота и диспетчер
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    
    # Регистрируем роутер
    dp.include_router(router)
    
    # Установка команд бота
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать работу"),
        BotCommand(command="help", description="Помощь"),
    ])
    
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())