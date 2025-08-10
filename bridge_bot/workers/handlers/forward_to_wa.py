import asyncio

from telethon import events

from bridge_bot import bot, heavy_proc_lock, jid
from bridge_bot.utils.bot_utils import get_sticker_pack
from bridge_bot.utils.log_utils import logger
from bridge_bot.utils.media_utils import (
    all_vid_streams_avc,
    convert_to_avc,
    convert_to_wa_sticker,
)
from bridge_bot.utils.msg_store import (
    delete_message,
    edit_message,
    get_message,
    save_message,
)
from bridge_bot.utils.msg_utils import (
    construct_message,
    conv_tgmd_to_wamd,
    get_subscription_header,
    get_tg_edit_data,
    load_proto,
)
from bridge_bot.utils.os_utils import s_remove, size_of
from bridge_bot.utils.tg_transfer import download_file


async def forward_texts(event):
    """Forwards text messages to WA from a Tg channel"""
    try:
        chat_id = event.chat_id
        if not (
            subscribed_info := bot.group_dict.setdefault("subscribed_channels", {}).get(
                chat_id
            )
        ):
            return

        func_list = [
            forward_text(event, chat_id) for chat_id in subscribed_info.get("chats")
        ]
        await asyncio.gather(*func_list)
    except Exception:
        await logger(Exception)


async def forward_text(event, wa_chat_id):
    try:
        msg = None
        chat_id = event.chat_id
        text = event.raw_text
        wa_jid = jid.build_jid(wa_chat_id, "g.us")
        text = get_subscription_header(event) + conv_tgmd_to_wamd(text, event.entities)
        if event.reply_to:
            msg = await get_message(wa_chat_id, chat_id, event.reply_to.reply_to_msg_id)
        if msg:
            Msg = load_proto(msg.raw)
            user_jid = load_proto(msg.raw_user, True)
            wa_msg = construct_message(
                wa_chat_id, user_jid.User, msg.wa_id, None, "g.us", user_jid.Server, Msg
            )
            rep = await bot.client.reply_message(text, wa_msg, to=wa_jid)
        else:
            rep = await bot.client.send_message(wa_jid, text)
        return await save_message(
            wa_chat_id,
            chat_id,
            None,
            rep.Message,
            event.id,
            rep.ID,
            timestamp=rep.Timestamp,
        )
    except Exception:
        await logger(Exception)


async def forward_images(event):
    """Forwards images to WA"""
    try:
        chat_id = event.chat_id
        if not (
            subscribed_info := bot.group_dict.setdefault("subscribed_channels", {}).get(
                chat_id
            )
        ):
            return
        image = await event.download_media(file=bytes)
        func_list = [
            forward_image(event, chat_id, image)
            for chat_id in subscribed_info.get("chats")
        ]
        await asyncio.gather(*func_list)
    except Exception:
        await logger(Exception)


async def forward_image(event, wa_chat_id, image):
    try:
        msg = wa_msg = None
        chat_id = event.chat_id
        text = event.raw_text
        wa_jid = jid.build_jid(wa_chat_id, "g.us")
        text = get_subscription_header(event) + conv_tgmd_to_wamd(text, event.entities)
        if event.reply_to:
            msg = await get_message(wa_chat_id, chat_id, event.reply_to.reply_to_msg_id)
        if msg:
            Msg = load_proto(msg.raw)
            user_jid = load_proto(msg.raw_user, True)
            wa_msg = construct_message(
                wa_chat_id, user_jid.User, msg.wa_id, None, "g.us", user_jid.Server, Msg
            )
        rep = await bot.client.send_image(wa_jid, image, text, quoted=wa_msg)
        return await save_message(
            wa_chat_id,
            chat_id,
            None,
            rep.Message,
            event.id,
            rep.ID,
            timestamp=rep.Timestamp,
        )
    except Exception:
        await logger(Exception)


async def forward_gifs(event):
    """Forwards gif messages to WA"""
    try:
        chat_id = event.chat_id
        if not (
            subscribed_info := bot.group_dict.setdefault("subscribed_channels", {}).get(
                chat_id
            )
        ):
            return
        _id = f"{event.chat.id}:{event.id}"
        in_ = f"temp/{_id}.gif"
        out_ = await event.download_media(file=in_)
        func_list = [
            forward_gif(event, chat_id, out_)
            for chat_id in subscribed_info.get("chats")
        ]
        await asyncio.gather(*func_list)
        s_remove(out_)
    except Exception:
        await logger(Exception)


