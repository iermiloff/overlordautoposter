import json
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.models import add_post, get_all_channels_detailed, get_timezone
from handlers.admin_menu import get_main_menu_kb
from handlers.admin_posts_list import render_post_card

router = Router()

class AddPostState(StatesGroup):
    text = State()
    media = State()
    channels = State()
    button_name = State()
    buttons_menu = State()
    button_url = State()
    post_type = State()       # Стейт выбора типа публикации
    interval = State()        # Стейт ввода интервала
    publish_time = State()    # Стейт ввода даты/времени

def get_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_add")]])

def get_buttons_control_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить еще кнопку", callback_data="add_one_more_btn")],
        [InlineKeyboardButton(text="⏭ К выбору типа публикации", callback_data="skip_buttons_step")]
    ])

def get_fsm_channels_kb(all_channels, selected: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ch in all_channels:
        icon = "✅" if ch['channel_id'] in selected else "⬜"
        builder.row(InlineKeyboardButton(text=f"{icon} {ch['title']}", callback_data=f"fsm_tglch_{ch['channel_id']}"))
    builder.row(InlineKeyboardButton(text="⏭ Далее к кнопкам", callback_data="fsm_channels_done"))
    builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_add"))
    return builder.as_markup()

def get_post_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Циклический (По интервалу)", callback_data="type_interval")],
        [InlineKeyboardButton(text="⏰ Единовременный (Отложенный)", callback_data="type_delayed")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_add")]
    ])

@router.callback_query(F.data == "menu_add_post")
async def start_add_post(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AddPostState.text)
    await callback.message.edit_text("📝 **Шаг 1 из 5: Текст поста**\n\nОтправьте текст публикации:", reply_markup=get_cancel_kb())

@router.message(AddPostState.text, F.text)
async def process_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    await state.set_state(AddPostState.media)
    try: await message.delete()
    except: pass
    await message.answer("🖼 **Шаг 2 из 5: Медиафайл**\n\nОтправьте фото/видео/gif или знак `-`, если медиа не нужно:", reply_markup=get_cancel_kb())

@router.message(AddPostState.media, F.photo | F.video | F.animation)
async def process_media_file(message: Message, state: FSMContext):
    media_id = message.photo[-1].file_id if message.photo else (message.video.file_id if message.video else message.animation.file_id)
    media_type = "photo" if message.photo else ("video" if message.video else "animation")
    await state.update_data(media_id=media_id, media_type=media_type, selected_channels=[])
    await state.set_state(AddPostState.channels)
    try: await message.delete()
    except: pass
    await message.answer("📡 **Шаг 3 из 5: Выберите каналы:**", reply_markup=get_fsm_channels_kb(get_all_channels_detailed(), []))

@router.message(AddPostState.media, F.text)
async def process_media_text(message: Message, state: FSMContext):
    text_input = message.text.strip()
    m_id, m_type = (None, "text") if text_input in ["-", "минус"] else (text_input, "unknown")
    await state.update_data(media_id=m_id, media_type=m_type, selected_channels=[])
    await state.set_state(AddPostState.channels)
    try: await message.delete()
    except: pass
    await message.answer("📡 **Шаг 3 из 5: Выберите каналы:**", reply_markup=get_fsm_channels_kb(get_all_channels_detailed(), []))

@router.callback_query(AddPostState.channels, F.data.startswith("fsm_tglch_"))
async def process_fsm_toggle_channel(callback: CallbackQuery, state: FSMContext):
    ch_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    selected = data.get("selected_channels", [])
    if ch_id in selected: selected.remove(ch_id)
    else: selected.append(ch_id)
    await state.update_data(selected_channels=selected)
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=get_fsm_channels_kb(get_all_channels_detailed(), selected))

@router.callback_query(AddPostState.channels, F.data == "fsm_channels_done")
async def process_fsm_channels_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("selected_channels"):
        await callback.answer(" Выберите хотя бы один канал!", show_alert=True)
        return
    await state.set_state(AddPostState.buttons_menu) # <-- Переводим в меню
    await callback.message.edit_text(" **Шаг 4 из 5: Настройка кнопок**", reply_markup=get_buttons_control_kb())

