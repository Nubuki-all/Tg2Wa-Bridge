import asyncio
import io
from datetime import datetime as dt

from telethon.types import DocumentAttributeSticker, InputStickerSetEmpty
from wand.image import Image as wand_image

from bridge_bot.config import bot
from bridge_bot.utils.log_utils import logger
from bridge_bot.utils.media_utils import get_video_thumbnail
from bridge_bot.utils.msg_store import (
    delete_message,
    edit_message,
    get_message,
    save_message,
)
from bridge_bot.utils.msg_utils import (
    add_bridge_header_tg,
    get_wa_edit_data,
    replace_mentions_for_tg,
    replace_wa_mentions,
    whatsapp_md_to_telegram_md,
)
from bridge_bot.utils.parse_md import parse as custom_parse
from bridge_bot.utils.tg_transfer import upload_file


async def text_to_tg(event, tg_chat_id, client):
    """Forwards text messages to TG"""
    try:
        chat_id = event.chat.id
        msg = None
        text = await replace_mentions_for_tg(bot.tg_client, event.text)
        text = await replace_wa_mentions(text, event)
        text = add_bridge_header_tg(whatsapp_md_to_telegram_md(text), event.from_user)
        if event.reply_to_message:
            msg = await get_message(
                chat_id, tg_chat_id, wa_id=event.reply_to_message.id
            )
        rep = await bot.tg_client.send_message(
            tg_chat_id,
            text,
            reply_to=msg.tg_id if msg else None,
            parse_mode=custom_parse,
        )
        return await save_message(
            chat_id,
            tg_chat_id,
            event.from_user.jid,
            event._message,
            rep.id,
            event.id,
            timestamp=event.timestamp,
        )
    except Exception:
        await logger(Exception)


async def img_to_tg(event, tg_chat_id, client):
    """Forwards image messages to TG"""
    try:
        chat_id = event.chat.id
        msg = None
        image = await event.download()
        image = io.BytesIO(image)
        image.name = "image." + event.media.mimetype.split("/")[1]
        text = await replace_mentions_for_tg(bot.tg_client, event.caption)
        text = await replace_wa_mentions(text, event)
        text = add_bridge_header_tg(whatsapp_md_to_telegram_md(text), event.from_user)
        if event.reply_to_message:
            msg = await get_message(
                chat_id, tg_chat_id, wa_id=event.reply_to_message.id
            )
        rep = await bot.tg_client.send_file(
            tg_chat_id,
            image,
            caption=text,
            reply_to=msg.tg_id if msg else None,
            parse_mode=custom_parse,
        )
        return await save_message(
            chat_id,
            tg_chat_id,
            event.from_user.jid,
            event._message,
            rep.id,
            event.id,
            timestamp=event.timestamp,
        )
    except Exception:
        await logger(Exception)


async def vid_to_tg(event, tg_chat_id, client):
    """Forwards video messages to TG"""
    try:
        chat_id = event.chat.id
        msg = None
        video_ = await event.download()
        video = io.BytesIO(video_)
        video.name = (
            "video_"
            + dt.now().isoformat("_", "seconds")
            + "."
            + event.media.mimetype.split("/")[1]
        )
        text = await replace_mentions_for_tg(bot.tg_client, event.caption)
        text = await replace_wa_mentions(text, event)
        text = add_bridge_header_tg(whatsapp_md_to_telegram_md(text), event.from_user)
        if event.reply_to_message:
            msg = await get_message(
                chat_id, tg_chat_id, wa_id=event.reply_to_message.id
            )
        thum = await get_video_thumbnail(video_)
        video = await upload_file(client, video_) or video
        rep = await bot.tg_client.send_file(
            tg_chat_id,
            video,
            caption=text,
            thumb=thum,
            reply_to=msg.tg_id if msg else None,
            parse_mode=custom_parse,
        )
        return await save_message(
            chat_id,
            tg_chat_id,
            event.from_user.jid,
            event._message,
            rep.id,
            event.id,
            timestamp=event.timestamp,
        )
    except Exception:
        await logger(Exception)


