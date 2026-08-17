import json
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.models import get_posts_page, get_posts_count, get_post_by_id
from handlers.admin_menu import get_main_menu_kb

router = Router()
POSTS_PER_PAGE = 5

def get_posts_list_kb(page: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    offset = page * POSTS_PER_PAGE
    posts = get_posts_page(limit=POSTS_PER_PAGE, offset=offset)
    total_posts = get_posts_count()
    
    for post in posts:
        status_icon = "🟢" if post['is_active'] == 1 else "⚪"
        type_icon = "⏰" if post['is_delayed'] == 1 else "🔄"
        short_text = post['text'][:20] + "..." if len(post['text']) > 20 else post['text']
        builder.row(InlineKeyboardButton(
            text=f"{status_icon} {type_icon} ID {post['id']}: {short_text}",
            callback_data=f"view_post_{post['id']}_{page}"
        ))
        
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"posts_page_{page - 1}"))
    if offset + POSTS_PER_PAGE < total_posts:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"posts_page_{page + 1}"))
        
    if nav_buttons:
        builder.row(*nav_buttons)
    builder.row(InlineKeyboardButton(text="« Главное меню", callback_data="to_main_menu"))
    return builder.as_markup()

@router.callback_query(F.data.startswith("posts_page_"))
async def process_posts_page(callback: CallbackQuery):
    page = int(callback.data.split("_")[2])
    if get_posts_count() == 0:
        text = "Список постов пуст."
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Главное меню", callback_data="to_main_menu")]])
        if callback.message.text: await callback.message.edit_text(text, reply_markup=kb)
        else:
            try: await callback.message.delete()
            except: pass
            await callback.message.answer(text, reply_markup=kb)
        return
        
    text = "📋 **Список постов:**\n🟢 Активен | ⚪ На паузе\n🔄 Циклический | ⏰ Отложенный"
    kb = get_posts_list_kb(page)
    if callback.message.text:
        await callback.message.edit_text(text, reply_markup=kb)
    else:
        try: await callback.message.delete()
        except: pass
        await callback.message.answer(text, reply_markup=kb)

def get_post_manage_kb(post_id: int, is_active: int, page: int) -> InlineKeyboardMarkup:
    status_text = "⏸ Приостановить" if is_active == 1 else "▶️ Активировать"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data=f"pub_now_{post_id}_{page}")],
        [InlineKeyboardButton(text="📂 Настройка каналов", callback_data=f"post_ch_{post_id}_{page}")],
        [
            InlineKeyboardButton(text=status_text, callback_data=f"toggle_{post_id}_{page}"),
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_post_{post_id}_{page}")
        ],
        [InlineKeyboardButton(text="🗑 Удалить пост", callback_data=f"confirm_del_{post_id}_{page}")],
        [InlineKeyboardButton(text="« Назад к списку", callback_data=f"posts_page_{page}")]
    ])

async def render_post_card(event, post_id: int, page: int):
    if isinstance(event, CallbackQuery): target_message = event.message
    else: target_message = event
    
    post = get_post_by_id(post_id)
    if not post:
        if isinstance(event, CallbackQuery): await event.answer("❌ Пост не найден.", show_alert=True)
        return
        
    status_str = "Активен" if post['is_active'] == 1 else "На паузе"
    last_p = post['last_posted'] if post['last_posted'] else "Ни разу"
    
    if post['is_delayed'] == 1:
        type_str = f"⏰ Отложенный (План: `{post['publish_at']}`)"
    else:
        type_str = f"🔄 Циклический (Каждые {post['interval_min']} мин.)"
        
    try: btn_count = len(json.loads(post['buttons']))
    except: btn_count = 0
    
    caption = (
        f"📄 **Карточка поста #{post['id']}**\n\n"
        f"🔹 **Статус:** {status_str}\n"
        f"🔹 **Тип:** {type_str}\n"
        f"🔹 **Кнопок:** {btn_count} шт.\n"
        f"🔹 **Последняя отправка:** {last_p}\n\n"
        f"📝 **Текст поста:**\n---\n{post['text']}\n---"
    )
    markup = get_post_manage_kb(post_id, post['is_active'], page)
    
    if post['media_type'] in [None, "text"]:
        if isinstance(event, CallbackQuery): await target_message.edit_text(caption, reply_markup=markup, parse_mode="Markdown")
        else:
            try: await target_message.delete()
            except: pass
            await target_message.answer(caption, reply_markup=markup, parse_mode="Markdown")
    else:
        try: await target_message.delete()
        except: pass
        if post['media_type'] == "photo":
            await target_message.answer_photo(photo=post['media_id'], caption=caption, reply_markup=markup, parse_mode="Markdown")
        elif post['media_type'] == "video":
            await target_message.answer_video(video=post['media_id'], caption=caption, reply_markup=markup, parse_mode="Markdown")
        elif post['media_type'] == "animation":
            await target_message.answer_animation(animation=post['media_id'], caption=caption, reply_markup=markup, parse_mode="Markdown")

@router.callback_query(F.data.startswith("view_post_"))
async def view_single_post(callback: CallbackQuery):
    parts = callback.data.split("_")
    await render_post_card(callback, int(parts[2]), int(parts[3]))
