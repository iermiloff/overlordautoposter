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
