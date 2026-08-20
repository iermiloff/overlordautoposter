import json
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.models import (
    get_post_by_id, get_all_channels_detailed, update_post_channels,
    update_post_status, delete_post, update_last_posted, get_posts_count
)
from handlers.admin_menu import build_public_kb
from handlers.admin_posts_list import render_post_card, get_posts_list_kb

router = Router()

@router.callback_query(F.data.startswith("post_ch_"))
async def manage_post_channels(callback: CallbackQuery):
    parts = callback.data.split("_")
    post_id, page = int(parts[2]), int(parts[3])
    post = get_post_by_id(post_id)
    all_channels = get_all_channels_detailed()
    
    if not post:
        await callback.answer("❌ Пост не найден.", show_alert=True)
        return
        
    try: chosen_channels = json.loads(post['target_channels'])
    except: chosen_channels = []
    
    builder = InlineKeyboardBuilder()
    for ch in all_channels:
        icon = "✅" if ch['channel_id'] in chosen_channels else "❌"
        builder.row(InlineKeyboardButton(text=f"{icon} {ch['title']}", callback_data=f"tglch_{post_id}_{ch['channel_id']}_{page}"))
        
    builder.row(InlineKeyboardButton(text="💾 Сохранить и вернуться", callback_data=f"view_post_{post_id}_{page}"))
    text = f"📂 **Настройка каналов для поста #{post_id}**\n\nНажимайте на channels для выбора:"
    
    if callback.message.text: await callback.message.edit_text(text, reply_markup=builder.as_markup())
    else: await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("tglch_"))
async def toggle_channel_for_post(callback: CallbackQuery):
    parts = callback.data.split("_")
    post_id, channel_id, page = int(parts[1]), int(parts[2]), int(parts[3])
    post = get_post_by_id(post_id)
    if not post: return
    
    try: current_chosen = json.loads(post['target_channels'])
    except: current_chosen = []
    
    if channel_id in current_chosen: current_chosen.remove(channel_id)
    else: current_chosen.append(channel_id)
    
    update_post_channels(post_id, current_chosen)
    await callback.answer()
    
    all_channels = get_all_channels_detailed()
    builder = InlineKeyboardBuilder()
    for ch in all_channels:
        icon = "✅" if ch['channel_id'] in current_chosen else "❌"
        builder.row(InlineKeyboardButton(text=f"{icon} {ch['title']}", callback_data=f"tglch_{post_id}_{ch['channel_id']}_{page}"))
    builder.row(InlineKeyboardButton(text="💾 Сохранить и вернуться", callback_data=f"view_post_{post_id}_{page}"))
    
    text = f"📂 **Настройка каналов для поста #{post_id}**\n\nНажимайте на каналы для выбора:"
    if callback.message.text: await callback.message.edit_text(text, reply_markup=builder.as_markup())
    else:
        try: await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup())
        except: pass

@router.callback_query(F.data.startswith("toggle_"))
async def process_toggle_status(callback: CallbackQuery):
    parts = callback.data.split("_")
    post_id, page = int(parts[1]), int(parts[2])
    post = get_post_by_id(post_id)
    if post:
        new_status = 0 if post['is_active'] == 1 else 1
        update_post_status(post_id, new_status)
        await callback.answer("✅ Статус успешно изменен")
        await render_post_card(callback, post_id, page)

