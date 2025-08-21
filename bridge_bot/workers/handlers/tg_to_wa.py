from datetime import datetime as dt

from neonize.utils.ffmpeg import AFFmpeg
from telethon import events
from telethon.tl.types import (
    MessageMediaWebPage,
    ReactionEmoji,
    UpdateBotMessageReaction,
)

from bridge_bot import bot, conf, heavy_proc_lock, jid
from bridge_bot.utils.bot_utils import get_sticker_pack, read_binary
from bridge_bot.utils.log_utils import logger
from bridge_bot.utils.media_utils import (
    all_vid_streams_avc,
    convert_to_avc,
    convert_to_wa_sticker,
    is_mp3_audio,
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
    get_bridge_header_wa,
    get_bridge_rheader_wa,
    get_tg_edit_data,
    is_echo,
    load_proto,
    replace_mentions_for_wa,
)
from bridge_bot.utils.os_utils import s_remove, size_of
from bridge_bot.utils.tg_transfer import download_file

# To Do: check if file size is properly within constraints


async def text_to_wa(event):
    """Forwards text messages to WA"""
    try:
        chat_id = event.chat_id
        if not (
            bridge_info := bot.group_dict.setdefault("tg_bridges", {}).get(chat_id)
        ):
            return
        msg = None
        text = conv_tgmd_to_wamd(event.raw_text, event.entities)
        wa_chat_id = bridge_info.get("wa_chat")
        wa_jid = jid.build_jid(wa_chat_id, "g.us")
        text = get_bridge_header_wa(event) + replace_mentions_for_wa(text)
        if event.reply_to:
            msg = await get_message(wa_chat_id, chat_id, event.reply_to.reply_to_msg_id)
        if msg:
            Msg = load_proto(msg.raw)
            user_jid = load_proto(msg.raw_user, True)
            wa_msg = construct_message(
                wa_chat_id, user_jid.User, msg.wa_id, None, "g.us", user_jid.Server, Msg
            )
            rep = await bot.client.reply_message(
                text, wa_msg, to=wa_jid, mentions_are_lids=True
            )
        else:
            rep = await bot.client.send_message(wa_jid, text, mentions_are_lids=True)
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


