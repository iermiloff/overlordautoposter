from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import config

router = Router()

def get_main_menu_kb() -> InlineKeyboardMarkup:
    """Генерация кнопок главного меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Список постов", callback_data="posts_page_0"),
            InlineKeyboardButton(text="➕ Добавить пост", callback_data="menu_add_post")
        ],
        [
            InlineKeyboardButton(text="🔍 Просканировать каналы", callback_data="scan_channels")
        ]
    ])

@router.callback_query(F.data == "scan_channels")
async def process_scan_channels(callback: CallbackQuery, bot: Bot):
    """Отображает список каналов, где бот сейчас находится в базе данных"""
    channels = get_all_channels_detailed()
    
    if not channels:
        text = (
            "🔍 **Сканирование каналов**\n\n"
            "❌ Бот пока не добавлен ни в один канал.\n\n"
            "ℹ️ **Инструкция:** Добавьте бота в ваш Telegram-канал и назначьте его администратором с правом публикации сообщений. "
            "После этого он автоматически появится в этом списке."
        )
    else:
        text = "🔍 **Доступные каналы для постинга:**\n\n"
        for idx, ch in enumerate(channels, 1):
            text += f"{idx}. 📢 **{ch['title']}** (ID: `{ch['channel_id']}`)\n"
        text += f"\nВсего подключено каналов: {len(channels)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="scan_channels")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="to_main_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.message(CommandStart(), lambda msg: msg.from_user.id in config.ADMIN_IDS)
async def cmd_start_admin(message: Message):
    """Вход в админку по команде /start (только для админов)"""
    await message.answer(
        "🤖 **Админ-панель автопостинга**\n\nВыберите нужное действие:",
        reply_markup=get_main_menu_kb()
    )

@router.callback_query(F.data == "to_main_menu")
async def back_to_main_menu(callback: CallbackQuery):
    """Возврат в главное меню через редактирование сообщения"""
    await callback.message.edit_text(
        "🤖 **Админ-панель автопостинга**\n\nВыберите нужное действие:",
        reply_markup=get_main_menu_kb()
    )

from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.models import get_posts_page, get_posts_count, get_post_by_id

POSTS_PER_PAGE = 5

def get_posts_list_kb(page: int) -> InlineKeyboardMarkup:
    """Генерация клавиатуры со списком постов и кнопками пагинации"""
    builder = InlineKeyboardBuilder()
    offset = page * POSTS_PER_PAGE
    
    # 1. Получаем посты для текущей страницы
    posts = get_posts_page(limit=POSTS_PER_PAGE, offset=offset)
    total_posts = get_posts_count()
    
    # 2. Добавляем кнопку для каждого поста
    for post in posts:
        status_icon = "🟢" if post['is_active'] == 1 else "🔴"
        # Срезаем текст, чтобы кнопка не была слишком огромной
        short_text = post['text'][:25] + "..." if len(post['text']) > 25 else post['text']
        
        builder.row(InlineKeyboardButton(
            text=f"{status_icon} ID {post['id']}: {short_text}",
            callback_data=f"view_post_{post['id']}_{page}" # Запоминаем страницу для возврата
        ))
    
    # 3. Кнопки пагинации (Назад / Вперед)
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"posts_page_{page - 1}"))
    
    # Если впереди есть еще посты, выводим "Вперед"
    if offset + POSTS_PER_PAGE < total_posts:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"posts_page_{page + 1}"))
        
    if nav_buttons:
        builder.row(*nav_buttons)
        
    # 4. Кнопка возврата в главное меню
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="to_main_menu"))
    
    return builder.as_markup()

# Обработчик переключения страниц
@router.callback_query(F.data.startswith("posts_page_"))
async def process_posts_page(callback: CallbackQuery):
    page = int(callback.data.split("_")[2])
    total = get_posts_count()
    
    if total == 0:
        await callback.message.edit_text(
            "📭 Список постов пуст. Сначала добавьте пост.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="to_main_menu")]
            ])
        )
        return

    await callback.message.edit_text(
        f"📋 **Список постов (Страница {page + 1}):**\n"
        f"🟢 — Автопостинг активен\n"
        f"🔴 — На паузе\n\n"
        f"Нажмите на пост для управления им:",
        reply_markup=get_posts_list_kb(page)
    )

import json
from datetime import datetime
from aiogram.exceptions import TelegramBadRequest
from database.models import update_post_status, delete_post, update_last_posted

def get_post_manage_kb(post_id: int, is_active: int, page: int) -> InlineKeyboardMarkup:
    status_text = "🔴 Приостановить" if is_active == 1 else "🟢 Активировать"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data=f"pub_now_{post_id}_{page}")
        ],
        [
            InlineKeyboardButton(text="📢 Настройка каналов", callback_data=f"post_ch_{post_id}_{page}")  # НОВАЯ КНОПКА
        ],
        [
            InlineKeyboardButton(text=status_text, callback_data=f"toggle_{post_id}_{page}"),
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_post_{post_id}_{page}")
        ],
        [
            InlineKeyboardButton(text="🗑 Удалить пост", callback_data=f"confirm_del_{post_id}_{page}")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад к списку", callback_data=f"posts_page_{page}")
        ]
    ])

@router.callback_query(F.data.startswith("post_ch_"))
async def manage_post_channels(callback: CallbackQuery):
    """Экран выбора каналов для конкретного поста"""
    parts = callback.data.split("_")
    post_id = int(parts[2])
    page = int(parts[3])
    
    post = get_post_by_id(post_id)
    all_channels = get_all_channels_detailed()
    
    if not post:
        await callback.answer("❌ Пост не найден.", show_alert=True)
        return

    # Десериализуем каналы, выбранные для этого поста
    try:
        chosen_channels = json.loads(post['target_channels'])
    except:
        chosen_channels = []

    builder = InlineKeyboardBuilder()
    
    # Генерируем кнопки-переключатели для каждого канала
    for ch in all_channels:
        ch_id = ch['channel_id']
        is_chosen = ch_id in chosen_channels
        
        # Если канал выбран — ставим галочку, если нет — пустой квадрат
        icon = "✅" if is_chosen else "◻️"
        
        builder.row(InlineKeyboardButton(
            text=f"{icon} {ch['title']}", 
            callback_data=f"tglch_{post_id}_{ch_id}_{page}"
        ))
        
    builder.row(InlineKeyboardButton(text="💾 Сохранить и вернуться", callback_data=f"view_post_{post_id}_{page}"))
    
    text = f"📢 **Настройка каналов для поста #{post_id}**\n\nНажимайте на каналы, чтобы включить или выключить публикацию поста в них:"
    
    if callback.message.text:
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    else:
        await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup())

# Обработчик клика по каналу (включение/выключение)
@router.callback_query(F.data.startswith("tglch_"))
async def toggle_channel_for_post(callback: CallbackQuery):
    parts = callback.data.split("_")
    post_id = int(parts[1])
    channel_id = int(parts[2])
    page = int(parts[3])
    
    post = get_post_by_id(post_id)
    if not post:
        return
        
    try:
        chosen_channels = json.loads(post['target_channels'])
    except:
        chosen_channels = []
        
    if channel_id in chosen_channels:
        chosen_channels.remove(channel_id)
    else:
        chosen_channels.append(channel_id)
        
    update_post_channels(post_id, chosen_channels)
    await callback.answer()
    
    # Перерисовываем меню выбора каналов
    callback.data = f"post_ch_{post_id}_{page}"
    await manage_post_channels(callback)


async def render_post_card(callback: CallbackQuery, post_id: int, page: int):
    """Вспомогательная функция для чистой отрисовки карточки поста без изменения callback.data"""
    post = get_post_by_id(post_id)
    if not post:
        await callback.answer("❌ Пост не найден.", show_alert=True)
        return

    status_str = "🟢 Активен (в ротации)" if post['is_active'] == 1 else "🔴 На паузе"
    last_p = post['last_posted'] if post['last_posted'] else "Ни разу"
    
    try:
        buttons_list = json.loads(post['buttons'])
        btn_count = len(buttons_list)
    except Exception:
        btn_count = 0

    caption = (
        f"📝 **Карточка поста #{post['id']}**\n\n"
        f"📊 **Статус:** {status_str}\n"
        f"⏳ **Интервал:** каждые {post['interval_min']} мин.\n"
        f"🔘 **Внешних кнопок:** {btn_count} шт.\n"
        f"🕒 **Последний постинг:** {last_p}\n\n"
        f"📋 **Текст поста:**\n---\n{post['text']}\n---"
    )

    markup = get_post_manage_kb(post_id, post['is_active'], page)

    # Если медиа нет, обновляем в том же сообщении
    if post['media_type'] in [None, "text"]:
        await callback.message.edit_text(caption, reply_markup=markup, parse_mode="Markdown")
    else:
        # Если есть медиа, удаляем старое текстовое меню
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        
        # Отправляем сообщение с медиафайлом
        if post['media_type'] == "photo":
            await callback.message.answer_photo(photo=post['media_id'], caption=caption, reply_markup=markup, parse_mode="Markdown")
        elif post['media_type'] == "video":
            await callback.message.answer_video(video=post['media_id'], caption=caption, reply_markup=markup, parse_mode="Markdown")
        elif post['media_type'] == "animation":
            await callback.message.answer_animation(animation=post['media_id'], caption=caption, reply_markup=markup, parse_mode="Markdown")
        else:
            await callback.message.answer(caption + f"\n\n📎 *ID Медиа:* `{post['media_id']}`", reply_markup=markup, parse_mode="Markdown")


# Перехватчик нажатия на пост из списка пагинации
@router.callback_query(F.data.startswith("view_post_"))
async def view_single_post(callback: CallbackQuery):
    parts = callback.data.split("_")
    post_id = int(parts[2])
    page = int(parts[3])
    await render_post_card(callback, post_id, page)


# Переключатель Активировать / Деактивировать
@router.callback_query(F.data.startswith("toggle_"))
async def process_toggle_status(callback: CallbackQuery):
    parts = callback.data.split("_")
    post_id = int(parts[1])
    page = int(parts[2])
    
    post = get_post_by_id(post_id)
    if post:
        new_status = 0 if post['is_active'] == 1 else 1
        update_post_status(post_id, new_status)
        await callback.answer("✅ Статус успешно изменен")
        
        # Рендерим карточку заново БЕЗ перезаписи callback.data
        await render_post_card(callback, post_id, page)


# Кнопка моментальной публикации (в самом конце функции исправляем вызов)
@router.callback_query(F.data.startswith("pub_now_"))
async def process_publish_now(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split("_")
    post_id = int(parts[2])
    page = int(parts[3])
    
    post = get_post_by_id(post_id)
    all_channels_db = get_all_channels_detailed()
    
    if not post:
        await callback.answer("❌ Пост не найден.", show_alert=True)
        return
        
    try:
        chosen_channels = json.loads(post['target_channels'])
    except:
        chosen_channels = []
        
    available_ids = [ch['channel_id'] for ch in all_channels_db]
    channels = [ch_id for ch_id in chosen_channels if ch_id in available_ids]
        
    if not channels:
        await callback.answer("❌ Для этого поста не выбрано ни одного доступного канала! Зайдите в «Настройка каналов».", show_alert=True)
        return

    public_markup = build_public_kb(post['buttons'])
    success_count = 0
    
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
            success_count += 1
        except Exception as e:
            print(f"Ошибка отправки в канал {channel_id}: {e}")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    update_last_posted(post_id, now_str)
    
    await callback.answer(f"🚀 Пост отправлен в {success_count} из {len(channels)} каналов!", show_alert=True)
    
    # ИСПРАВЛЕНО: Рендерим карточку заново БЕЗ перезаписи callback.data
    await render_post_card(callback, post_id, page)

from aiogram import Bot
from database.models import get_all_channels_detailed

def build_public_kb(buttons_json: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру для подписчиков из сохраненного в БД JSON"""
    if not buttons_json:
        return None
    
    try:
        buttons_data = json.loads(buttons_json)
    except:
        return None
        
    if not buttons_data:
        return None
        
    # Формируем кнопки в ряд (по одной на строку для аккуратности)
    keyboard = []
    for btn in buttons_data:
        keyboard.append([InlineKeyboardButton(text=btn['text'], url=btn['url'])])
        
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@router.callback_query(F.data.startswith("pub_now_"))
async def process_publish_now(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split("_")
    post_id = int(parts[2])
    page = int(parts[3])
    
    post = get_post_by_id(post_id)
    all_channels_db = get_all_channels_detailed()  # <-- ОБНОВЛЕННАЯ СТРОКА
    
    if not post:
        await callback.answer("❌ Пост не найден.", show_alert=True)
        return
        
    try:
        chosen_channels = json.loads(post['target_channels'])
    except:
        chosen_channels = []
        
    # Проверяем, что выбранные каналы все еще существуют в нашей базе данных доступных каналов
    available_ids = [ch['channel_id'] for ch in all_channels_db]
    channels = [ch_id for ch_id in chosen_channels if ch_id in available_ids]
        
    if not channels:
        await callback.answer("❌ Для этого поста не выбрано ни одного доступного канала! Зайдите в «Настройка каналов».", show_alert=True)
        return

    # Клавиатура со ссылками для обычных пользователей
    public_markup = build_public_kb(post['buttons'])
    
    success_count = 0
    # Отправляем во все подключенные каналы
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
            success_count += 1
        except Exception as e:
            # Например, бота удалили из канала, а событие не отловилось
            print(f"Ошибка отправки в канал {channel_id}: {e}")

    # Обновляем время последней отправки в базе данных
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    update_last_posted(post_id, now_str)
    
    await callback.answer(f"🚀 Пост отправлен в {success_count} из {len(channels)} каналов!", show_alert=True)
    
    # Обновляем карточку поста на экране менеджера, чтобы зафиксировать новое время отправки
    callback.data = f"view_post_{post_id}_{page}"
    await view_single_post(callback)

# Экран подтверждения удаления поста
@router.callback_query(F.data.startswith("confirm_del_"))
async def confirm_delete_post(callback: CallbackQuery):
    parts = callback.data.split("_")
    post_id = int(parts[2])
    page = int(parts[3])
    
    # Кнопки подтверждения
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑 Да, удалить навсегда", callback_data=f"execute_del_{post_id}_{page}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_post_{post_id}_{page}")
        ]
    ])
    
    # Редактируем сообщение на предупреждение. Если было медиа, текст изменится под ним.
    # Если медиа не было, просто изменится текст сообщения.
    if callback.message.text:
        await callback.message.edit_text(
            f"⚠️ **Вы уверены, что хотите удалить пост #{post_id}?**\nЭто действие нельзя отменить.",
            reply_markup=markup
        )
    else:
        await callback.message.edit_caption(
            caption=f"⚠️ **Вы уверены, что хотите удалить пост #{post_id}?**\nЭто действие нельзя отменить.",
            reply_markup=markup
        )

# Само удаление после подтверждения
@router.callback_query(F.data.startswith("execute_del_"))
async def execute_delete_post(callback: CallbackQuery):
    parts = callback.data.split("_")
    post_id = int(parts[2])
    page = int(parts[3])
    
    # Удаляем из БД
    delete_post(post_id)
    await callback.answer("🗑 Пост успешно удален", show_alert=True)
    
    # Если у поста было медиа (сообщение без основного текста), то для возврата к списку
    # проще удалить это сообщение и отправить список заново, чтобы интерфейс выглядел аккуратно
    if not callback.message.text:
        try:
            await callback.message.delete()
        except Exception:
            pass
        # Отправляем список постов заново
        total = get_posts_count()
        if total == 0:
            await callback.message.answer(
                "📭 Список постов пуст.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="to_main_menu")]
                ])
            )
        else:
            await callback.message.answer(
                f"📋 **Список постов (Страница {page + 1}):**\nВыберите пост для управления:",
                reply_markup=get_posts_list_kb(page)
            )
    else:
        # Если это был чисто текстовый пост, плавно возвращаем менеджера к списку через edit_text
        callback.data = f"posts_page_{page}"
        await process_posts_page(callback)
