import asyncio
import json
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from config import config
from database.models import init_db, get_all_posts, update_last_posted
from handlers import admin_menu, add_post, channels_track
from handlers.admin_menu import build_public_kb

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

async def autoposting_scheduler(bot: Bot):
    """
    Фоновый цикл автопостинга.
    Просыпается раз в минуту и проверяет, какие посты пора опубликовать.
    """
    logging.info("🚀 Фоновый планировщик автопостинга успешно запущен.")
    
    while True:
        try:
            posts = get_all_posts()
            now = datetime.now()
            
            for post in posts:
                # Проверяем только активные посты
                if post['is_active'] != 1:
                    continue
                
                # Парсим целевые каналы для этого поста
                try:
                    channels = json.loads(post['target_channels'])
                except Exception:
                    channels = []
                
                if not channels:
                    continue
                
                # Проверяем, пришло ли время для публикации
                should_publish = False
                
                if not post['last_posted']:
                    # Если пост еще ни разу не публиковался — отправляем его сразу
                    should_publish = True
                else:
                    try:
                        last_posted_dt = datetime.strptime(post['last_posted'], "%Y-%m-%d %H:%M:%S")
                        # Если с момента последней публикации прошло больше минут, чем заданный интервал
                        if now >= last_posted_dt + timedelta(minutes=post['interval_min']):
                            should_publish = True
                    except ValueError:
                        # На случай некорректного формата даты в БД
                        should_publish = True
                
                if should_publish:
                    public_markup = build_public_kb(post['buttons'])
                    
                    logging.info(f"⏳ Наступило время публикации поста #{post['id']}")
                    
                    for channel_id in channels:
                        try:
                            if post['media_type'] in [None, "text"]:
                                await bot.send_message(chat_id=channel_id, text=post['text'], reply_markup=public_markup, parse_mode="Markdown")
                            elif post['media_type'] == "photo":
                                await bot.send_photo(chat_id=channel_id, photo=post['media_id'], caption=post['text'], reply_markup=public_markup, parse_mode="Markdown")
                            elif post['media_type'] == "video":
                                await bot.send_video(chat_id=channel_id, video=post['media_id'], caption=post['text'], reply_markup=public_markup, parse_mode="Markdown")
                            elif post['media_type'] == "animation":
                                await bot.send_animation(chat_id=channel_id, animation=post['media_id'], caption=post['text'], reply_markup=public_markup, parse_mode="Markdown")
                        except Exception as e:
                            logging.error(f"❌ Ошибка отправки поста #{post['id']} в канал {channel_id}: {e}")
                    
                    # Обновляем метку времени публикации в БД
                    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
                    update_last_posted(post['id'], now_str)
                    
        except Exception as e:
            logging.error(f"🚨 Ошибка в цикле планировщика: {e}")
            
        # Спим 60 секунд до следующей проверки
        await asyncio.sleep(60)

async def main():
    # 1. Инициализируем базу данных
    init_db()
    
    # 2. Инициализируем бота и диспетчер
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    
    # 3. Регистрируем наши роутеры обработчиков
    dp.include_router(admin_menu.router)
    dp.include_router(add_post.router)
    dp.include_router(channels_track.router)
    
    # 4. Запускаем фоновый планировщик автопостинга
    asyncio.create_task(autoposting_scheduler(bot))
    
    # 5. Стираем старые вебхуки (если были) и запускаем Long Polling
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("🤖 Бот успешно запущен в режиме Long Polling.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("🤖 Бот остановлен.")