@router.callback_query(F.data.startswith("pub_now_"))
async def process_publish_now(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split("_")
    post_id, page = int(parts[2]), int(parts[3])
    post = get_post_by_id(post_id)
    all_channels_db = get_all_channels_detailed()
    
    if not post:
        await callback.answer("❌ Пост не найден.", show_alert=True)
        return
        
    try: chosen_channels = json.loads(post['target_channels'])
    except: chosen_channels = []
    
    available_ids = [ch['channel_id'] for ch in all_channels_db]
    channels = [ch_id for ch_id in chosen_channels if ch_id in available_ids]
    
    if not channels:
        await callback.answer("❌ Не выбрано ни одного доступного канала!", show_alert=True)
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
            print(f"Ошибка ручной отправки в канал {channel_id}: {e}")
            
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    update_last_posted(post_id, now_str)
    await callback.answer(f"🚀 Отправлено в {success_count} из {len(channels)} каналов!", show_alert=True)
    await render_post_card(callback, post_id, page)

@router.callback_query(F.data.startswith("confirm_del_"))
async def confirm_delete_post(callback: CallbackQuery):
    parts = callback.data.split("_")
    post_id, page = int(parts[2]), int(parts[3])
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💥 Да, удалить навсегда", callback_data=f"execute_del_{post_id}_{page}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_post_{post_id}_{page}")
    ]])
    text = f"⚠️ **Вы уверены, что хотите удалить пост #{post_id}?**\nЭто действие необратимо."
    if callback.message.text: await callback.message.edit_text(text, reply_markup=markup)
    else: await callback.message.edit_caption(caption=text, reply_markup=markup)

@router.callback_query(F.data.startswith("execute_del_"))
async def execute_delete_post(callback: CallbackQuery):
    parts = callback.data.split("_")
    post_id, page = int(parts[2]), int(parts[3])
    delete_post(post_id)
    await callback.answer("💥 Пост успешно удален", show_alert=True)
    
    if not callback.message.text:
        try: await callback.message.delete()
        except: pass
        
    total = get_posts_count()
    if total == 0:
        await callback.message.answer("Список постов пуст.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Главное меню", callback_data="to_main_menu")]]))
    else:
        await callback.message.answer(f"📋 **Список постов (Страница {page + 1}):**", reply_markup=get_posts_list_kb(page))

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import json
from database.models import update_post_field, update_post_media, get_post_by_id
from handlers.admin_posts_list import render_post_card

class EditPostFullState(StatesGroup):
    menu = State()
    waiting_text = State()
    waiting_media = State()
    waiting_btn_name = State()
    waiting_btn_url = State()
    waiting_interval = State()
    waiting_time = State()

