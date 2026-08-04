from aiogram import Router, F
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
        ]
    ])

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
    """Клавиатура управления конкретным постом"""
    status_text = "🔴 Приостановить" if is_active == 1 else "🟢 Активировать"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data=f"pub_now_{post_id}_{page}")
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

@router.callback_query(F.data.startswith("view_post_"))
async def view_single_post(callback: CallbackQuery):
    """Просмотр карточки конкретного поста"""
    parts = callback.data.split("_")
    post_id = int(parts[2])
    page = int(parts[3])
    
    post = get_post_by_id(post_id)
    if not post:
        await callback.answer("❌ Пост не найден.", show_alert=True)
        return

    # Формируем красивое описание настроек для менеджера
    status_str = "🟢 Активен (в ротации)" if post['is_active'] == 1 else "🔴 На паузе"
    last_p = post['last_posted'] if post['last_posted'] else "Ни разу"
    
    buttons_list = json.loads(post['buttons'])
    btn_count = len(buttons_list)

    caption = (
        f"📝 **Карточка поста # {post['id']}**\n\n"
        f"📊 **Статус:** {status_str}\n"
        f"⏳ **Интервал:** каждые {post['interval_min']} мин.\n"
        f"🔘 **Внешних кнопок:** {btn_count} шт.\n"
        f"🕒 **Последний постинг:** {last_p}\n\n"
        f"📋 **Текст поста:**\n---\n{post['text']}\n---"
    )

    markup = get_post_manage_kb(post_id, post['is_active'], page)

    # Если медиа нет, просто обновляем интерфейс в том же сообщении
    if post['media_type'] in [None, "text"]:
        await callback.message.edit_text(caption, reply_markup=markup, parse_mode="Markdown")
    else:
        # Если есть медиа, во избежание визуального мусора удаляем старое текстовое меню
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        
        # И отправляем новое чистое сообщение с медиафайлом и админ-кнопками под ним
        if post['media_type'] == "photo":
            await callback.message.answer_photo(photo=post['media_id'], caption=caption, reply_markup=markup, parse_mode="Markdown")
        elif post['media_type'] == "video":
            await callback.message.answer_video(video=post['media_id'], caption=caption, reply_markup=markup, parse_mode="Markdown")
        elif post['media_type'] == "animation":
            await callback.message.answer_animation(animation=post['media_id'], caption=caption, reply_markup=markup, parse_mode="Markdown")
        else:
            # На случай, если сохранен сырой file_id без явного типа
            await callback.message.answer(caption + f"\n\n📎 *ID Медиа:* `{post['media_id']}`", reply_markup=markup, parse_mode="Markdown")

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
        
        # Имитируем повторный клик для обновления карточки без дублирования кода
        callback.data = f"view_post_{post_id}_{page}"
        await view_single_post(callback)

from aiogram import Bot
from database.models import get_all_channels

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
    channels = get_all_channels()
    
    if not post:
        await callback.answer("❌ Пост не найден.", show_alert=True)
        return
        
    if not channels:
        await callback.answer("❌ Нет каналов для публикации. Добавьте бота в админы какого-нибудь канала.", show_alert=True)
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

