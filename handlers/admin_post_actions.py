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
    text = f"📂 **Настройка каналов для поста #{post_id}**\n\nНажимайте на каналы для выбора:"
    
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

@router.callback_query(F.data.startswith("pub_now_{post_id}_{page}"))
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