def get_edit_menu_kb(post_id: int, page: int) -> InlineKeyboardMarkup:
    """Генерация клавиатуры выбора параметра для изменения"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Изменить текст", callback_data=f"ed_field_text_{post_id}_{page}"),
            InlineKeyboardButton(text="🖼 Изменить медиа", callback_data=f"ed_field_media_{post_id}_{page}")
        ],
        [
            InlineKeyboardButton(text="🔗 Сбросить кнопки", callback_data=f"ed_field_btns_{post_id}_{page}"),
            InlineKeyboardButton(text="⏱ Настройка времени", callback_data=f"ed_field_time_{post_id}_{page}")
        ],
        [
            InlineKeyboardButton(text="« В карточку поста", callback_data=f"view_post_{post_id}_{page}")
        ]
    ])

@router.callback_query(F.data.startswith("edit_post_"))
async def open_edit_main_menu(callback: CallbackQuery, state: FSMContext):
    """Входная точка: открывает главное меню редактирования (с поддержкой медиа-сообщений)"""
    await state.clear()
    parts = callback.data.split("_")
    post_id, page = int(parts[2]), int(parts[3])
    
    await state.update_data(ed_post_id=post_id, ed_page=page)
    await state.set_state(EditPostFullState.menu)
    
    text = f"⚙️ **Редактирование поста #{post_id}**\n\nВыберите параметр для настройки:"
    
    # Исправление бага: проверяем, содержит ли сообщение медиаданные
    if callback.message.photo or callback.message.video or callback.message.animation:
        await callback.message.edit_caption(caption=text, reply_markup=get_edit_menu_kb(post_id, page), parse_mode="Markdown")
    else:
        await callback.message.edit_text(text, reply_markup=get_edit_menu_kb(post_id, page), parse_mode="Markdown")

# --- 1. РЕДАКТИРОВАНИЕ ТЕКСТА ---
@router.callback_query(EditPostFullState.menu, F.data.startswith("ed_field_text_"))
async def edit_text_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditPostFullState.waiting_text)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="ed_back_to_menu")]])
    text = "📝 **Изменение текста**\n\nОтправьте в чат новый текст для публикации:"
    
    if callback.message.photo or callback.message.video or callback.message.animation:
        await callback.message.edit_caption(caption=text, reply_markup=cancel_kb, parse_mode="Markdown")
    else:
        await callback.message.edit_text(text, reply_markup=cancel_kb, parse_mode="Markdown")

@router.message(EditPostFullState.waiting_text, F.text)
async def edit_text_save(message: Message, state: FSMContext):
    data = await state.get_data()
    update_post_field(data["ed_post_id"], "text", message.text)
    try: await message.delete()
    except: pass
    await message.answer("✅ Текст успешно изменен!")
    await return_to_edit_menu(message, state)

# --- 2. РЕДАКТИРОВАНИЕ МЕДИА ---
@router.callback_query(EditPostFullState.menu, F.data.startswith("ed_field_media_"))
async def edit_media_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditPostFullState.waiting_media)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="ed_back_to_menu")]])
    text = "🖼 **Изменение медиа**\n\nОтправьте новое фото/видео/GIF или знак `-` для удаления медиафайла:"
    
    if callback.message.photo or callback.message.video or callback.message.animation:
        await callback.message.edit_caption(caption=text, reply_markup=cancel_kb, parse_mode="Markdown")
    else:
        await callback.message.edit_text(text, reply_markup=cancel_kb, parse_mode="Markdown")

@router.message(EditPostFullState.waiting_media)
async def edit_media_save(message: Message, state: FSMContext):
    data = await state.get_data()
    post_id = data["ed_post_id"]
    
    if message.text and message.text.strip() in ["-", "минус"]:
        update_post_media(post_id, "text", None)
        await message.answer("✅ Медиа удалено. Пост переведен в текстовый режим.")
    elif message.photo:
        update_post_media(post_id, "photo", message.photo[-1].file_id)
        await message.answer("✅ Фото успешно обновлено!")
    elif message.video:
        update_post_media(post_id, "video", message.video.file_id)
        await message.answer("✅ Видео успешно обновлено!")
    elif message.animation:
        update_post_media(post_id, "animation", message.animation.file_id)
        await message.answer("✅ GIF успешно обновлена!")
    else:
        await message.answer("❌ Формат не поддерживается. Отправьте медиа или `-`:")
        return

    try: await message.delete()
    except: pass
    await return_to_edit_menu(message, state)

router.callback_query(EditPostFullState.menu, F.data.startswith("ed_field_btns_"))
async def edit_btns_start(callback: CallbackQuery, state: FSMContext):
    await state.update_data(temp_buttons=[])
    await state.set_state(EditPostFullState.waiting_btn_name)
    control_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить все кнопки", callback_data="ed_clear_all_btns")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="ed_back_to_menu")]
    ])
    text = "🔗 **Настройка кнопок**\n\nВведите текст для первой кнопки (отправьте сообщением в чат):"
    
    # Исправление: Проверка медиа перед изменением
    if callback.message.photo or callback.message.video or callback.message.animation:
        await callback.message.edit_caption(caption=text, reply_markup=control_kb, parse_mode="Markdown")
    else:
        await callback.message.edit_text(text, reply_markup=control_kb, parse_mode="Markdown")

@router.callback_query(EditPostFullState.menu, F.data == "ed_clear_all_btns")
@router.callback_query(EditPostFullState.waiting_btn_name, F.data == "ed_clear_all_btns")
async def edit_btns_clear(callback: CallbackQuery, state: FSMContext):
    """Этот хэндлер теперь сработает всегда, гасит часики и очищает базу"""
    await callback.answer() # Сразу гасим часики в Telegram, чтобы не зависали
    
    data = await state.get_data()
    post_id = data.get("ed_post_id")
    page = data.get("ed_page", 0)
    
    if not post_id:
        # Если админ долго спал и стейт стерся, вытаскиваем ID прямо из текста сообщения
        try:
            # Текст: "⚙️ Редактирование поста #123" -> забираем 123
            post_id = int(callback.message.text.split("#")[1].split("\n")[0].strip())
        except:
            try:
                post_id = int(callback.message.caption.split("#")[1].split("\n")[0].strip())
            except:
                await callback.answer("❌ Сессия устарела. Вернитесь в список постов.", show_alert=True)
                return

    # Чистим базу данных строго в валидный пустой JSON-массив
    update_post_field(post_id, "buttons", "[]")
    await callback.answer("🗑 Все инлайн-кнопки успешно удалены!", show_alert=True)
    
    await state.set_state(EditPostFullState.menu)
    await state.update_data(ed_post_id=post_id, ed_page=page)
    
    text = f"⚙️ **Редактирование поста #{post_id}**\n\nВыберите параметр для настройки:"
    if callback.message.photo or callback.message.video or callback.message.animation:
        await callback.message.edit_caption(caption=text, reply_markup=get_edit_menu_kb(post_id, page), parse_mode="Markdown")
    else:
        await callback.message.edit_text(text, reply_markup=get_edit_menu_kb(post_id, page), parse_mode="Markdown")


@router.message(EditPostFullState.waiting_btn_name, F.text)
async def edit_btns_name_get(message: Message, state: FSMContext):
    await state.update_data(current_btn_name=message.text)
    await state.set_state(EditPostFullState.waiting_btn_url)
    try: await message.delete()
    except: pass
    await message.answer(f"Отправьте URL-ссылку для кнопки «{message.text}»:")

@router.message(EditPostFullState.waiting_btn_url, F.text)
async def edit_btns_url_get(message: Message, state: FSMContext):
    url = message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
        await message.answer("❌ Ссылка должна начинаться с http://, https:// или tg://. Попробуйте еще раз:")
        return
        
    data = await state.get_data()
    btns = data.get("temp_buttons", [])
    btns.append({"text": data["current_btn_name"], "url": url})
    await state.update_data(temp_buttons=btns, current_btn_name=None)
    try: await message.delete()
    except: pass
    
    control_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить еще кнопку", callback_data="ed_add_more_btn_action")],
        [InlineKeyboardButton(text="💾 Сохранить эти кнопки", callback_data="ed_save_btns_action")]
    ])
    await message.answer(f"✅ Кнопка добавлена! Всего кнопок в очереди: {len(btns)} шт.", reply_markup=control_kb)

@router.callback_query(F.data == "ed_add_more_btn_action")
async def edit_btns_more_loop(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditPostFullState.waiting_btn_name)
    await callback.message.answer("Введите название для следующей кнопки:")

@router.callback_query(F.data == "ed_save_btns_action")
async def edit_btns_finalize_save(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    update_post_field(data["ed_post_id"], "buttons", json.dumps(data["temp_buttons"]))
    await callback.answer("✅ Список кнопок обновлен!")
    await state.set_state(EditPostFullState.menu)
    
    text = f"⚙️ **Редактирование поста #{data['ed_post_id']}**"
    if callback.message.photo or callback.message.video or callback.message.animation:
        await callback.message.edit_caption(caption=text, reply_markup=get_edit_menu_kb(data["ed_post_id"], data["ed_page"]))
    else:
        await callback.message.edit_text(text, reply_markup=get_edit_menu_kb(data["ed_post_id"], data["ed_page"]))

# --- 4. НАСТРОЙКА ТАЙМИНГОВ ---
@router.callback_query(EditPostFullState.menu, F.data.startswith("ed_field_time_"))
async def edit_time_type_start(callback: CallbackQuery, state: FSMContext):
    type_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Сделать Циклическим", callback_data="ed_choose_cyclic")],
        [InlineKeyboardButton(text="📌 Сделать Отложенным", callback_data="ed_choose_delayed")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="ed_back_to_menu")]
    ])
    text = "⏱ **Настройка расписания**\n\nВыберите тип публикации:"
    
    # Исправление: Проверка медиа перед изменением
    if callback.message.photo or callback.message.video or callback.message.animation:
        await callback.message.edit_caption(caption=text, reply_markup=type_kb, parse_mode="Markdown")
    else:
        await callback.message.edit_text(text, reply_markup=type_kb, parse_mode="Markdown")

@router.callback_query(F.data == "ed_choose_cyclic")
async def edit_time_cyclic_input(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditPostFullState.waiting_interval)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="ed_back_to_menu")]])
    text = "Введите интервал повторения (в минутах):"
    
    if callback.message.photo or callback.message.video or callback.message.animation:
        await callback.message.edit_caption(caption=text, reply_markup=cancel_kb)
    else:
        await callback.message.edit_text(text, reply_markup=cancel_kb)

@router.message(EditPostFullState.waiting_interval, F.text)
async def edit_time_cyclic_save(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("❌ Введите положительное целое число минут:")
        return
    data = await state.get_data()
    post_id = data["ed_post_id"]
    
    update_post_field(post_id, "interval_min", int(message.text))
    update_post_field(post_id, "publish_at", None)
    update_post_field(post_id, "is_delayed", 0)
    try: await message.delete()
    except: pass
    await message.answer("✅ Пост переведен в циклический режим!")
    await return_to_edit_menu(message, state)

@router.callback_query(F.data == "ed_choose_delayed")
async def edit_time_delayed_input(callback: CallbackQuery, state: FSMContext):
    from database.models import get_timezone
    await state.set_state(EditPostFullState.waiting_time)
    current_tz = get_timezone()
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="ed_back_to_menu")]])
    text = f"**Ввод времени публикации**\n\nПояс: `{current_tz}`\nШаблон: `ДД.ММ.ГГГГ ЧЧ:ММ` (Пример: `25.12.2026 14:00`):"
    
    if callback.message.photo or callback.message.video or callback.message.animation:
        await callback.message.edit_caption(caption=text, reply_markup=cancel_kb, parse_mode="Markdown")
    else:
        await callback.message.edit_text(text, reply_markup=cancel_kb, parse_mode="Markdown")

@router.message(EditPostFullState.waiting_time, F.text)
async def edit_time_delayed_save(message: Message, state: FSMContext):
    from datetime import datetime
    time_str = message.text.strip()
    try:
        datetime.strptime(time_str, "%d.%m.%Y %H:%M")
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте шаблон `ДД.ММ.ГГГГ ЧЧ:ММ`:")
        return
        
    data = await state.get_data()
    post_id = data["ed_post_id"]
    
    update_post_field(post_id, "interval_min", None)
    update_post_field(post_id, "publish_at", time_str)
    update_post_field(post_id, "is_delayed", 1)
    try: await message.delete()
    except: pass
    await message.answer(f"✅ Переведено в отложенный режим! Время: {time_str}")
    await return_to_edit_menu(message, state)

# --- НАВИГАЦИЯ ---
@router.callback_query(F.data == "ed_back_to_menu")
async def edit_cancel_to_menu_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(EditPostFullState.menu)
    text = f"⚙️ **Редактирование поста #{data['ed_post_id']}**"
    
    if callback.message.photo or callback.message.video or callback.message.animation:
        await callback.message.edit_caption(caption=text, reply_markup=get_edit_menu_kb(data["ed_post_id"], data["ed_page"]))
    else:
        await callback.message.edit_text(text, reply_markup=get_edit_menu_kb(data["ed_post_id"], data["ed_page"]))

async def return_to_edit_menu(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(EditPostFullState.menu)
    text = f"⚙️ **Редактирование поста #{data['ed_post_id']}**"
    await message.answer(text, reply_markup=get_edit_menu_kb(data["ed_post_id"], data["ed_page"]))
