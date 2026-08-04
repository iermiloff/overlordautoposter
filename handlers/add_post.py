import json
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import config
from database.models import add_post
from handlers.admin_menu import get_main_menu_kb

router = Router()

# Состояния FSM машины
class AddPostState(StatesGroup):
    text = State()
    media = State()
    button_name = State()
    button_url = State()
    interval = State()

# Универсальная кнопка отмены для каждого шага
def get_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить создание", callback_data="cancel_add")]
    ])

# Меню управления кнопками
def get_buttons_control_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить кнопку", callback_data="add_one_more_btn")],
        [InlineKeyboardButton(text="⏳ Перейти к интервалу", callback_data="skip_buttons_step")]
    ])

# --- ТОЧКА ВХОДА (Вызывается из главного меню) ---
@router.callback_query(F.data == "menu_add_post")
async def start_add_post(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("❌ Доступ ограничен.", show_alert=True)
        return
        
    await state.clear()
    await state.set_state(AddPostState.text)
    await callback.message.edit_text(
        "📝 **Шаг 1 из 4: Текст поста**\n\nОтправьте текст, который будет содержать пост. "
        "Вы можете использовать стандартную разметку Telegram (жирный, курсив).",
        reply_markup=get_cancel_kb()
    )

# --- ШАГ 1: ТЕКСТ -> ПЕРЕХОД К МЕДИА ---
@router.message(AddPostState.text, F.text)
async def process_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    await state.set_state(AddPostState.media)
    
    # Удаляем сообщение пользователя, чтобы не засорять чат админки
    try:
        await message.delete()
    except Exception:
        pass

    await message.answer(
        "🎬 **Шаг 2 из 4: Медиафайл**\n\n"
        "Отправьте изображение, видео или GIF (анимацию).\n"
        "Также вы можете прислать `file_id` нужного медиафайла текстом.\n\n"
        "Если медиафайл для этого поста не нужен, отправьте знак минус: `-`",
        reply_markup=get_cancel_kb()
    )

# --- ШАГ 2: МЕДИАФАЙЛ (Если загружен напрямую) ---
@router.message(AddPostState.media, F.photo | F.video | F.animation)
async def process_media_file(message: Message, state: FSMContext):
    media_id = None
    media_type = None

    if message.photo:
        media_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.video:
        media_id = message.video.file_id
        media_type = "video"
    elif message.animation:
        media_id = message.animation.file_id
        media_type = "animation"

    await state.update_data(media_id=media_id, media_type=media_type)
    await state.set_state(AddPostState.button_name)
    
    try:
        await message.delete()
    except Exception:
        pass
        
    await message.answer(
        "🔘 **Шаг 3 из 4: Инлайн-кнопки**\n\n"
        "Вы можете прикрепить к посту интерактивные кнопки со ссылками для подписчиков.\n"
        "Сейчас у поста нет кнопок.",
        reply_markup=get_buttons_control_kb()
    )

# --- ШАГ 2: МЕДИАФАЙЛ (Если отправлен текстом или пропущен) ---
@router.message(AddPostState.media, F.text)
async def process_media_text(message: Message, state: FSMContext):
    text_input = message.text.strip()
    
    if text_input in ["-", "минус"]:
        await state.update_data(media_id=None, media_type="text")
    else:
        # Считаем, что менеджер передал готовый file_id строкой
        await state.update_data(media_id=text_input, media_type="unknown")
        
    await state.set_state(AddPostState.button_name)
    
    try:
        await message.delete()
    except Exception:
        pass
        
    await message.answer(
        "🔘 **Шаг 3 из 4: Инлайн-кнопки**\n\n"
        "Вы можете прикрепить к посту интерактивные кнопки со ссылками для подписчиков.\n"
        "Сейчас у поста нет кнопок.",
        reply_markup=get_buttons_control_kb()
    )

# --- ШАГ 3: КНОПКИ (Запрос названия) ---
@router.callback_query(AddPostState.button_name, F.data == "add_one_more_btn")
async def ask_button_name(callback: CallbackQuery):
    await callback.message.edit_text(
        "Введите **название** для кнопки (текст, который увидят подписчики):",
        reply_markup=get_cancel_kb()
    )

# --- ШАГ 3: КНОПКИ (Приняли название -> Запрос ссылки) ---
@router.message(AddPostState.button_name, F.text)
async def process_button_name(message: Message, state: FSMContext):
    await state.update_data(temp_btn_name=message.text)
    await state.set_state(AddPostState.button_url)
    
    try:
        await message.delete()
    except Exception:
        pass
        
    await message.answer(
        f"Теперь отправьте **URL-ссылку** для кнопки «{message.text}»:\n"
        "Ссылка обязательно должна начинаться с http://, https:// или tg://",
        reply_markup=get_cancel_kb()
    )

# --- ШАГ 3: КНОПКИ (Приняли ссылку -> Валидация -> Вывод списка) ---
@router.message(AddPostState.button_url, F.text)
async def process_button_url(message: Message, state: FSMContext):
    url = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass

    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
        await message.answer(
            "❌ Некорректный формат ссылки! Она должна начинаться с http://, https:// или tg://\n"
            "Попробуйте отправить ссылку еще раз:",
            reply_markup=get_cancel_kb()
        )
        return

    data = await state.get_data()
    buttons = data.get("buttons", [])
    
    # Сохраняем новую кнопку в массив данных FSM
    buttons.append({"text": data["temp_btn_name"], "url": url})
    await state.update_data(buttons=buttons, temp_btn_name=None)
    
    # Формируем список уже добавленных кнопок для наглядности
    buttons_preview = ""
    for idx, btn in enumerate(buttons, 1):
        buttons_preview += f"{idx}. [{btn['text']}] -> {btn['url']}\n"

    await state.set_state(AddPostState.button_name)
    await message.answer(
        f"🔘 **Шаг 3 из 4: Инлайн-кнопки**\n\n"
        f"Список добавленных кнопок:\n{buttons_preview}\n"
        f"Вы можете добавить еще одну кнопку или перейти к следующему шагу.",
        reply_markup=get_buttons_control_kb()
    )

# --- ШАГ 3 -> ШАГ 4: Переход к интервалу ---
@router.callback_query(AddPostState.button_name, F.data == "skip_buttons_step")
async def finish_buttons_step(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddPostState.interval)
    await callback.message.edit_text(
        "⏳ **Шаг 4 из 4: Интервал автопостинга**\n\n"
        "Укажите интервал повторения для этого поста в **минутах**.\n"
        "Например, введите `60` для публикации каждый час, или `1440` для публикации раз в сутки.",
        reply_markup=get_cancel_kb()
    )

# --- ШАГ 4: ИНТЕРВАЛ -> СОХРАНЕНИЕ В БД ---
@router.message(AddPostState.interval, F.text)
async def process_interval_and_save(message: Message, state: FSMContext):
    try:
        await message.delete()
    except Exception:
        pass

    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer(
            "❌ Пожалуйста, введите целое положительное число минут:",
            reply_markup=get_cancel_kb()
        )
        return

    interval = int(message.text)
    data = await state.get_data()
    
    # Сохраняем все собранные данные в SQLite
    add_post(
        media_type=data.get("media_type"),
        media_id=data.get("media_id"),
        text=data.get("text"),
        buttons=data.get("buttons", []),
        interval=interval
    )
    
    await state.clear()
    await message.answer(
        "🎉 **Пост успешно создан и добавлен в систему автопостинга!**\n"
        "Он автоматически стал активным и попал в ротацию меню.",
        reply_markup=get_main_menu_kb()
    )

# --- ОТМЕНА НА ЛЮБОМ ШАГЕ ---
@router.callback_query(F.data == "cancel_add")
async def cancel_post_creation(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🤖 **Админ-панель автопостинга**\n\n❌ Создание поста отменено. Вы вернулись в главное меню:",
        reply_markup=get_main_menu_kb()
    )
