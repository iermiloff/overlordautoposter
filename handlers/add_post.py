import json
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import config
from database.models import add_post, get_all_channels_detailed
from handlers.admin_menu import get_main_menu_kb

router = Router()

# Состояния FSM машины
class AddPostState(StatesGroup):
    text = State()
    media = State()
    channels = State()  # НОВЫЙ ШАГ
    button_name = State()
    button_url = State()
    interval = State()

def get_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить создание", callback_data="cancel_add")]
    ])

def get_buttons_control_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить кнопку", callback_data="add_one_more_btn")],
        [InlineKeyboardButton(text="⏳ Перейти к интервалу", callback_data="skip_buttons_step")]
    ])

# Функция генерации клавиатуры выбора каналов внутри FSM
def get_fsm_channels_kb(all_channels, selected_channels: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    for ch in all_channels:
        ch_id = ch['channel_id']
        icon = "✅" if ch_id in selected_channels else "◻️"
        builder.row(InlineKeyboardButton(
            text=f"{icon} {ch['title']}", 
            callback_data=f"fsm_tglch_{ch_id}"
        ))
        
    builder.row(InlineKeyboardButton(text="⏭ Далее к кнопкам", callback_data="fsm_channels_done"))
    builder.row(InlineKeyboardButton(text="❌ Отменить создание", callback_data="cancel_add"))
    return builder.as_markup()


# --- ТОЧКА ВХОДА ---
@router.callback_query(F.data == "menu_add_post")
async def start_add_post(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("❌ Доступ ограничен.", show_alert=True)
        return
        
    await state.clear()
    await state.set_state(AddPostState.text)
    await callback.message.edit_text(
        "📝 **Шаг 1 из 5: Текст поста**\n\nОтправьте текст, который будет содержать пост.",
        reply_markup=get_cancel_kb()
    )

# --- ШАГ 1: ТЕКСТ -> К МЕДИА ---
@router.message(AddPostState.text, F.text)
async def process_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    await state.set_state(AddPostState.media)
    
    try: await message.delete()
    except Exception: pass

    await message.answer(
        "🎬 **Шаг 2 из 5: Медиафайл**\n\n"
        "Отправьте изображение, видео или GIF (или их `file_id` текстом).\n"
        "Если медиафайл не нужен, отправьте минус: `-`",
        reply_markup=get_cancel_kb()
    )

# --- ШАГ 2: МЕДИА -> К ВЫБОРУ КАНАЛОВ (Файл напрямую) ---
@router.message(AddPostState.media, F.photo | F.video | F.animation)
async def process_media_file(message: Message, state: FSMContext):
    media_id = message.photo[-1].file_id if message.photo else (message.video.file_id if message.video else message.animation.file_id)
    media_type = "photo" if message.photo else ("video" if message.video else "animation")

    await state.update_data(media_id=media_id, media_type=media_type, selected_channels=[])
    await state.set_state(AddPostState.channels)
    
    try: await message.delete()
    except Exception: pass
        
    all_channels = get_all_channels_detailed()
    await message.answer(
        "📢 **Шаг 3 из 5: Выберите каналы для публикации**\n\n"
        "Отметьте каналы, в которые должен транслироваться этот пост:",
        reply_markup=get_fsm_channels_kb(all_channels, [])
    )

# --- ШАГ 2: МЕДИА -> К ВЫБОРУ КАНАЛОВ (Текст/Минус) ---
@router.message(AddPostState.media, F.text)
async def process_media_text(message: Message, state: FSMContext):
    text_input = message.text.strip()
    media_id, media_type = (None, "text") if text_input in ["-", "минус"] else (text_input, "unknown")
    
    await state.update_data(media_id=media_id, media_type=media_type, selected_channels=[])
    await state.set_state(AddPostState.channels)
    
    try: await message.delete()
    except Exception: pass
        
    all_channels = get_all_channels_detailed()
    await message.answer(
        "📢 **Шаг 3 из 5: Выберите каналы для публикации**\n\n"
        "Отметьте каналы, в которые должен транслироваться этот пост:",
        reply_markup=get_fsm_channels_kb(all_channels, [])
    )

# --- ШАГ 3: ДИНАМИЧЕСКИЙ ВЫБОР КАНАЛОВ (Клик по каналу) ---
@router.callback_query(AddPostState.channels, F.data.startswith("fsm_tglch_"))
async def process_fsm_toggle_channel(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    selected = data.get("selected_channels", [])
    
    if channel_id in selected:
        selected.remove(channel_id)
    else:
        selected.append(channel_id)
        
    await state.update_data(selected_channels=selected)
    await callback.answer()
    
    all_channels = get_all_channels_detailed()
    await callback.message.edit_reply_markup(reply_markup=get_fsm_channels_kb(all_channels, selected))

# --- ШАГ 3 -> ШАГ 4: К КНОПКАМ ---
@router.callback_query(AddPostState.channels, F.data == "fsm_channels_done")
async def process_fsm_channels_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("selected_channels"):
        await callback.answer("⚠️ Выберите хотя бы один канал для продолжения!", show_alert=True)
        return
        
    await state.set_state(AddPostState.button_name)
    await callback.message.edit_text(
        "🔘 **Шаг 4 из 5: Инлайн-кнопки**\n\n"
        "Вы можете прикрепить к посту интерактивные кнопки со ссылками для подписчиков.\n"
        "Сейчас у поста нет кнопок.",
        reply_markup=get_buttons_control_kb()
    )

# --- ШАГ 4: КНОПКИ (Название) ---
@router.callback_query(AddPostState.button_name, F.data == "add_one_more_btn")
async def ask_button_name(callback: CallbackQuery):
    await callback.message.edit_text("Введите **название** для кнопки:", reply_markup=get_cancel_kb())

# --- ШАГ 4: КНОПКИ (Ссылка) ---
@router.message(AddPostState.button_name, F.text)
async def process_button_name(message: Message, state: FSMContext):
    await state.update_data(temp_btn_name=message.text)
    await state.set_state(AddPostState.button_url)
    try: await message.delete()
    except Exception: pass
        
    await message.answer(f"Теперь отправьте **URL-ссылку** для кнопки «{message.text}»:", reply_markup=get_cancel_kb())

# --- ШАГ 4: КНОПКИ (Валидация и вывод) ---
@router.message(AddPostState.button_url, F.text)
async def process_button_url(message: Message, state: FSMContext):
    url = message.text.strip()
    try: await message.delete()
    except Exception: pass

    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
        await message.answer("❌ Ссылка должна начинаться с http://, https:// или tg://\nПопробуйте еще раз:", reply_markup=get_cancel_kb())
        return

    data = await state.get_data()
    buttons = data.get("buttons", [])
    buttons.append({"text": data["temp_btn_name"], "url": url})
    await state.update_data(buttons=buttons, temp_btn_name=None)
    
    buttons_preview = "".join([f"{i}. [{b['text']}] -> {b['url']}\n" for i, b in enumerate(buttons, 1)])
    await state.set_state(AddPostState.button_name)
    await message.answer(f"🔘 **Шаг 4 из 5: Инлайн-кнопки**\n\nСписок добавленных кнопок:\n{buttons_preview}", reply_markup=get_buttons_control_kb())

# --- ШАГ 4 -> ШАГ 5: К ИНТЕРВАЛУ ---
@router.callback_query(AddPostState.button_name, F.data == "skip_buttons_step")
async def finish_buttons_step(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddPostState.interval)
    await callback.message.edit_text(
        "⏳ **Шаг 5 из 5: Интервал автопостинга**\n\nУкажите интервал повторения для этого поста в **минутах** (например, `60`):",
        reply_markup=get_cancel_kb()
    )

# --- ШАГ 5: ИНТЕРВАЛ -> ФИНАЛЬНОЕ СОХРАНЕНИЕ ---
@router.message(AddPostState.interval, F.text)
async def process_interval_and_save(message: Message, state: FSMContext):
    try: await message.delete()
    except Exception: pass

    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("❌ Введите целое положительное число минут:", reply_markup=get_cancel_kb())
        return

    interval = int(message.text)
    data = await state.get_data()
    
    # Сохраняем в базу данных с выбранным массивом каналов
    add_post(
        media_type=data.get("media_type"),
        media_id=data.get("media_id"),
        text=data.get("text"),
        buttons=data.get("buttons", []),
        interval=interval,
        target_channels=data.get("selected_channels", [])
    )
    
    await state.clear()
    await message.answer("🎉 **Пост успешно создан, каналы привязаны и запущены в автопостинг!**", reply_markup=get_main_menu_kb())

# --- ОТМЕНА ---
@router.callback_query(F.data == "cancel_add")
async def cancel_post_creation(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🤖 **Админ-панель автопостинга**\n\n❌ Создание поста отменено.", reply_markup=get_main_menu_kb())