@router.callback_query(AddPostState.buttons_menu, F.data == "add_one_more_btn")
async def ask_button_name(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddPostState.button_name) # <-- Только теперь ждем имя кнопки
    await callback.message.edit_text("Введите название кнопки:", reply_markup=get_cancel_kb())

@router.message(AddPostState.button_name, F.text)
async def process_button_name(message: Message, state: FSMContext):
    await state.update_data(temp_btn_name=message.text)
    await state.set_state(AddPostState.button_url)
    try: await message.delete()
    except: pass
    await message.answer(f"Отправьте URL для кнопки «{message.text}»:", reply_markup=get_cancel_kb())

@router.message(AddPostState.button_url, F.text)
async def process_button_url(message: Message, state: FSMContext):
    url = message.text.strip()
    try: await message.delete()
    except: pass
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
        await message.answer("❌ Ссылка должна начинаться с http:// или https://:", reply_markup=get_cancel_kb())
        return
    data = await state.get_data()
    buttons = data.get("buttons", [])
    buttons.append({"text": data["temp_btn_name"], "url": url})
    await state.update_data(buttons=buttons, temp_btn_name=None)
    await state.set_state(AddPostState.button_name)
    await message.answer("✅ Кнопка добавлена!", reply_markup=get_buttons_control_kb())

@router.callback_query(AddPostState.button_name, F.data == "skip_buttons_step")
async def finish_buttons_step(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddPostState.post_type)
    await callback.message.edit_text("⚙️ **Шаг 5 из 5: Выберите тип публикации**", reply_markup=get_post_type_kb())

@router.callback_query(AddPostState.post_type, F.data == "type_interval")
async def choose_type_interval(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddPostState.interval)
    await callback.message.edit_text("🔄 **Ввод интервала**\n\nВведите интервал повторения (в минутах):", reply_markup=get_cancel_kb())

@router.message(AddPostState.interval, F.text)
async def process_interval_and_save(message: Message, state: FSMContext):
    try: await message.delete()
    except: pass
    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("❌ Введите целое число:", reply_markup=get_cancel_kb())
        return
    data = await state.get_data()
    add_post(
        media_type=data.get("media_type"),
        media_id=data.get("media_id"),
        text=data.get("text"),
        buttons=data.get("buttons", []),
        interval=int(message.text),
        publish_at=None,
        is_delayed=0,
        target_channels=data.get("selected_channels", [])
    )
    await state.clear()
    await message.answer("🎉 Циклический пост успешно добавлен в ротацию!", reply_markup=get_main_menu_kb())

@router.callback_query(AddPostState.post_type, F.data == "type_delayed")
async def choose_type_delayed(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddPostState.publish_time)
    current_tz = get_timezone()
    await callback.message.edit_text(
        f"⏰ **Ввод времени отложенного поста**\n\n"
        f"Выбранный часовой пояс: `{current_tz}`\n\n"
        f"Отправьте дату и время публикации в формате:\n`ДД.ММ.ГГГГ ЧЧ:ММ`\n\n"
        f"Пример: `25.12.2026 18:30`",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown"
    )

@router.message(AddPostState.publish_time, F.text)
async def process_delayed_time_and_save(message: Message, state: FSMContext):
    try: await message.delete()
    except: pass
    time_str = message.text.strip()
    
    try:
        datetime.strptime(time_str, "%d.%m.%Y %H:%M")
    except ValueError:
        await message.answer("❌ Неверный формат. Шаблон: `ДД.ММ.ГГГГ ЧЧ:ММ` (Пример: `17.08.2026 21:00`):", reply_markup=get_cancel_kb())
        return
        
    data = await state.get_data()
    add_post(
        media_type=data.get("media_type"),
        media_id=data.get("media_id"),
        text=data.get("text"),
        buttons=data.get("buttons", []),
        interval=None,
        publish_at=time_str,
        is_delayed=1,
        target_channels=data.get("selected_channels", [])
    )
    await state.clear()
    await message.answer(f"🎉 Отложенный пост сохранен! Публикация в `{time_str}` по вашему поясу.", reply_markup=get_main_menu_kb())

@router.callback_query(F.data == "cancel_add")
async def cancel_post_creation(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🤖 Действие отменено.", reply_markup=get_main_menu_kb())

