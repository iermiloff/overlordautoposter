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
    button_url = State()
    interval = State()

class EditPostState(StatesGroup):
    waiting_for_text = State()
    waiting_for_media = State()
    waiting_for_button_name = State()
    waiting_for_button_url = State()
    waiting_for_interval = State()

def get_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_add")]])

def get_buttons_control_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить кнопку", callback_data="add_one_more_btn")],
        [InlineKeyboardButton(text="⏳ Перейти к интервалу", callback_data="skip_buttons_step")]
    ])

def get_fsm_channels_kb(all_channels, selected: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ch in all_channels:
        icon = "✅" if ch['channel_id'] in selected else "◻️"
        builder.row(InlineKeyboardButton(text=f"{icon} {ch['title']}", callback_data=f"fsm_tglch_{ch['channel_id']}"))
    builder.row(InlineKeyboardButton(text="⏭ Далее к кнопкам", callback_data="fsm_channels_done"))
    builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_add"))
    return builder.as_markup()

# --- СЦЕНАРИЙ СОЗДАНИЯ ---
@router.callback_query(F.data == "menu_add_post")
async def start_add_post(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AddPostState.text)
    await callback.message.edit_text("📝 **Шаг 1 из 5: Текст поста**\n\nОтправьте текст:", reply_markup=get_cancel_kb())

@router.message(AddPostState.text, F.text)
async def process_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    await state.set_state(AddPostState.media)
    try: await message.delete()
    except: pass
    await message.answer("🎬 **Шаг 2 из 5: Медиафайл**\n\nОтправьте фото/видео/gif или `-` если медиа не нужно:", reply_markup=get_cancel_kb())

@router.message(AddPostState.media, F.photo | F.video | F.animation)
async def process_media_file(message: Message, state: FSMContext):
    media_id = message.photo[-1].file_id if message.photo else (message.video.file_id if message.video else message.animation.file_id)
    media_type = "photo" if message.photo else ("video" if message.video else "animation")
    await state.update_data(media_id=media_id, media_type=media_type, selected_channels=[])
    await state.set_state(AddPostState.channels)
    try: await message.delete()
    except: pass
    await message.answer("📢 **Шаг 3 из 5: Выберите каналы:**", reply_markup=get_fsm_channels_kb(get_all_channels_detailed(), []))

@router.message(AddPostState.media, F.text)
async def process_media_text(message: Message, state: FSMContext):
    text_input = message.text.strip()
    m_id, m_type = (None, "text") if text_input in ["-", "минус"] else (text_input, "unknown")
    await state.update_data(media_id=m_id, media_type=m_type, selected_channels=[])
    await state.set_state(AddPostState.channels)
    try: await message.delete()
    except: pass
    await message.answer("📢 **Шаг 3 из 5: Выберите каналы:**", reply_markup=get_fsm_channels_kb(get_all_channels_detailed(), []))

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
        await callback.answer("⚠️ Выберите каналы!", show_alert=True)
        return
    await state.set_state(AddPostState.button_name)
    await callback.message.edit_text("🔘 **Шаг 4 из 5: Кнопки**", reply_markup=get_buttons_control_kb())

@router.callback_query(AddPostState.button_name, F.data == "add_one_more_btn")
async def ask_button_name(callback: CallbackQuery):
    await callback.message.edit_text("Введите название кнопки:", reply_markup=get_cancel_kb())

@router.message(AddPostState.button_name, F.text)
async def process_button_name(message: Message, state: FSMContext):
    await state.update_data(temp_btn_name=message.text)
    await state.set_state(AddPostState.button_url)
    try: await message.delete()
    except: pass
    await message.answer(f"Отправьте URL-ссылку для «{message.text}»:", reply_markup=get_cancel_kb())

@router.message(AddPostState.button_url, F.text)
async def process_button_url(message: Message, state: FSMContext):
    url = message.text.strip()
    try: await message.delete()
    except: pass
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
        await message.answer("❌ Начните с http:// или https://:", reply_markup=get_cancel_kb())
        return
    data = await state.get_data()
    buttons = data.get("buttons", [])
    buttons.append({"text": data["temp_btn_name"], "url": url})
    await state.update_data(buttons=buttons, temp_btn_name=None)
    await state.set_state(AddPostState.button_name)
    await message.answer("🔘 Кнопка добавлена!", reply_markup=get_buttons_control_kb())

@router.callback_query(AddPostState.button_name, F.data == "skip_buttons_step")
async def finish_buttons_step(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddPostState.interval)
    await callback.message.edit_text("⏳ **Шаг 5 из 5: Интервал** (в минутах):", reply_markup=get_cancel_kb())

@router.message(AddPostState.interval, F.text)
async def process_interval_and_save(message: Message, state: FSMContext):
    try: await message.delete()
    except: pass
    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("❌ Введите число:", reply_markup=get_cancel_kb())
        return
    data = await state.get_data()
    add_post(data.get("media_type"), data.get("media_id"), data.get("text"), data.get("buttons", []), int(message.text), data.get("selected_channels", []))
    await state.clear()
    await message.answer("🎉 Пост успешно создан!", reply_markup=get_main_menu_kb())

# --- СЦЕНАРИЙ РЕДАКТИРОВАНИЯ ---
@router.callback_query(F.data.startswith("ed_txt_"))
async def edit_text_trigger(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    await state.update_data(edit_post_id=int(parts[2]), edit_page=int(parts[3]))
    await state.set_state(EditPostState.waiting_for_text)
    await callback.message.edit_text("📝 Введите **новый текст**:", reply_markup=get_cancel_kb())

@router.message(EditPostState.waiting_for_text, F.text)
async def process_edit_text(message: Message, state: FSMContext):
    data = await state.get_data()
    update_post_field(data['edit_post_id'], "text", message.text)
    await state.clear()
    await render_post_card(message, data['edit_post_id'], data['edit_page'])

@router.callback_query(F.data.startswith("ed_med_"))
async def edit_media_trigger(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    await state.update_data(edit_post_id=int(parts[2]), edit_page=int(parts[3]))
    await state.set_state(EditPostState.waiting_for_media)
    await callback.message.edit_text("🎬 Отправьте **новое медиа** или `-` для удаления:", reply_markup=get_cancel_kb())

@router.message(EditPostState.waiting_for_media)
async def process_edit_media(message: Message, state: FSMContext):
    data = await state.get_data()
    if message.text and message.text.strip() in ["-", "минус"]: update_post_media(data['edit_post_id'], "text", None)
    elif message.photo: update_post_media(data['edit_post_id'], "photo", message.photo[-1].file_id)
    elif message.video: update_post_media(data['edit_post_id'], "video", message.video.file_id)
    elif message.animation: update_post_media(data['edit_post_id'], "animation", message.animation.file_id)
    elif message.text: update_post_media(data['edit_post_id'], "unknown", message.text.strip())
    await state.clear()
    await render_post_card(message, data['edit_post_id'], data['edit_page'])

@router.callback_query(F.data.startswith("ed_int_"))
async def edit_interval_trigger(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    await state.update_data(edit_post_id=int(parts[2]), edit_page=int(parts[3]))
    await state.set_state(EditPostState.waiting_for_interval)
    await callback.message.edit_text("⏳ Введите **новый интервал** (мин):", reply_markup=get_cancel_kb())

@router.message(EditPostState.waiting_for_interval, F.text)
async def process_edit_interval(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) <= 0: return
    data = await state.get_data()
    update_post_field(data['edit_post_id'], "interval_min", int(message.text))
    await state.clear()
    await render_post_card(message, data['edit_post_id'], data['edit_page'])

# Безопасный фильтр на изменение кнопок (срабатывает, если в конце число)
@router.callback_query(F.data.startswith("ed_btn_"), lambda c: c.data.split("_")[-1].isdigit())
async def edit_buttons_trigger(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    await state.update_data(edit_post_id=int(parts[2]), edit_page=int(parts[3]), buttons=[])
    await state.set_state(EditPostState.waiting_for_button_name)
    await callback.message.edit_text("🔘 **Перезапись кнопок**\n\nВведите название первой кнопки:", reply_markup=get_cancel_kb())

@router.message(EditPostState.waiting_for_button_name, F.text)
async def process_edit_btn_name(message: Message, state: FSMContext):
    await state.update_data(temp_btn_name=message.text)
    await state.set_state(EditPostState.waiting_for_button_url)
    try: await message.delete()
    except: pass
    await message.answer(f"Отправьте URL для «{message.text}»:", reply_markup=get_cancel_kb())

@router.message(EditPostState.waiting_for_button_url, F.text)
async def process_edit_btn_url(message: Message, state: FSMContext):
    url = message.text.strip()
    try: await message.delete()
    except: pass
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")): return

    data = await state.get_data()
    buttons = data.get("buttons", [])
    buttons.append({"text": data["temp_btn_name"], "url": url})
    await state.update_data(buttons=buttons, temp_btn_name=None)
    update_post_field(data['edit_post_id'], "buttons", json.dumps(buttons))
    
    control_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить еще", callback_data="subbtn_more")],
        [InlineKeyboardButton(text="💾 Сохранить и выйти", callback_data="subbtn_save")]
    ])
    await state.set_state(EditPostState.waiting_for_button_name)
    await message.answer(f"🔘 Добавлено кнопок: {len(buttons)}", reply_markup=control_kb)

@router.callback_query(EditPostState.waiting_for_button_name, F.data == "subbtn_more")
async def edit_more_btn_click(callback: CallbackQuery):
    await callback.message.edit_text("Введите название следующей кнопки:", reply_markup=get_cancel_kb())

@router.callback_query(EditPostState.waiting_for_button_name, F.data == "subbtn_save")
async def edit_btn_save_click(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.message.delete()
    await state.clear()
    await render_post_card(callback.message, data['edit_post_id'], data['edit_page'])

# --- ОТМЕНА ---
@router.callback_query(F.data == "cancel_add")
async def cancel_post_creation(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🤖 **Админ-панель**\n\nДействие отменено.", reply_markup=get_main_menu_kb())