async def audio_to_tg(event, tg_chat_id, client):
    """Forwards audio messages to TG"""
    try:
        chat_id = event.chat.id
        is_ptt = event.media.PTT
        msg = None
        if is_ptt:
            ext = ".opus"
            name = "voice"
        else:
            ext = ".mp3"
            name = "audio"
        audio = await event.download()
        audio = io.BytesIO(audio)
        audio.name = f"{name}_" + dt.now().isoformat("_", "seconds") + ext
        # text = await replace_mentions_for_tg(bot.tg_client, event.caption)
        text = ""
        text = add_bridge_header_tg(whatsapp_md_to_telegram_md(text), event.from_user)
        if event.reply_to_message:
            msg = await get_message(
                chat_id, tg_chat_id, wa_id=event.reply_to_message.id
            )
        rep = await bot.tg_client.send_file(
            tg_chat_id,
            audio,
            caption=text,
            reply_to=msg.tg_id if msg else None,
            voice_note=is_ptt,
            parse_mode=custom_parse,
        )
        return await save_message(
            chat_id,
            tg_chat_id,
            event.from_user.jid,
            event._message,
            rep.id,
            event.id,
            timestamp=event.timestamp,
        )
    except Exception:
        await logger(Exception)


async def doc_to_tg(event, tg_chat_id, client):
    """Forwards document messages to TG"""
    try:
        chat_id = event.chat.id
        msg = None
        document = await event.download()
        document = io.BytesIO(document)
        document.name = event.media.fileName
        text = await replace_mentions_for_tg(bot.tg_client, event.caption)
        text = await replace_wa_mentions(text, event)
        text = add_bridge_header_tg(whatsapp_md_to_telegram_md(text), event.from_user)
        if event.reply_to_message:
            msg = await get_message(
                chat_id, tg_chat_id, wa_id=event.reply_to_message.id
            )
        rep = await bot.tg_client.send_file(
            tg_chat_id,
            document,
            caption=text,
            force_document=True,
            reply_to=msg.tg_id if msg else None,
            parse_mode=custom_parse,
        )
        return await save_message(
            chat_id,
            tg_chat_id,
            event.from_user.jid,
            event._message,
            rep.id,
            event.id,
            timestamp=event.timestamp,
        )
    except Exception:
        await logger(Exception)


async def sticker_to_tg(event, tg_chat_id, client):
    """Forwards sticker messages to TG"""
    try:
        chat_id = event.chat.id
        ext = "webp"
        msg = None
        sticker = await event.download()
        if event.sticker.isAnimated:
            ext = "webm"
            with wand_image(blob=sticker, format="webp") as img:
                with img.convert("webm") as img2:
                    img2.coalesce()
                    sticker = img2.make_blob(format="webm")
        sticker = io.BytesIO(sticker)
        sticker.name = "sticker." + ext
        text = ""
        text = add_bridge_header_tg(whatsapp_md_to_telegram_md(text), event.from_user)
        if event.reply_to_message:
            msg = await get_message(
                chat_id, tg_chat_id, wa_id=event.reply_to_message.id
            )
        if not msg:
            rep = await bot.tg_client.send_file(
                tg_chat_id,
                sticker,
                attributes=[
                    DocumentAttributeSticker(alt="", stickerset=InputStickerSetEmpty())
                ],
            )
        else:
            rep = await bot.tg_client.send_file(
                tg_chat_id,
                sticker,
                attributes=[
                    DocumentAttributeSticker(alt="", stickerset=InputStickerSetEmpty())
                ],
                reply_to=msg.tg_id,
            )
        await rep.reply(text, parse_mode=custom_parse)
        return await save_message(
            chat_id,
            tg_chat_id,
            event.from_user.jid,
            event._message,
            rep.id,
            event.id,
            timestamp=event.timestamp,
        )
    except Exception:
        await logger(Exception)


async def delete_for_tg(event, tg_chat_id, client):
    "Deletes bridged messages when deleted on Whatsapp."
    try:
        chat_id = event.chat.id
        msg = await get_message(chat_id, tg_chat_id, wa_id=event.revoked_id)
        if not msg:
            return
        msg_id = msg.tg_id
        status = await delete_message(chat_id, tg_chat_id, msg_id)
        if not status:
            await logger(
                e=f"@wa_to_tg: Failed to delete message from database, msg;\n{msg}",
                error=True,
            )
        try:
            await bot.tg_client.delete_messages(tg_chat_id, msg_id)
        except Exception:
            pass
        # clean reaction messages in database (on both end)
        await delete_message(chat_id, tg_chat_id, msg_id, is_reaction=True)
        await delete_message(chat_id, tg_chat_id, wa_id=msg.wa_id, is_reaction=True)
    except Exception:
        await logger(Exception)


