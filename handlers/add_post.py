from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import config
from database.models import add_post

router = Router()

# Ограничиваем доступ: только для ID из .env
@router.message(lambda message: message.from_user.id not in config.ADMIN_IDS)
async def access_denied(message: Message):
    await message.answer("❌ Доступ в админ-панель ограничен.")
    return

# Состояния FSM
class AddPostState(StatesGroup):
    text = State()
    media = State()
    button_name = State()
    button_url = State()
    interval = State()

# Клавиатура отмены
def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить создание", callback_data="cancel_add")]
    ])

# Клавиатура завершения ввода кнопок
def buttons_control_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить кнопку", callback_data="add_more_btn")],
        [InlineKeyboardButton(text="⏭ Пропустить / К интервалу", callback_data="skip_buttons")]
    ])

# Накало создания поста (вызывается из главного меню)
@router.callback_query(F.data == "menu_add_post")
async def start_add_post(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AddPostState.text)
    await callback.message.edit_text("📝 **Шаг 1:** Отправьте текст для будущего поста.", reply_markup=cancel_kb())

# 1. Получение текста
@router.message(AddPostState.text)
async def process_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text)
    await state.set_state(AddPostState.media)
    
    await message.answer(
        "🎬 **Шаг 2:** Отправьте медиафайл (Картинку, Видео или GIF).\n"
        "Вы можете отправить файл напрямую или прислать его `file_id` текстом.\n"
        "Если медиа не требуется, отправьте кодовое слово: `минус`",
        reply_markup=cancel_kb()
    )

# 2. Получение медиа (Файлом)
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
    await message.answer("🔘 **Шаг 3:** Переходим к кнопкам. Хотите добавить инлайн-ссылку?", reply_markup=buttons_control_kb())

# 2. Получение медиа (Текстом: file_id или без медиа)
@router.message(AddPostState.media, F.text)
async def process_media_text(message: Message, state: FSMContext):
    text_low = message.text.lower().strip()
    if text_low in ["минус", "-", "no"]:
        await state.update_data(media_id=None, media_type="text")
    else:
        # Считаем, что пользователь передал file_id текстом. Проверку типа сделаем при постинге.
        await state.update_data(media_id=message.text, media_type="unknown")
    
    await state.set_state(AddPostState.button_name)
    await message.answer("🔘 **Шаг 3:** Переходим к кнопкам. Хотите добавить инлайн-ссылку?", reply_markup=buttons_control_kb())

# 3. Кнопки: Запрос названия
@router.callback_query(AddPostState.button_name, F.data == "add_more_btn")
async def ask_button_name(callback: CallbackQuery):
    await callback.message.edit_text("Введите **название** для кнопки (текст, который увидят пользователи):", reply_markup=cancel_kb())

# 3. Кнопки: Запрос ссылки
@router.message(AddPostState.button_name, F.text)
async def process_button_name(message: Message, state: FSMContext):
    await state.update_data(current_btn_name=message.text)
    await state.set_state(AddPostState.button_url)
    await message.answer(f"Теперь отправьте **URL-ссылку** для кнопки «{message.text}»:", reply_markup=cancel_kb())

# 3. Кнопки: Валидация ссылки и сохранение в массив
@router.message(AddPostState.button_url, F.text)
async def process_button_url(message: Message, state: FSMContext):
    url = message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
        await message.answer("❌ Ссылка должна начинаться с http://, https:// или tg://. Попробуйте еще раз:")
        return

    user_data = await state.get_data()
    buttons = user_data.get("buttons", [])
    
    # Добавляем новую кнопку в список
    buttons.append({"text": user_data["current_btn_name"], "url": url})
    await state.update_data(buttons=buttons)
    
    await state.set_state(AddPostState.button_name)
    await message.answer(f"✅ Кнопка «{user_data['current_btn_name']}» успешно добавлена!\nВсего кнопок: {len(buttons)}", reply_markup=buttons_control_kb())

# 4. Пропуск кнопок -> Переход к интервалу
@router.callback_query(AddPostState.button_name, F.data == "skip_buttons")
async def skip_buttons(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddPostState.interval)
    await callback.message.edit_text("⏳ **Шаг 4:** Укажите интервал повторения постинга в **минутах** (например, `60` или `1440`):", reply_markup=cancel_kb())

# 5. Интервал и финальное сохранение
@router.message(AddPostState.interval, F.text)
async def process_interval(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("❌ Пожалуйста, введите корректное число минут (целое, больше нуля):")
        return

    interval = int(message.text)
    data = await state.get_data()
    
    # Записываем в БД
    add_post(
        media_type=data.get("media_type"),
        media_id=data.get("media_id"),
        text=data.get("text"),
        buttons=data.get("buttons", []),
        interval=interval
    )
    
    await state.clear()
    await message.answer("🎉 **Пост успешно создан!** Он добавлен в базу данных со статусом «Активен».")

# Сброс FSM
@router.callback_query(F.data == "cancel_add")
async def cancel_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Создание поста отменено. Вы вернулись в главное меню.")