async def forward_gif(event, wa_chat_id, gif):
    try:
        msg = wa_msg = None
        chat_id = event.chat_id
        event.file.name
        text = event.raw_text
        wa_jid = jid.build_jid(wa_chat_id, "g.us")
        up_as_doc = False
        if size_of(gif) > 100000000:
            up_as_doc = True
        text = get_subscription_header(event) + conv_tgmd_to_wamd(text, event.entities)
        if event.reply_to:
            msg = await get_message(wa_chat_id, chat_id, event.reply_to.reply_to_msg_id)
        if msg:
            Msg = load_proto(msg.raw)
            user_jid = load_proto(msg.raw_user, True)
            wa_msg = construct_message(
                wa_chat_id, user_jid.User, msg.wa_id, None, "g.us", user_jid.Server, Msg
            )
        rep = (
            await bot.client.send_video(
                wa_jid,
                gif,
                text,
                quoted=wa_msg,
                gifplayback=True,
                is_gif=True,
            )
            if not up_as_doc
            else await bot.client.send_document(
                wa_jid, gif, text, quoted=wa_msg, filename=event.file.name
            )
        )
        await save_message(
            wa_chat_id,
            chat_id,
            None,
            rep.Message,
            event.id,
            rep.ID,
            timestamp=rep.Timestamp,
        )
        return
    except Exception:
        await logger(Exception)


async def forward_vids(event):
    """Forwards video messages to WA"""
    try:
        chat_id = event.chat_id
        if not (
            subscribed_info := bot.group_dict.setdefault("subscribed_channels", {}).get(
                chat_id
            )
        ):
            return
        _id = f"{event.chat.id}:{event.id}"
        in_ = f"temp/{_id}.mp4"
        out_ = f"temp/{_id}-1.mp4"
        await download_file(event.client, event.video, in_, event)
        if not await all_vid_streams_avc(in_):
            async with heavy_proc_lock:
                await convert_to_avc(in_, out_)
            s_remove(in_)
        else:
            out_ = in_
        func_list = [
            forward_vid(event, chat_id, out_)
            for chat_id in subscribed_info.get("chats")
        ]
        await asyncio.gather(*func_list)
        s_remove(out_)
    except Exception:
        await logger(Exception)


async def forward_vid(event, wa_chat_id, vid):
    try:
        msg = wa_msg = None
        chat_id = event.chat_id
        event.file.name
        text = event.raw_text
        wa_jid = jid.build_jid(wa_chat_id, "g.us")
        up_as_doc = False
        # in_ = await event.download_media(file=in_)
        if size_of(vid) > 100000000:
            up_as_doc = True
        text = get_subscription_header(event) + conv_tgmd_to_wamd(text, event.entities)
        if event.reply_to:
            msg = await get_message(wa_chat_id, chat_id, event.reply_to.reply_to_msg_id)
        if msg:
            Msg = load_proto(msg.raw)
            user_jid = load_proto(msg.raw_user, True)
            wa_msg = construct_message(
                wa_chat_id, user_jid.User, msg.wa_id, None, "g.us", user_jid.Server, Msg
            )
        rep = (
            await bot.client.send_video(
                wa_jid,
                vid,
                text,
                quoted=wa_msg,
            )
            if not up_as_doc
            else await bot.client.send_document(
                wa_jid, vid, text, quoted=wa_msg, filename=event.file.name
            )
        )
        await save_message(
            wa_chat_id,
            chat_id,
            None,
            rep.Message,
            event.id,
            rep.ID,
            timestamp=rep.Timestamp,
        )
        return
    except Exception:
        await logger(Exception)


async def forward_audios(event):
    """Forwards audio messages to WA"""
    try:
        chat_id = event.chat_id
        if not (
            subscribed_info := bot.group_dict.setdefault("subscribed_channels", {}).get(
                chat_id
            )
        ):
            return
        audio = await download_file(event.client, event.document, bytes, event)
        func_list = [
            forward_audio(event, chat_id, audio)
            for chat_id in subscribed_info.get("chats")
        ]
        await asyncio.gather(*func_list)
    except Exception:
        await logger(Exception)