async def img_to_wa(event):
    """Forwards images to WA"""
    try:
        chat_id = event.chat_id
        if not (
            bridge_info := bot.group_dict.setdefault("tg_bridges", {}).get(chat_id)
        ):
            return
        msg = wa_msg = None
        spoiler = False
        if hasattr(event.media, "spoiler"):
            spoiler = event.media.spoiler
        image = await event.download_media(file=bytes)
        text = conv_tgmd_to_wamd(event.raw_text, event.entities)
        wa_chat_id = bridge_info.get("wa_chat")
        wa_jid = jid.build_jid(wa_chat_id, "g.us")
        text = get_bridge_header_wa(event) + replace_mentions_for_wa(text)
        if event.reply_to:
            msg = await get_message(wa_chat_id, chat_id, event.reply_to.reply_to_msg_id)
        if msg:
            Msg = load_proto(msg.raw)
            user_jid = load_proto(msg.raw_user, True)
            wa_msg = construct_message(
                wa_chat_id, user_jid.User, msg.wa_id, None, "g.us", user_jid.Server, Msg
            )
        rep = await bot.client.send_image(
            wa_jid, image, text, quoted=wa_msg, spoiler=spoiler, mentions_are_lids=True
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


async def vid_cleanup(event, org, proc, org_name, skip_upload=True):
    file_name = org_name or "video_" + dt.now().isoformat("_", "seconds") + ".mkv"
    (
        await event.reply_document(org, file_name, "*Original Video*")
        if not skip_upload
        else None
    )
    s_remove(org, proc)


async def gif_to_wa(event):
    """Forwards gif messages to WA"""
    try:
        chat_id = event.chat_id
        if not (
            bridge_info := bot.group_dict.setdefault("tg_bridges", {}).get(chat_id)
        ):
            return
        msg = wa_msg = None
        spoiler = False
        if hasattr(event.media, "spoiler"):
            spoiler = event.media.spoiler
        text = conv_tgmd_to_wamd(event.raw_text, event.entities)
        wa_chat_id = bridge_info.get("wa_chat")
        wa_jid = jid.build_jid(wa_chat_id, "g.us")
        up_as_doc = False
        gif = await event.download_media(file=bytes)

        if len(gif) > 100000000:
            up_as_doc = True
        text = get_bridge_header_wa(event) + replace_mentions_for_wa(text)
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
                spoiler=spoiler,
                mentions_are_lids=True,
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
    except Exception:
        await logger(Exception)


async def vid_to_wa(event):
    """Forwards video messages to WA"""
    try:
        chat_id = event.chat_id
        if not (
            bridge_info := bot.group_dict.setdefault("tg_bridges", {}).get(chat_id)
        ):
            return
        msg = wa_msg = None
        spoiler = False
        if hasattr(event.media, "spoiler"):
            spoiler = event.media.spoiler
        text = conv_tgmd_to_wamd(event.raw_text, event.entities)
        wa_chat_id = bridge_info.get("wa_chat")
        wa_jid = jid.build_jid(wa_chat_id, "g.us")
        _id = f"{event.chat.id}:{event.id}"
        in_ = f"temp/{_id}.mp4"
        out_ = f"temp/{_id}-1.mp4"
        up_as_doc = False
        await download_file(event.client, event.video, in_, event)
        if not await all_vid_streams_avc(in_):
            async with heavy_proc_lock:
                rep = await bot.client.send_message(
                    wa_jid, "Processing a video from tg"
                )
                await convert_to_avc(in_, out_)
                s_remove(in_)
                await bot.client.revoke_message(wa_jid, bot.client.me.JID, rep.ID)

        else:
            out_ = in_
        vid = await read_binary(out_)
        s_remove(out_)
        if len(vid) > 100000000:
            up_as_doc = True
        text = get_bridge_header_wa(event) + replace_mentions_for_wa(text)
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
                spoiler=spoiler,
                mentions_are_lids=True,
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
    except Exception:
        await logger(Exception)


async def audio_to_wa(event):
    """Forwards audio messages to WA"""
    try:
        chat_id = event.chat_id
        if not (
            bridge_info := bot.group_dict.setdefault("tg_bridges", {}).get(chat_id)
        ):
            return
        audio = await download_file(event.client, event.document, bytes, event)
        async with AFFmpeg(audio) as ffmpeg:
            if not await is_mp3_audio(ffmpeg.filepath):
                audio = await ffmpeg.to_mp3()
        msg = wa_msg = None
        text = conv_tgmd_to_wamd(event.raw_text, event.entities)
        wa_chat_id = bridge_info.get("wa_chat")
        wa_jid = jid.build_jid(wa_chat_id, "g.us")
        text = get_bridge_header_wa(event) + replace_mentions_for_wa(text)
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
        await bot.client.reply_message(text, wa_msg_, to=wa_jid, mentions_are_lids=True)
    except Exception:
        await logger(Exception)


async def doc_to_wa(event):
    """Forwards document messages to WA"""
    try:
        chat_id = event.chat_id
        if not (
            bridge_info := bot.group_dict.setdefault("tg_bridges", {}).get(chat_id)
        ):
            return
        doc = await download_file(event.client, event.document, bytes, event)
        msg = wa_msg = None
        text = conv_tgmd_to_wamd(event.raw_text, event.entities)
        wa_chat_id = bridge_info.get("wa_chat")
        wa_jid = jid.build_jid(wa_chat_id, "g.us")
        text = get_bridge_header_wa(event) + replace_mentions_for_wa(text)
        if event.reply_to:
            msg = await get_message(wa_chat_id, chat_id, event.reply_to.reply_to_msg_id)
        if msg:
            Msg = load_proto(msg.raw)
            user_jid = load_proto(msg.raw_user, True)
            wa_msg = construct_message(
                wa_chat_id, user_jid.User, msg.wa_id, None, "g.us", user_jid.Server, Msg
            )
        rep = await bot.client.send_document(
            wa_jid, doc, text, event.file.name, quoted=wa_msg, mentions_are_lids=True
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


async def sticker_to_wa(event):
    """Forwards sticker messages to WA"""
    try:
        chat_id = event.chat_id
        if not (
            bridge_info := bot.group_dict.setdefault("tg_bridges", {}).get(chat_id)
        ):
            return
        _id = f"{event.chat.id}:{event.id}"
        # in_ = f"temp/{_id}_{event.file.name}"
        sticker = await event.download_media(file=bytes)
        msg = wa_msg = None
        text = ""
        wa_chat_id = bridge_info.get("wa_chat")
        wa_jid = jid.build_jid(wa_chat_id, "g.us")
        try:
            stickerset = await get_sticker_pack(event)
        except Exception as e:
            await logger(e=e, warning=True)
            stickerset = None

        packname = stickerset.set.title if stickerset else "None"
        sticker = await convert_to_wa_sticker(sticker, event.file.name, packname)
        # + replace_mentions_for_wa(text)
        text = get_bridge_header_wa(event)
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
        await bot.client.reply_message(text, wa_msg_, to=wa_jid, mentions_are_lids=True)
    except Exception:
        await logger(Exception)


async def delete_for_wa(event):
    "Deletes bridged messages when deleted on telegram."
    try:
        chat_id = event.chat_id
        if not (
            bridge_info := bot.group_dict.setdefault("tg_bridges", {}).get(chat_id)
        ):
            return
        wa_chat_id = bridge_info.get("wa_chat")
        for msg_id in event.deleted_ids:
            msg = await get_message(wa_chat_id, chat_id, msg_id)
            if not msg:
                continue
            user_jid = load_proto(msg.raw_user, True)
            try:
                await bot.client.revoke_message(
                    jid.build_jid(wa_chat_id, "g.us"), user_jid, msg.wa_id
                )
            except Exception:
                await logger(Exception)
            status = await delete_message(wa_chat_id, chat_id, msg_id)
            if not status:
                await logger(
                    e=f"@delete_for_wa: Failed to deleted message from database, msg;\n{msg}",
                    error=True,
                )
            # clean reaction messages in database (on both end)
            await delete_message(wa_chat_id, chat_id, msg_id, is_reaction=True)
            await delete_message(wa_chat_id, chat_id, wa_id=msg.wa_id, is_reaction=True)
    except Exception:
        await logger(Exception)


async def edit_for_wa(event):
    "Edits bridged messages when exited on telegram."
    try:
        chat_id = event.chat_id
        if not (
            bridge_info := bot.group_dict.setdefault("tg_bridges", {}).get(chat_id)
        ):
            return
        wa_chat_id = bridge_info.get("wa_chat")
        msg_id = event.id
        msg = await get_message(wa_chat_id, chat_id, msg_id)
        if not msg:
            return
        text = conv_tgmd_to_wamd(event.raw_text, event.entities)
        text = get_bridge_header_wa(event) + replace_mentions_for_wa(text)
        update_data, edit_msg = get_tg_edit_data(text, msg.raw)
        if not update_data:
            await logger(
                e=f"@edit_for_wa: msg does not support editing on Whatsapp's end, msg;\n{msg}",
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
                e=f"@tg_to_wa: Failed to edit message in database, msg;\n{msg}",
                error=True,
            )
    except Exception:
        await logger(Exception)


async def handle_reaction_update(event):
    """Handles Telegram reaction updates and bridges them to WhatsApp as a live message"""
    if not hasattr(event.peer, "channel_id"):
        return
    chat_id = int(f"-100{event.peer.channel_id}")
    if not (bridge_info := bot.group_dict.setdefault("tg_bridges", {}).get(chat_id)):
        return

    reaction_emoji = None

    try:
        if event.new_reactions:
            reaction = event.new_reactions[0]
            if isinstance(reaction, ReactionEmoji):
                reaction_emoji = reaction.emoticon
        reaction_text = await get_bridge_rheader_wa(event, bot.tg_client) + (
            f"Reacted {reaction_emoji} to:"
            if reaction_emoji
            else "Removed their reaction"
        )
        msg_id = event.msg_id
        wa_chat_id = bridge_info["wa_chat"]
        msg_ = await get_message(wa_chat_id, chat_id, tg_id=msg_id)
        if not msg_:
            await logger(
                e=f"Original Telegram message with id: {msg_id} not found for reaction in chat: {chat_id}",
                warning=True,
            )
            return
        msg = await get_message(wa_chat_id, chat_id, tg_id=msg_id, is_reaction=True)

        if msg:
            update_data, edit_msg = get_tg_edit_data(reaction_text, msg.raw)
            try:
                await bot.client.edit_message(
                    jid.build_jid(wa_chat_id, "g.us"), msg.wa_id, edit_msg
                )
            except Exception as edit_err:
                await logger(f"WA edit failed: {edit_err}", error=True)
            status = await edit_message(
                wa_chat_id,
                chat_id,
                update_data,
                tg_id=msg_id,
                is_reaction=True,
            )
            if not status:
                await logger(
                    e=f"@handle_reaction_update: Failed to edit reaction in database, msg:\n"
                    f"{msg}",
                    error=True,
                )
        else:
            Msg = load_proto(msg_.raw)
            user_jid = load_proto(msg_.raw_user, True)
            wa_msg = construct_message(
                wa_chat_id,
                user_jid.User,
                msg_.wa_id,
                None,
                "g.us",
                user_jid.Server,
                Msg,
            )
            rep = await bot.client.reply_message(
                reaction_text,
                wa_msg,
                to=jid.build_jid(wa_chat_id, "g.us"),
                mentions_are_lids=True,
            )
            await save_message(
                wa_chat_id,
                chat_id,
                None,
                msg=rep.Message,
                tg_id=msg_id,
                wa_id=rep.ID,
                is_reaction=True,
                timestamp=rep.Timestamp,
            )
    except Exception:
        await logger(Exception)


def add_tg_bridge_handlers():
    client = (
        bot.tg_client2 if (bot.tg_client2 and conf.UB_REC_EVENTS) else bot.tg_client
    )

    active_tg_bridges = bot.group_dict.setdefault("tg_bridges", {}).keys()

    def not_echo(event):
        return not is_echo(event.sender_id)

    def chat(event):
        return event.chat_id in active_tg_bridges

    handlers = [
        (audio_to_wa, [lambda e: e.audio and not e.video_note, lambda e: e.voice]),
        (
            doc_to_wa,
            [
                lambda e: (
                    e.document
                    and not (
                        e.audio
                        or e.voice
                        or e.gif
                        or e.sticker
                        or e.photo
                        or e.video
                        or e.video_note
                    )
                )
            ],
        ),
        (gif_to_wa, [lambda e: e.gif]),
        (img_to_wa, [lambda e: e.photo]),
        (sticker_to_wa, [lambda e: e.sticker]),
        (
            text_to_wa,
            [
                lambda e: e.text
                and (
                    not e.media
                    or (e.media and isinstance(e.media, MessageMediaWebPage))
                )
            ],
        ),
        (
            vid_to_wa,
            [
                lambda e: e.video and not (e.gif or e.video_note or e.sticker),
                lambda e: e.video_note,
            ],
        ),
    ]

    # Register all handlers
    for handler, filters in handlers:
        for event_filter in filters:

            def full_filter(e, f=event_filter):
                return chat(e) and not_echo(e) and f(e)

            client.add_event_handler(handler, events.NewMessage(func=full_filter))

    client.add_event_handler(
        delete_for_wa, events.MessageDeleted(func=lambda e: chat(e))
    )
    client.add_event_handler(
        edit_for_wa, events.MessageEdited(func=lambda e: chat(e) and not_echo(e))
    )
    bot.tg_client.add_event_handler(
        handle_reaction_update, events.Raw(UpdateBotMessageReaction)
    )
