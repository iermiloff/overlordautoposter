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
