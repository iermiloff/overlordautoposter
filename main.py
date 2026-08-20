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
                # Безопасно приводим Row к словарю для работы с миграциями
                p_dict = dict(post)
                
                # Проверяем только активные посты
                if p_dict.get('is_active', 1) != 1:
                    continue
                
                try:
                    channels = json.loads(p_dict.get('target_channels', '[]'))
                except Exception:
                    channels = []
                
                if not channels:
                    continue
                
                should_publish = False
                
                # --- ЛОГИКА 1: ОБРАБОТКА ОТЛОЖЕННОГО ПОСТА ---
                if p_dict.get('is_delayed', 0) == 1:
                    try:
                        admin_tz_str = get_timezone()
                        if isinstance(admin_tz_str, (list, tuple)):
                            admin_tz_str = admin_tz_str[0]
                        admin_tz_str = str(admin_tz_str).strip()
                        
                        local_dt = datetime.strptime(p_dict.get('publish_at'), "%d.%m.%Y %H:%M")
                        
                        try:
                            tz_obj = ZoneInfo(admin_tz_str)
                        except Exception:
                            logging.error(f" Неизвестный часовой пояс '{admin_tz_str}', откат на UTC")
                            tz_obj = ZoneInfo("UTC")
                        
                        local_dt = local_dt.replace(tzinfo=tz_obj)
                        
                        if now_utc >= local_dt.astimezone(ZoneInfo("UTC")):
                            should_publish = True
                    except Exception as ex:
                        logging.error(f"❌Ошибка парсинга времени отложенного поста #{p_dict.get('id')}: {ex}")
                        continue
                
                # --- ЛОГИКА 2: ОБРАБОТКА ИНТЕРВАЛЬНОГО ПОСТА ---
                else:
                    now_naive_utc = now_utc.replace(tzinfo=None)
                    if not p_dict.get('last_posted'):
                        should_publish = True
                    else:
                        try:
                            last_posted_dt = datetime.strptime(p_dict.get('last_posted'), "%Y-%m-%d %H:%M:%S")
                            if now_naive_utc >= last_posted_dt + timedelta(minutes=p_dict.get('interval_min', 0)):
                                should_publish = True
                        except ValueError:
                            should_publish = True
                
                # --- ВЫПОЛНЕНИЕ ПУБЛИКАЦИИ ---
                if should_publish:
                    public_markup = build_public_kb(p_dict.get('buttons'))
                    
                    # ОТЛАДОЧНЫЙ ЛОГ: проверяем, создались ли кнопки
                    if public_markup:
                        logging.info(f" Сгенерирована клавиатура для поста #{p_dict.get('id')}: {public_markup.inline_keyboard}")
                    else:
                        logging.warning(f" Клавиатура для поста #{p_dict.get('id')} НЕ создана. В БД лежит: {p_dict.get('buttons')}")
                
                    logging.info(f" Наступило время публикации поста #{p_dict.get('id')}")
                    
                    # Фиксируем попытку отправки в базу данных
                    now_str = datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S")
                    update_last_posted(p_dict.get('id'), now_str)
                    
                    # Перебираем целевые каналы
                    for channel_id in channels:
                        try:
                            m_type = p_dict.get('media_type')
                            m_id = p_dict.get('media_id')
                            text_content = p_dict.get('text', '')
                            
                            # Попытка отправки с Markdown
                            try:
                                if m_type in [None, "text"]:
                                    await bot.send_message(chat_id=channel_id, text=text_content, reply_markup=public_markup, parse_mode="Markdown")
                                elif m_type == "photo":
                                    await bot.send_photo(chat_id=channel_id, photo=m_id, caption=text_content, reply_markup=public_markup, parse_mode="Markdown")
                                elif m_type == "video":
                                    await bot.send_video(chat_id=channel_id, video=m_id, caption=text_content, reply_markup=public_markup, parse_mode="Markdown")
                                elif m_type == "animation":
                                    await bot.send_animation(chat_id=channel_id, animation=m_id, caption=text_content, reply_markup=public_markup, parse_mode="Markdown")
                            except Exception as telegram_err:
                                logging.error(f"❌ Ошибка Markdown форматирования. Отправка без parse_mode: {telegram_err}")
                                # Резервная копия без parse_mode
                                if m_type in [None, "text"]:
                                    await bot.send_message(chat_id=channel_id, text=text_content, reply_markup=public_markup)
                                elif m_type == "photo":
                                    await bot.send_photo(chat_id=channel_id, photo=m_id, caption=text_content, reply_markup=public_markup)
                                elif m_type == "video":
                                    await bot.send_video(chat_id=channel_id, video=m_id, caption=text_content, reply_markup=public_markup)
                                elif m_type == "animation":
                                    await bot.send_animation(chat_id=channel_id, animation=m_id, caption=text_content, reply_markup=public_markup)
                            
                            logging.info(f"✅Пост #{p_dict.get('id')} успешно отправлен в канал {channel_id}")
                            
                            # Если пост был отложенным — удаляем после первой успешной отправки в канал
                            if p_dict.get('is_delayed', 0) == 1:
                                delete_post(p_dict.get('id'))
                                logging.info(f" Отложенный пост #{p_dict.get('id')} выполнился и был удален из базы данных.")
                        
                        except Exception as e:
                            logging.error(f"❌Ошибка отправки поста #{p_dict.get('id')} в канал {channel_id}: {e}")
        
        except Exception as e:
            logging.error(f" Ошибка в цикле планировщика: {e}")
        
        await asyncio.sleep(60)


async def main():
    init_db()
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    
    dp.include_router(admin_menu.router)
    dp.include_router(admin_posts_list.router)
    dp.include_router(admin_post_actions.router)
    dp.include_router(add_post.router)
    dp.include_router(channels_track.router)
    
    asyncio.create_task(autoposting_scheduler(bot))
    
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info(" Бот успешно запущен в режиме Long Polling.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info(" Бот остановлен.")
