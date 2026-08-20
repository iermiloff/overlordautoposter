from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import config
from database.models import get_all_channels_detailed, get_timezone, set_timezone

router = Router()

# Список основных часовых поясов для СНГ и мира
COMMON_TIMEZONES = [
    ("UTC (Лондон)", "UTC"),
    ("МСК (UTC+3)", "Europe/Moscow"),
    ("Калининград (UTC+2)", "Europe/Kaliningrad"),
    ("Самара (UTC+4)", "Europe/Samara"),
    ("Екатеринбург (UTC+5)", "Europe/Yekaterinburg"),
    ("Омск (UTC+6)", "Europe/Omsk"),
    ("Красноярск (UTC+7)", "Europe/Krasnoyarsk"),
    ("Иркутск (UTC+8)", "Europe/Irkutsk"),
    ("Якутск (UTC+9)", "Europe/Yakutsk"),
    ("Владивосток (UTC+10)", "Europe/Vladivostok"),
    ("Ташкент / Душанбе (UTC+5)", "Asia/Tashkent"),
    ("Астана / Алматы (UTC+5)", "Asia/Almaty")
]

def get_main_menu_kb() -> InlineKeyboardMarkup:
    """Генерация кнопок главного меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Список постов", callback_data="posts_page_0"),
            InlineKeyboardButton(text="➕ Добавить пост", callback_data="menu_add_post")
        ],
        [
            InlineKeyboardButton(text="📡 Просканировать каналы", callback_data="scan_channels"),
            InlineKeyboardButton(text="⚙️ Часовой пояс", callback_data="menu_timezone")
        ]
    ])

def get_timezone_kb() -> InlineKeyboardMarkup:
    """Клавиатура со списком временных зон"""
    builder = InlineKeyboardBuilder()
    current_tz = get_timezone()
    
    for label, tz_name in COMMON_TIMEZONES:
        icon = "🟢 " if tz_name == current_tz else ""
        builder.row(InlineKeyboardButton(text=f"{icon}{label}", callback_data=f"set_tz_{tz_name}"))
        
    builder.row(InlineKeyboardButton(text="« В главное меню", callback_data="to_main_menu"))
    return builder.as_markup()

@router.message(CommandStart(), F.chat.type == "private", lambda msg: msg.from_user.id in config.ADMIN_IDS)
async def cmd_start_admin(message: Message):
    """Вход в админку по команде /start (ТОЛЬКО в ЛС и только для админов)"""
    await message.answer(
        "👋 **Админ-панель автопостинга**\n\nВыберите нужное действие:",
        reply_markup=get_main_menu_kb()
    )

@router.callback_query(F.data == "menu_timezone")
async def show_timezone_menu(callback: CallbackQuery):
    """Экран настройки часового пояса"""
    current_tz = get_timezone()
    text = (
        "⚙️ **Настройка часового пояса**\n\n"
        f"Текущий пояс администратора: `{current_tz}`\n\n"
        "Выберите ваш часовой пояс из списка ниже. Все отложенные публикации "
        "будут создаваться и отображаться по этому времени:"
    )
    await callback.message.edit_text(text, reply_markup=get_timezone_kb())

@router.callback_query(F.data.startswith("set_tz_"))
async def process_set_timezone(callback: CallbackQuery):
    """Сохранение выбранного часового пояса"""
    new_tz = callback.data.replace("set_tz_", "")
    set_timezone(new_tz)
    await callback.answer(f"✅ Часовой пояс изменен на {new_tz}", show_alert=True)
    await show_timezone_menu(callback)

@router.callback_query(F.data == "scan_channels")
async def process_scan_channels(callback: CallbackQuery, bot: Bot):
    channels = get_all_channels_detailed()
    if not channels:
        text = (
            "📡 **Сканирование каналов**\n\n"
            "❌ Бот пока не добавлен ни в один канал.\n\n"
            "**Инструкция:** Добавьте бота в ваш Telegram-канал и назначьте его "
            "администратором с правом публикации сообщений. После этого он автоматически появится здесь."
        )
    else:
        text = "📡 **Доступные каналы для постинга:**\n\n"
        for idx, ch in enumerate(channels, 1):
            text += f"{idx}. **{ch['title']}** (ID: `{ch['channel_id']}`)\n"
        text += f"\nВсего подключено каналов: {len(channels)}"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="scan_channels")],
        [InlineKeyboardButton(text="« В главное меню", callback_data="to_main_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "to_main_menu")
async def back_to_main_menu(callback: CallbackQuery):
    text = "👋 **Админ-панель автопостинга**\n\nВыберите нужное действие:"
    kb = get_main_menu_kb()
    if callback.message.text:
        await callback.message.edit_text(text, reply_markup=kb)
    else:
        try: await callback.message.delete()
        except: pass
        await callback.message.answer(text, reply_markup=kb)

def build_public_kb(buttons_data) -> InlineKeyboardMarkup:
    """Полностью безопасное создание инлайн-кнопок для подписчиков"""
    if not buttons_data:
        return None
        
    # Если это пустая строка, JSON-массив из пробелов или "null"
    if isinstance(buttons_data, str):
        cleaned = buttons_data.strip()
        if not cleaned or cleaned in ["[]", "null", "", "{}"]:
            return None
            
    # Циклическая распаковка строк на случай двойного json.dumps()
    while isinstance(buttons_data, str):
        try:
            buttons_data = json.loads(buttons_data)
        except Exception:
            # Если в базе лежит битый текст, который не распарсить
            return None

    if not isinstance(buttons_data, list) or not buttons_data:
        return None

    keyboard = []
    for btn in buttons_data:
        if isinstance(btn, dict) and 'text' in btn and 'url' in btn:
            keyboard.append([InlineKeyboardButton(text=btn['text'], url=btn['url'])])

    return InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None



