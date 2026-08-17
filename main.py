import asyncio
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher
from config import config
from database.models import init_db, get_all_posts, update_last_posted, delete_post, get_timezone
from handlers import admin_menu, admin_posts_list, admin_post_actions, add_post, channels_track
from handlers.admin_menu import build_public_kb

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

async def autoposting_scheduler(bot: Bot):
    """
    Фоновый цикл автопостинга.
    Обрабатывает как циклические (интервальные), так и разовые отложенные посты.
    """
    logging.info(" Фоновый планировщик автопостинга успешно запущен.")
    
    while True:
        try:
            posts = get_all_posts()
            now_utc = datetime.now(ZoneInfo("UTC"))
            
            for post in posts:
                # Проверяем только активные посты
                if post['is_active'] != 1:
                    continue
                    
                try:
                    channels = json.loads(post['target_channels'])
                except Exception:
                    channels = []
                    
                if not channels:
                    continue
                
                should_publish = False
                
                # --- ЛОГИКА 1: ОБРАБОТКА ОТЛОЖЕННОГО ПОСТА ---
                if post['is_delayed'] == 1:
                    try:
                        # Получаем часовой пояс админа (или UTC по дефолту)
                        admin_tz_str = get_timezone()
                        # Парсим локальное время, указанное админом при создании
                        local_dt = datetime.strptime(post['publish_at'], "%d.%m.%Y %H:%M")
                        # Присваиваем ему часовой пояс админа
                        local_dt = local_dt.replace(tzinfo=ZoneInfo(admin_tz_str))
                        
                        # Если текущее UTC-время сервера больше или равно UTC-времени поста
                        if now_utc >= local_dt.astimezone(ZoneInfo("UTC")):
                            should_publish = True
                    except Exception as ex:
                        logging.error(f"❌ Ошибка парсинга времени отложенного поста #{post['id']}: {ex}")
                        continue
                
                # --- ЛОГИКА 2: ОБРАБОТКА ИНТЕРВАЛЬНОГО ПОСТА ---
                else:
                    # Серверное время без привязки к поясу для интервалов
                    now_naive = datetime.now()
                    if not post['last_posted']:
                        # Если пост еще ни разу не публиковался — отправляем его сразу
                        should_publish = True
                    else:
                        try:
                            last_posted_dt = datetime.strptime(post['last_posted'], "%Y-%m-%d %H:%M:%S")
                            # Если с момента последней публикации прошло больше минут, чем заданный интервал
                            if now_naive >= last_posted_dt + timedelta(minutes=post['interval_min']):
                                should_publish = True
                        except ValueError:
                            # На случай некорректного формата даты в БД
                            should_publish = True
                
                # --- ВЫПОЛНЕНИЕ ПУБЛИКАЦИИ ---
                if should_publish:
                    public_markup = build_public_kb(post['buttons'])
                    logging.info(f" Наступило время публикации поста #{post['id']}")
                    
                    # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Сразу обновляем время публикации в БД.
                    # Даже если все каналы выдадут ошибку, бот зафиксирует попытку 
                    # и не будет спамить каждую минуту, а подождет следующий интервал.
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    update_last_posted(post['id'], now_str)
                    
                    # Перебираем каналы. Ошибка в одном канале теперь никак не прервет цикл
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
                            
                            logging.info(f"✅ Пост #{post['id']} успешно отправлен в канал {channel_id}")
                            
                        except Exception as e:
                            # Бот запишет ошибку по конкретному каналу, но продолжит слать в другие
                            logging.error(f"❌ Ошибка отправки поста #{post['id']} в канал {channel_id}: {e}")
                    
                    # Если пост был отложенным (одноразовым) — удаляем его после успешной публикации
                    if post['is_delayed'] == 1:
                        delete_post(post['id'])
                        logging.info(f"⏰ Отложенный пост #{post['id']} выполнился и был удален из базы данных.")
                        
        except Exception as e:
            logging.error(f" Ошибка в цикле планировщика: {e}")
            
        # Спим 60 секунд до следующей проверки
        await asyncio.sleep(60)

async def main():
    # 1. Инициализируем базу данных
    init_db()
    
    # 2. Инициализируем бота и диспетчер
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    
    # 3. Регистрируем роутеры обработчиков (включая новые разделенные файлы)
    dp.include_router(admin_menu.router)
    dp.include_router(admin_posts_list.router)
    dp.include_router(admin_post_actions.router)
    dp.include_router(add_post.router)
    dp.include_router(channels_track.router)
    
    # 4. Запускаем фоновый планировщик автопостинга
    asyncio.create_task(autoposting_scheduler(bot))
    
    # 5. Стираем старые вебхуки (если были) и запускаем Long Polling
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info(" Бот успешно запущен в режиме Long Polling.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info(" Бот остановлен.")