async def forward_audio(event, wa_chat_id, audio):
    try:
        # audio = await event.download_media(file=bytes)
        chat_id = event.chat_id
        msg = wa_msg = None
        text = event.raw_text
        wa_jid = jid.build_jid(wa_chat_id, "g.us")
        get_subscription_header
        text = get_subscription_header(event) + conv_tgmd_to_wamd(text, event.entities)
        if event.reply_to:
            msg = await get_message(wa_chat_id, chat_id, event.reply_to.reply_to_msg_id)
        if msg:
            Msg = load_proto(msg.raw)
            user_jid = load_proto(msg.raw_user, True)
            wa_msg = construct_message(
                wa_chat_id, user_jid.User, msg.wa_id, None, "g.us", user_jid.Server, Msg
            )
        rep = await bot.client.send_audio(
            wa_jid, audio, bool(event.voice), quoted=wa_msg
        )
        await save_message(
            wa_chat_id,
            chat_id,
            None,
            rep.Message,
            event.id,
            rep.ID,
            timestamp=rep.Timestamp,
        )
        user_jid = bot.client.me.JID
        wa_msg_ = construct_message(
            wa_chat_id,
            user_jid.User,
            rep.ID,
            None,
            "g.us",
            user_jid.Server,
            rep.Message,
        )
        await bot.client.reply_message(text, wa_msg_, to=wa_jid)
    except Exception:
        await logger(Exception)


async def forward_docs(event):
    """Forwards document messages to WA"""
    try:
        chat_id = event.chat_id
        if not (
            subscribed_info := bot.group_dict.setdefault("subscribed_channels", {}).get(
                chat_id
            )
        ):
            return
        _id = f"{event.chat.id}:{event.id}"
        doc = f"temp/{_id}_{event.file.name}"
        await download_file(event.client, event.document, doc, event)
        func_list = [
            forward_doc(event, chat_id, doc) for chat_id in subscribed_info.get("chats")
        ]
        await asyncio.gather(*func_list)
        s_remove(doc)
    except Exception:
        await logger(Exception)


async def forward_doc(event, wa_chat_id, doc):
    try:

        chat_id = event.chat_id
        # doc = await event.download_media(file=in_)
        msg = wa_msg = None
        text = event.raw_text
        wa_jid = jid.build_jid(wa_chat_id, "g.us")
        text = get_subscription_header(event) + conv_tgmd_to_wamd(text, event.entities)
        if event.reply_to:
            msg = await get_message(wa_chat_id, chat_id, event.reply_to.reply_to_msg_id)
        if msg:
            Msg = load_proto(msg.raw)
            user_jid = load_proto(msg.raw_user, True)
            wa_msg = construct_message(
                wa_chat_id, user_jid.User, msg.wa_id, None, "g.us", user_jid.Server, Msg
            )
        rep = await bot.client.send_document(
            wa_jid, doc, text, event.file.name, quoted=wa_msg
        )
        return await save_message(
            wa_chat_id,
            chat_id,
            None,
            rep.Message,
            event.id,
            rep.ID,
            timestamp=rep.Timestamp,
        )
    except Exception:
        await logger(Exception)


async def forward_stickers(event):
    """Forwards sticker messages to WA"""
    try:
        chat_id = event.chat_id
        if not (
            subscribed_info := bot.group_dict.setdefault("subscribed_channels", {}).get(
                chat_id
            )
        ):
            return
        sticker = await event.download_media(file=bytes)
        try:
            stickerset = await get_sticker_pack(event)
        except Exception as e:
            await logger(e=e, warning=True)
            stickerset = None
        packname = stickerset.set.title if stickerset else "None"
        sticker = await convert_to_wa_sticker(sticker, event.file.name, packname)
        func_list = [
            forward_sticker(event, chat_id, sticker)
            for chat_id in subscribed_info.get("chats")
        ]
        await asyncio.gather(*func_list)
    except Exception:
        await logger(Exception)


async def forward_sticker(event, wa_chat_id, sticker):
    try:
        chat_id = event.chat_id
        msg = wa_msg = None
        wa_jid = jid.build_jid(wa_chat_id, "g.us")
        text = get_subscription_header(event)
        if event.reply_to:
            msg = await get_message(wa_chat_id, chat_id, event.reply_to.reply_to_msg_id)
        if msg:
            Msg = load_proto(msg.raw)
            user_jid = load_proto(msg.raw_user, True)
            wa_msg = construct_message(
                wa_chat_id, user_jid.User, msg.wa_id, None, "g.us", user_jid.Server, Msg
            )
        rep = await bot.client.send_sticker(
            wa_jid, sticker, quoted=wa_msg, passthrough=True
        )
        await save_message(
            wa_chat_id,
            chat_id,
            None,
            rep.Message,
            event.id,
            rep.ID,
            timestamp=rep.Timestamp,
        )
        user_jid = bot.client.me.JID
        wa_msg_ = construct_message(
            wa_chat_id,
            user_jid.User,
            rep.ID,
            None,
            "g.us",
            user_jid.Server,
            rep.Message,
        )
        await bot.client.reply_message(text, wa_msg_, to=wa_jid)
    except Exception:
        await logger(Exception)