async def edit_for_tg(event, tg_chat_id, client):
    "Edits bridged messages when edited on Whatsapp."
    try:
        chat_id = event.chat.id
        msg = await get_message(chat_id, tg_chat_id, wa_id=event.edited_id)
        if not msg:
            return
        msg_id = msg.tg_id
        text = event.caption or event.text
        text = await replace_mentions_for_tg(bot.tg_client, text)
        text = await replace_wa_mentions(text, event)
        text = add_bridge_header_tg(whatsapp_md_to_telegram_md(text), event.from_user)
        update_data = get_wa_edit_data(event)
        if not update_data:
            await logger(
                e=f"@wa_to_tg: Unknown edit event, event;\n{event.message}", error=True
            )
            return
        status = await edit_message(chat_id, tg_chat_id, update_data, msg_id)
        if not status:
            await logger(
                e=f"@wa_to_tg: Failed to edit message in database, msg;\n{msg}",
                error=True,
            )
        try:
            await bot.tg_client.edit_message(
                tg_chat_id, msg_id, text, parse_mode=custom_parse
            )
        except Exception:
            pass
    except Exception:
        await logger(Exception)


async def edit_del_for_tg(event, tg_chat_id, client):
    if event.is_revoke:
        return await delete_for_tg(event, tg_chat_id, client)
    elif event.is_edit:
        return await edit_for_tg(event, tg_chat_id, client)


async def handle_reaction_msg(event, tg_chat_id, client):
    """Handles Whatsapp reaction updates and bridges them to Telegram as a live message"""
    try:
        chat_id = event.chat.id
        msg_id = event.reaction.key.ID
        msg_ = await get_message(chat_id, tg_chat_id, wa_id=msg_id)
        if not msg_:
            await logger(
                e=f"Original Whatsapp message with id: {msg_id} not found for reaction in chat: {chat_id}",
                warning=True,
            )
            return
        reaction_emoji = event.reaction.text
        reaction_text = (
            f"Reacted {reaction_emoji} to:"
            if reaction_emoji
            else "Removed their reaction"
        )
        text = add_bridge_header_tg(
            whatsapp_md_to_telegram_md(reaction_text), event.from_user
        )
        msg = await get_message(chat_id, tg_chat_id, wa_id=msg_id, is_reaction=True)
        if msg:
            try:
                await bot.tg_client.edit_message(
                    tg_chat_id, msg.tg_id, text, parse_mode=custom_parse
                )
            except Exception:
                pass
            return
        rep = await bot.tg_client.send_message(
            tg_chat_id,
            text,
            reply_to=msg_.tg_id,
            parse_mode=custom_parse,
        )
        return await save_message(
            chat_id,
            tg_chat_id,
            None,
            None,
            rep.id,
            msg_id,
            is_reaction=True,
            timestamp=event.timestamp,
        )
    except Exception:
        await logger(Exception)


filter_dict = {
    "audio": audio_to_tg,
    "conversation": text_to_tg,
    "document": doc_to_tg,
    "extendedText": text_to_tg,
    "image": img_to_tg,
    "sticker": sticker_to_tg,
    "video": vid_to_tg,
    "reaction": handle_reaction_msg,
    "protocol": edit_del_for_tg,
}


async def forward_events(event, _, client):
    chat_id = event.chat.id
    if chat_id not in bot.group_dict.get("active_wa_bridges"):
        return
    if not (handler := filter_dict.get(event.short_name)):
        return
    forwarders = [
        handler(event, bridge.get("tg_chat"), client)
        for bridge in bot.group_dict.setdefault("tg_bridges", {}).values()
        if bridge.get("wa_chat") == chat_id
    ]
    await asyncio.gather(*forwarders)


def add_wa_bridge_handlers():
    bot.add_handler(forward_events)
