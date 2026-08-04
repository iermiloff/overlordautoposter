from aiogram import Router, F
from aiogram.types import ChatMemberUpdated
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, JOIN_TRANSITION, LEAVE_TRANSITION, ADMINISTRATOR
from database.models import add_channel, remove_channel

router = Router()

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=ADMINISTRATOR))
async def bot_added_as_admin(event: ChatMemberUpdated):
    """Вызывается, когда бота добавляют в админы канала или меняют права"""
    if event.new_chat_member.status == "administrator":
        add_channel(event.chat.id, event.chat.title)
    else:
        # Если права забрали
        remove_channel(event.chat.id)