async def handle_edits(event):
    """Handle messages changes and relay them to WA"""
    try:
        chat_id = event.chat_id
        if not (
            subscribed_info := bot.group_dict.setdefault("subscribed_channels", {}).get(
                chat_id
            )
        ):
            return
        func_list = [
            relay_edit(event, chat_id) for chat_id in subscribed_info.get("chats")
        ]
        for func in func_list:
            await func
            await asyncio.sleep(5)
    except Exception:
        await logger(Exception)


async def relay_edit(event, wa_chat_id):
    try:
        chat_id = event.chat_id
        msg_id = event.id
        text = event.raw_text
        msg = await get_message(wa_chat_id, chat_id, msg_id)
        if not msg:
            return
        text = get_subscription_header(event) + conv_tgmd_to_wamd(text, event.entities)
        update_data, edit_msg = get_tg_edit_data(text, msg.raw)
        if not update_data:
            await logger(
                e=f"@relay_edit: msg does not support editing on Whatsapp's end, msg;\n{msg}",
                warning=True,
            )
            return
        try:
            await bot.client.edit_message(
                jid.build_jid(wa_chat_id, "g.us"), msg.wa_id, edit_msg
            )
        except Exception:
            await logger(Exception)
        status = await edit_message(wa_chat_id, chat_id, update_data, msg_id)
        if not status:
            await logger(
                e=f"@relay_edit: Failed to edit message in database, msg;\n{msg}",
                error=True,
            )
    except Exception:
        await logger(Exception)


async def handle_deletes(event):
    """Handle messages deletion and relay them to WA"""
    try:
        chat_id = event.chat_id
        if not (
            subscribed_info := bot.group_dict.setdefault("subscribed_channels", {}).get(
                chat_id
            )
        ):
            return
        func_list = [
            relay_delete(event, chat_id) for chat_id in subscribed_info.get("chats")
        ]
        for func in func_list:
            await func
            await asyncio.sleep(5)
    except Exception:
        await logger(Exception)


async def relay_delete(event, wa_chat_id):
    try:
        chat_id = event.chat_id
        for msg_id in event.deleted_ids:
            msg = await get_message(wa_chat_id, chat_id, msg_id)
            if not msg:
                continue
            Msg = load_proto(msg.raw)
            user_jid = load_proto(msg.raw_user, True)
            wa_msg = construct_message(
                wa_chat_id, user_jid.User, msg.wa_id, None, "g.us", user_jid.Server, Msg
            )
            await bot.client.reply_message(
                "⚠️ *This message has been deleted!*",
                wa_msg,
                to=jid.build_jid(wa_chat_id, "g.us"),
            )
            status = await delete_message(wa_chat_id, chat_id, msg_id)
            if not status:
                await logger(
                    e=f"@relay_delete: Failed to deleted message from database, msg;\n{msg}",
                    error=True,
                )
    except Exception:
        await logger(Exception)


def add_forward_handlers():
    client = bot.tg_client2 or bot.tg_client
    client.add_event_handler(
        forward_audios, events.NewMessage(func=lambda e: e.audio and not e.video_note)
    )
    client.add_event_handler(forward_audios, events.NewMessage(func=lambda e: e.voice))
    client.add_event_handler(
        forward_docs,
        events.NewMessage(
            func=lambda e: e.document
            and not (
                e.audio
                or e.voice
                or e.gif
                or e.sticker
                or e.photo
                or e.video
                or e.video_note
            )
        ),
    )
    client.add_event_handler(forward_gifs, events.NewMessage(func=lambda e: e.gif))
    client.add_event_handler(forward_images, events.NewMessage(func=lambda e: e.photo))
    client.add_event_handler(
        forward_stickers, events.NewMessage(func=lambda e: e.sticker)
    )
    client.add_event_handler(
        forward_texts,
        events.NewMessage(func=lambda e: e.message.message and not e.media),
    )
    client.add_event_handler(
        forward_vids,
        events.NewMessage(
            func=lambda e: e.video and not (e.gif or e.video_note or e.sticker)
        ),
    )
    client.add_event_handler(
        forward_vids, events.NewMessage(func=lambda e: e.video_note)
    )
    client.add_event_handler(handle_edits, events.MessageEdited())
    client.add_event_handler(handle_deletes, events.MessageDeleted())
