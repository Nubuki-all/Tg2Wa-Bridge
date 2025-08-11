import asyncio
import itertools
import time
import uuid
from collections import deque

from asyncprawcore.exceptions import Redirect

from bridge_bot import bot, conf
from bridge_bot.utils.bot_utils import (
    DummyListener,
    compare_inner_dict_value,
    get_date_from_ts,
    human_format_num,
    remove_inactive_wasubs,
)
from bridge_bot.utils.db_utils import save2db2
from bridge_bot.utils.log_utils import logger
from bridge_bot.utils.msg_store import deinitialize_session, initialize_session
from bridge_bot.utils.msg_utils import get_args, user_is_owner
from bridge_bot.utils.os_utils import re_x, updater
from bridge_bot.utils.sudo_button_utils import (
    create_sudo_button,
    wait_for_button_response,
)


async def restart_handler(event, args, client):
    """Restarts bot. (To avoid issues use /update instead.)"""
    if not user_is_owner(event.from_user.id):
        return
    try:
        rst = await event.reply("*Restarting Please Wait…*")
        message = f"{rst.chat.id}:{rst.id}:{rst.chat.server}"
        re_x("restart", message)
    except Exception:
        await event.reply("An Error Occurred")
        await logger(Exception)


async def update_handler(event, args, client):
    """Fetches latest update for bot"""
    try:
        if not user_is_owner(event.from_user.id):
            return
        upt_mess = "Updating…"
        reply = await event.reply(f"*{upt_mess}*")
        updater(reply)
    except Exception:
        await logger(Exception)


async def bridge(event, args, client):
    """Bridges the current WA chat with the specified telegram chat!"""
    try:
        if not event.chat.is_group:
            return
        user_id = event.from_user.id
        if not user_is_owner(user_id):
            return
        if not args.startswith("-100"):
            return await event.reply(
                f"*'{args}' is not a valid telegram group/channel id*"
            )
        if not args.lstrip("-").isdigit():
            return await event.reply(f"*'{args}' is not a valid telegram chat_id*")
        args = int(args)
        if args in bot.group_dict.setdefault("subscribed_channels", {}):
            return await event.reply(f"Specified chat has already been subscribed")
        tg_bridges = bot.group_dict.setdefault("tg_bridges", {})
        if tg_bridges.get(args):
            return await event.reply(f"Specified chat has already been bridged")
        wa_chat_id = event.chat.id
        if bot.tg_client2 and conf.UB_REC_EVENTS:
            client = bot.tg_client2
        else:
            client = bot.tg_client
        chat = await client.get_entity(args)
        y = "Yes"
        n = "No"
        button_dict = {
            uuid.uuid4(): [y, y],
            uuid.uuid4(): [n, n],
        }
        chat_name = (await bot.client.get_group_info(event.chat.jid)).GroupName.Name
        text = f"Bridge {chat_name} with {chat.title}?"
        poll_msg = await create_sudo_button(
            text, button_dict, event.chat.jid, user_id, 1, None, event.message
        )
        dl_poll_msg = bot.client.revoke_message(
            event.chat.jid, bot.client.me.JID, poll_msg.ID
        )
        if not (results := await wait_for_button_response(poll_msg.ID)):
            await dl_poll_msg
            return await event.reply("Yh, I'm done waiting.")
        await dl_poll_msg
        info = button_dict.get(results[0])
        if not info[0] == y:
            return await event.reply("*Operation Cancelled!*")
        tg_bridges.update({args: {"tg_chat": args, "wa_chat": wa_chat_id}})
        active_wa_bridges = bot.group_dict.setdefault("active_wa_bridges", [])
        (
            active_wa_bridges.append(wa_chat_id)
            if wa_chat_id not in active_wa_bridges
            else None
        )
        await save2db2(bot.group_dict, "groups")
        await initialize_session(wa_chat_id)
        await event.reply(
            f"*Bridged @{wa_chat_id}@g.us with {chat.title} successfully!*"
        )
    except Exception as e:
        await logger(Exception)
        await event.reply(f"*Error:* {e}")


async def unbridge(event, args, client):
    """Unbridges the current WA chat from the specified telegram chat!"""
    try:
        if not event.chat.is_group:
            return
        user_id = event.from_user.id
        if not user_is_owner(user_id):
            return
        wa_chat_id = event.chat.id
        if wa_chat_id not in (
            active_wa_bridges := bot.group_dict.setdefault("active_wa_bridges", [])
        ):
            return await event.reply("No active bridges in this chat!")
        if not args.startswith("-100"):
            return await event.reply(
                f"*'{args}' is not a valid telegram group/channel id*"
            )
        if not args.lstrip("-").isdigit():
            return await event.reply(f"*'{args}' is not a valid telegram chat_id*")
        args = int(args)
        if not (tg_bridges := bot.group_dict.setdefault("tg_bridges", {})).get(args):
            return await event.reply(f"Specified chat was not bridged!*")
        if bot.tg_client2 and conf.UB_REC_EVENTS:
            client = bot.tg_client2
        else:
            client = bot.tg_client
        chat = await client.get_entity(args)
        y = "Yes"
        n = "No"
        button_dict = {
            uuid.uuid4(): [y, y],
            uuid.uuid4(): [n, n],
        }
        chat_name = (await bot.client.get_group_info(event.chat.jid)).GroupName.Name
        text = f"Unbridge {chat_name} from {chat.title}?"
        poll_msg = await create_sudo_button(
            text, button_dict, event.chat.jid, user_id, 1, None, event.message
        )
        dl_poll_msg = bot.client.revoke_message(
            event.chat.jid, bot.client.me.JID, poll_msg.ID
        )
        if not (results := await wait_for_button_response(poll_msg.ID)):
            await dl_poll_msg
            return await event.reply("Yh, I'm done waiting.")
        await dl_poll_msg
        info = button_dict.get(results[0])
        if not info[0] == y:
            return await event.reply("*Operation Cancelled!*")
        tg_bridges.pop(args)
        if not compare_inner_dict_value(tg_bridges, "wa_chat", wa_chat_id):
            active_wa_bridges.remove(wa_chat_id)
            await deinitialize_session(wa_chat_id)
        await save2db2(bot.group_dict, "groups")
        await event.reply(
            f"*Unbridged @{wa_chat_id}@g.us from {chat.title} successfully!*"
        )
    except Exception as e:
        await logger(Exception)
        await event.reply(f"*Error:* {e}")


async def subscribe(event, args, client):
    """
    Subscribe to the specified telegram chat
    Argument:
        CHAT_ID : Telegram chat id to subscribe to.
    """
    try:
        user_id = event.from_user.id
        if not user_is_owner(user_id):
            return
        if not args.lstrip("-").isdigit():
            return await event.reply(f"*'{args}' is not a valid telegram chat_id*")
        if not args.startswith("-100"):
            return await event.reply(
                f"*'{args}' is not a valid telegram group/channel id*"
            )
        args = int(args)
        if args in bot.group_dict.setdefault("tg_bridges", {}):
            return await event.reply(f"Specified chat has already been bridged")
        subscribed = bot.group_dict.setdefault("subscribed_channels", {})
        if subscribed.get(args):
            return await event.reply(
                f"Specified chat has already been subscribed, edit the subscription instead"
            )
        chat = await (bot.tg_client2 or bot.tg_client).get_entity(args)
        y = "Yes"
        n = "No"
        button_dict = {
            uuid.uuid4(): [y, y],
            uuid.uuid4(): [n, n],
        }
        text = f"Subscribe to {chat.title}?"
        poll_msg = await create_sudo_button(
            text, button_dict, event.chat.jid, user_id, 1, None, event.message
        )
        dl_poll_msg = bot.client.revoke_message(
            event.chat.jid, bot.client.me.JID, poll_msg.ID
        )
        if not (results := await wait_for_button_response(poll_msg.ID)):
            await dl_poll_msg
            return await event.reply("Yh, I'm done waiting.")
        await dl_poll_msg
        info = button_dict.get(results[0])
        if not info[0] == y:
            return await event.reply("*Operation Cancelled!*")
        subscribed.update({args: {"chats": [], "name": chat.title}})
        await save2db2(bot.group_dict, "groups")
        await event.reply(f"*Subscribed to {chat.title} successfully!*")
    except Exception as e:
        await logger(Exception)
        await event.reply(f"*Error:* {e}")


async def unsubscribe(event, args, client):
    """
    Fully unsubscribes the specified telegram chat!
    Argument:
        CHAT_ID : Telegram chat id to unsubscribe.
    """
    try:
        user_id = event.from_user.id
        if not user_is_owner(user_id):
            return
        wa_chat_id = event.chat.id
        if not args.lstrip("-").isdigit():
            return await event.reply(f"*'{args}' is not a valid telegram chat_id*")
        if not args.startswith("-100"):
            return await event.reply(
                f"*'{args}' is not a valid telegram group/channel id*"
            )
        args = int(args)
        if not (subscribed := bot.group_dict.setdefault("subscribed_channels", {})).get(
            args
        ):
            return await event.reply(f"*Specified subscription does not exist!*")
        chat = await (bot.tg_client2 or bot.tg_client).get_entity(args)
        y = "Yes"
        n = "No"
        button_dict = {
            uuid.uuid4(): [y, y],
            uuid.uuid4(): [n, n],
        }
        text = f"Fully unsubscribe {chat.title}?\n"
        poll_msg = await create_sudo_button(
            text, button_dict, event.chat.jid, user_id, 1, None, event.message
        )
        dl_poll_msg = bot.client.revoke_message(
            event.chat.jid, bot.client.me.JID, poll_msg.ID
        )
        if not (results := await wait_for_button_response(poll_msg.ID)):
            await dl_poll_msg
            return await event.reply("Yh, I'm done waiting.")
        await dl_poll_msg
        info = button_dict.get(results[0])
        if not info[0] == y:
            return await event.reply("*Operation Cancelled!*")
        subscribed.pop(args)
        removed_ids = remove_inactive_wasubs()
        for gc_id in removed_ids:
            await deinitialize_session(wa_chat_id)
        await save2db2(bot.group_dict, "groups")
        await event.reply(f"*Unsubscribed from {chat.title} successfully!*")
    except Exception as e:
        await logger(Exception)
        await event.reply(f"*Error:* {e}")


async def add_subscriber(event, args, client):
    """
    Add a chat to a subscribed telegram chat
    Argument:
        CHAT_ID: Telegram chat_id (Previously subscribed telegram chat)
        -id WA_CHAT_ID: Whatsapp chat_id or . for current chat
    """
    try:
        user_id = event.from_user.id
        if not user_is_owner(user_id):
            return
        arg, args = get_args(
            "-id",
            to_parse=args,
            get_unknown=True,
        )
        if not args.lstrip("-").isdigit():
            return await event.reply(f"*'{args}' is not a valid telegram chat_id*")
        if not args.startswith("-100"):
            return await event.reply(
                f"*'{args}' is not a valid telegram group/channel id*"
            )
        if not arg.id:
            return await event.reply(
                "Please supply a Whatsapp group id with the -id flag"
            )
        args = int(args)
        if not (
            subscribed_info := bot.group_dict.setdefault("subscribed_channels", {}).get(
                args
            )
        ):
            return await event.reply(f"*Specified subscription does not exist!*")
        wa_chat_id = arg.id if arg.id != "." else event.chat.id
        if wa_chat_id in (chats := subscribed_info.get("chats")):
            return await event.reply("Chat has already been Added.")
        chats.append(wa_chat_id)
        active_wa_subs = bot.group_dict.setdefault("active_wa_subs", [])
        if wa_chat_id not in active_wa_subs:
            active_wa_subs.append(wa_chat_id)
            await initialize_session(wa_chat_id)
        await save2db2(bot.group_dict, "groups")
        await event.reply(
            f"*Successfully added @{wa_chat_id}@g.us to subscription: {subscribed_info.get('name')}!*"
        )
    except Exception:
        await logger(Exception)


async def remove_subscriber(event, args, client):
    """
    Removes a chat from a subscribed telegram chat
    Argument:
        CHAT_ID: Telegram chat_id (Previously subscribed telegram chat)
        -id WA_CHAT_ID: Whatsapp chat_id or . for current chat
    """
    try:
        user_id = event.from_user.id
        if not user_is_owner(user_id):
            return
        arg, args = get_args(
            "-id",
            to_parse=args,
            get_unknown=True,
        )
        if not args.lstrip("-").isdigit():
            return await event.reply(f"*'{args}' is not a valid telegram chat_id*")
        if not args.startswith("-100"):
            return await event.reply(
                f"*'{args}' is not a valid telegram group/channel id*"
            )
        if not arg.id:
            return await event.reply(
                "Please supply a Whatsapp group id with the -id flag"
            )
        args = int(args)
        if not (
            subscribed_info := bot.group_dict.setdefault("subscribed_channels", {}).get(
                args
            )
        ):
            return await event.reply(f"*Specified subscription does not exist!*")
        wa_chat_id = arg.id if arg.id != "." else event.chat.id
        if wa_chat_id not in (chats := subscribed_info.get("chats")):
            return await event.reply("Chat has already been removed or wasn't added.")
        chats.remove(wa_chat_id)
        removed_ids = remove_inactive_wasubs()
        for gc_id in removed_ids:
            await deinitialize_session(wa_chat_id)
        await save2db2(bot.group_dict, "groups")
        await event.reply(
            f"*Successfully removed @{wa_chat_id}@g.us from subscription: {subscribed_info.get('name')}!*"
        )
    except Exception:
        await logger(Exception)


def get_list_of_added_chats(s_info: dict) -> str:
    msg = ""
    for i, x in zip(itertools.count(1), s_info.get("chats")):
        msg += f"{i}. {x}"
    if msg:
        msg = "*List of added chats:*\n" + msg
    return msg


async def edit_subscription(event, args, client):
    """
    Edit a telegram subscription
    Arguments:
        CHAT_ID: Telegram chat_id (Previously subscribed telegram chat)
    """
    try:
        user_id = event.from_user.id
        if not user_is_owner(user_id):
            return
        if not args.lstrip("-").isdigit():
            return await event.reply(f"*'{args}' is not a valid telegram chat_id*")
        if not args.startswith("-100"):
            return await event.reply(
                f"*'{args}' is not a valid telegram group/channel id*"
            )
        args = int(args)
        if not (
            subscribed_info := bot.group_dict.setdefault("subscribed_channels", {}).get(
                args
            )
        ):
            return await event.reply(f"*Specified subscription does not exist!*")
        chat = await (bot.tg_client2 or bot.tg_client).get_entity(args)
        f = "Add a chat"
        s = "Remove a chat"
        t = "Cancel"
        button_dict = {
            uuid.uuid4(): [f, add_subscriber],
            uuid.uuid4(): [s, remove_subscriber],
            uuid.uuid4(): [t, t],
        }
        text = f"Choose an action for subscription: {chat.title}"
        poll_msg = await create_sudo_button(
            text, button_dict, event.chat.jid, user_id, 1, None, event.message
        )
        dl_poll_msg = bot.client.revoke_message(
            event.chat.jid, bot.client.me.JID, poll_msg.ID
        )
        if not (results := await wait_for_button_response(poll_msg.ID)):
            await dl_poll_msg
            return await event.reply("Yh, I'm done waiting.")
        await dl_poll_msg
        info = button_dict.get(results[0])
        if info[0] == t:
            return await event.reply("*Operation Cancelled!*")
        if info[0] == s:
            text = get_list_of_added_chats(subscribed_info)
            await event.reply(text) if text else None
        text = "*Reply this message with the WhatsApp group id of chat to add/remove*\n_Also accepts '.' to specify current chat_"
        rep = await event.reply(text)
        listener = DummyListener()

        async def get_reply(event, _, __):
            if not ((replied := event.reply_to_message) and replied.id == rep.id):
                return
            if event.from_user.id != user_id:
                return
            if event.is_actual_media:
                return await event.reply("why?")
            if not (text := event.text):
                return
            listener.response = text

        key = bot.add_handler(get_reply)
        s_time = time.time()
        while (time.time() - s_time) < 60:
            if listener.response:
                bot.unregister(key)
                await rep.delete()
                break
            await asyncio.sleep(1)
        else:
            bot.unregister(key)
            await rep.delete()
            return await rep.reply("Operation Time out")
        await info[1](event, f"{args} -id {listener.response}", client)
    except Exception:
        await logger(Exception)


async def list_subscriptions(event, args, client):
    "Lists all subscriptions"
    try:
        user_id = event.from_user.id
        if not user_is_owner(user_id):
            return
        msg = ""
        subscribed = bot.group_dict.setdefault("subscribed_channels", {})
        for i, chat_id in zip(itertools.count(1), subscribed):
            msg += f"{i}. {chat_id}; {subscribed[chat_id].get('name')}"
            msg += "\n"
        if not msg:
            return await event.reply("No subscriptions!")
        msg = "*List of subscribed channels:*\n" + msg
        await event.reply(msg)
    except Exception:
        await logger(Exception)


inactive_reddit_client_err = (
    "Error: Reddit client has not been initialized, "
    "set the required envs then restart!"
)


async def subscribe_subreddit(event, args, client):
    """
    Subscribe to the specified telegram chat
    Argument:
        Subreddit : Reddit subreddit to subscribe to.
    """
    try:
        user_id = event.from_user.id
        if not user_is_owner(user_id):
            return
        if not bot.reddit:
            return await event.reply(inactive_reddit_client_err)
        args = args.lower()
        subscribed = bot.group_dict.setdefault("subscribed_subreddits", {})
        if subscribed.get(args):
            return await event.reply(
                f"Specified subreddit has already been subscribed to, edit the subscription instead"
            )
        try:
            sub = await bot.reddit.subreddit(args, fetch=True)
        except Redirect:
            return await event.reply("Specified subreddit does not exist!")
        sub_name = sub.display_name
        sub_img = ""
        if hasattr(sub, "community_icon"):
            sub_img = sub.community_icon
        if not sub_img:
            sub_img = sub.icon_img
        try:
            info_text = (
                f"*{sub.display_name_prefixed}*"
                f"\n\n *Created on:* {get_date_from_ts(sub.created_utc)}"
                f"\n*NSFW:* {sub.over18}"
                f"\n*Subscribers:* {human_format_num(sub.subscribers)}"
                "\n\n*Description:*\n"
                f"> {sub.public_description}"
                f"\n\n*Url:* https://www.reddit.com{sub.url}"
            )
        except Exception as e:
            info_text = ""
            await logger(e=e, warning=True)
        y = "Yes"
        n = "No"
        button_dict = {
            uuid.uuid4(): [y, y],
            uuid.uuid4(): [n, n],
        }
        text = f"Subscribe to {'the above' if info_text else sub_name}?"
        if info_text:
            rep = (
                await event.reply_photo(sub_img, info_text)
                if sub_img
                else await event.reply(info_text)
            )
        else:
            rep = event
        poll_msg = await create_sudo_button(
            text, button_dict, rep.chat.jid, user_id, 1, None, rep.message
        )
        dl_poll_msg = bot.client.revoke_message(
            rep.chat.jid, bot.client.me.JID, poll_msg.ID
        )
        if not (results := await wait_for_button_response(poll_msg.ID)):
            await dl_poll_msg
            return await event.reply("Yh, I'm done waiting.")
        await dl_poll_msg
        info = button_dict.get(results[0])
        if not info[0] == y:
            return await event.reply("*Operation Cancelled!*")
        last_ids = deque(maxlen=50)
        async for submission in sub.new(limit=5):
            last_ids.append(submission.id)
        subscribed.update({args: {"chats": [], "name": sub_name, "last_ids": last_ids}})
        await save2db2(bot.group_dict, "groups")
        await event.reply(f"*Subscribed to {sub_name} successfully!*")
    except Exception as e:
        await logger(Exception)
        await event.reply(f"*Error:* {e}")


async def unsubscribe_subreddit(event, args, client):
    """
    Fully unsubscribes the specified subreddit!
    Argument:
        Subreddit : Subreddit to unsubscribe.
    """
    try:
        user_id = event.from_user.id
        if not user_is_owner(user_id):
            return
        args = args.lower()
        if not (
            subscribed := bot.group_dict.setdefault("subscribed_subreddits", {})
        ).get(args):
            return await event.reply(f"*Specified subscription does not exist!*")
        sub_name = subscribed[args]["name"]
        y = "Yes"
        n = "No"
        button_dict = {
            uuid.uuid4(): [y, y],
            uuid.uuid4(): [n, n],
        }
        text = f"Fully unsubscribe {sub_name}?\n"
        poll_msg = await create_sudo_button(
            text, button_dict, event.chat.jid, user_id, 1, None, event.message
        )
        dl_poll_msg = bot.client.revoke_message(
            event.chat.jid, bot.client.me.JID, poll_msg.ID
        )
        if not (results := await wait_for_button_response(poll_msg.ID)):
            await dl_poll_msg
            return await event.reply("Yh, I'm done waiting.")
        await dl_poll_msg
        info = button_dict.get(results[0])
        if not info[0] == y:
            return await event.reply("*Operation Cancelled!*")
        subscribed.pop(args)
        await save2db2(bot.group_dict, "groups")
        await event.reply(f"*Unsubscribed from {sub_name} successfully!*")
    except Exception as e:
        await logger(Exception)
        await event.reply(f"*Error:* {e}")


async def add_subreddit_subscriber(event, args, client):
    """
    Add a chat to a subscribed telegram chat
    Argument:
        Subreddit : Reddit subreddit (Previously subscribed subreddit)
        -id WA_CHAT_ID: Whatsapp chat_id or . for current chat
    """
    try:
        user_id = event.from_user.id
        if not user_is_owner(user_id):
            return
        arg, args = get_args(
            "-id",
            to_parse=args,
            get_unknown=True,
        )
        if not arg.id:
            return await event.reply(
                "Please supply a Whatsapp group id with the -id flag"
            )
        args = args.lower()
        if not (
            subscribed_info := bot.group_dict.setdefault(
                "subscribed_subreddits", {}
            ).get(args)
        ):
            return await event.reply(f"*Specified subscription does not exist!*")
        wa_chat_id = arg.id if arg.id != "." else event.chat.id
        if wa_chat_id in (chats := subscribed_info.get("chats")):
            return await event.reply("Chat has already been Added.")
        chats.append(wa_chat_id)
        await save2db2(bot.group_dict, "groups")
        await event.reply(
            f"*Successfully added @{wa_chat_id}@g.us to subscription: {subscribed_info.get('name')}!*"
        )
    except Exception:
        await logger(Exception)


async def remove_subreddit_subscriber(event, args, client):
    """
    Removes a chat from a subscribed telegram chat
    Argument:
        Subreddit : Reddit subreddit (Previously subscribed subreddit)
        -id WA_CHAT_ID: Whatsapp chat_id or . for current chat
    """
    try:
        user_id = event.from_user.id
        if not user_is_owner(user_id):
            return
        arg, args = get_args(
            "-id",
            to_parse=args,
            get_unknown=True,
        )
        if not arg.id:
            return await event.reply(
                "Please supply a Whatsapp group id with the -id flag"
            )
        args = args.lower()
        if not (
            subscribed_info := bot.group_dict.setdefault(
                "subscribed_subreddits", {}
            ).get(args)
        ):
            return await event.reply(f"*Specified subscription does not exist!*")
        wa_chat_id = arg.id if arg.id != "." else event.chat.id
        if wa_chat_id not in (chats := subscribed_info.get("chats")):
            return await event.reply("Chat has already been removed or wasn't added.")
        chats.remove(wa_chat_id)
        await save2db2(bot.group_dict, "groups")
        await event.reply(
            f"*Successfully removed @{wa_chat_id}@g.us from subscription: {subscribed_info.get('name')}!*"
        )
    except Exception:
        await logger(Exception)


async def edit_subreddit_subscription(event, args, client):
    """
    Edit a subreddit subscription:
    Arguments:
        Subreddit Name (Must have been previously subscribed to)
    """
    try:
        user_id = event.from_user.id
        if not user_is_owner(user_id):
            return
        if not bot.reddit:
            return await event.reply(inactive_reddit_client_err)
        args = args.lower()
        if not (
            subscribed_info := bot.group_dict.setdefault(
                "subscribed_subreddits", {}
            ).get(args)
        ):
            return await event.reply(f"*Specified subscription does not exist!*")
        try:
            sub = await bot.reddit.subreddit(args, fetch=True)
        except Redirect:
            return await event.reply(
                "Specified subreddit does not exist/has been deleted!"
            )
        sub_name = sub.display_name
        f = "Add a chat"
        s = "Remove a chat"
        t = "Cancel"
        button_dict = {
            uuid.uuid4(): [f, add_subreddit_subscriber],
            uuid.uuid4(): [s, remove_subreddit_subscriber],
            uuid.uuid4(): [t, t],
        }
        text = f"Choose an action for subscription: {sub_name}"
        poll_msg = await create_sudo_button(
            text, button_dict, event.chat.jid, user_id, 1, None, event.message
        )
        dl_poll_msg = bot.client.revoke_message(
            event.chat.jid, bot.client.me.JID, poll_msg.ID
        )
        if not (results := await wait_for_button_response(poll_msg.ID)):
            await dl_poll_msg
            return await event.reply("Yh, I'm done waiting.")
        await dl_poll_msg
        info = button_dict.get(results[0])
        if info[0] == t:
            return await event.reply("*Operation Cancelled!*")
        if info[0] == s:
            text = get_list_of_added_chats(subscribed_info)
            await event.reply(text) if text else None
        text = "*Reply this message with the WhatsApp group id of chat to add/remove*\n_Also accepts '.' to specify current chat_"
        rep = await event.reply(text)
        listener = DummyListener()

        async def get_reply(event, _, __):
            if not ((replied := event.reply_to_message) and replied.id == rep.id):
                return
            if event.from_user.id != user_id:
                return
            if event.is_actual_media:
                return await event.reply("why?")
            if not (text := event.text):
                return
            listener.response = text

        key = bot.add_handler(get_reply)
        s_time = time.time()
        while (time.time() - s_time) < 60:
            if listener.response:
                bot.unregister(key)
                await rep.delete()
                break
            await asyncio.sleep(1)
        else:
            bot.unregister(key)
            await rep.delete()
            return await rep.reply("Operation Time out")
        await info[1](event, f"{args} -id {listener.response}", client)
    except Exception:
        await logger(Exception)


async def list_subreddit_subscriptions(event, args, client):
    "Lists all subreddit subscriptions"
    try:
        user_id = event.from_user.id
        if not user_is_owner(user_id):
            return
        msg = ""
        subscribed = bot.group_dict.setdefault("subscribed_subreddits", {})
        for i, sub in zip(itertools.count(1), subscribed):
            msg += f"{i}. {sub}"
            msg += "\n"
        if not msg:
            return await event.reply("No subscriptions!")
        msg = "*List of subscribed subreddits:*\n" + msg
        await event.reply(msg)
    except Exception:
        await logger(Exception)


async def manage(event, args, client):
    """Lists commands from the manage module"""
    try:
        pre = conf.CMD_PREFIX
        msg = (
            "*#Telegram*\n"
            f"{pre}bridge - *Bridge a chat*\n"
            f"{pre}unbridge - *Un-Bridge a chat*\n"
            f"{pre}add2sub - *Add a chat to an existing subscription*\n"
            f"{pre}edit_sub - *Edit an existing subscription*\n"
            f"{pre}rm_sub - *Remove a chat from an existing subscription*\n"
            f"{pre}subscribe - *Subscribe to a Telegram chat*\n"
            f"{pre}unsubscribe - *Unsubscribe from a Telegram chat*\n"
            "\n*#Reddit:*\n"
            f"{pre}add2rsub - *Add a chat to an existing subreddit subscription*\n"
            f"{pre}edit_rsub - *Edit an existing subreddit subscription*\n"
            f"{pre}rm_rsub - *Remove a chat from an existing subreddit subscription*\n"
            f"{pre}rsubscribe - *Subscribe to a Subreddit*\n"
            f"{pre}runsubscribe - *Unsubscribe from a Subreddit*\n"
            "\n*#Restart:*\n"
            f"{pre}restart - *Restarts bot*\n"
            f"{pre}update - *Update & restarts bot*\n"
            "\n*All above commands are restricted to the [Owner] permission class.*"
        )
        await event.reply(msg)
    except Exception:
        await logger(Exception)


########## ADD HANDLERS ##########
def add_manage_handlers():
    bot.add_handler(restart_handler, "restart")
    bot.add_handler(update_handler, "update")
    bot.add_handler(manage, "manage")
    bot.add_handler(
        add_subscriber,
        "add2sub",
        require_args=True,
    )
    bot.add_handler(
        edit_subscription,
        "edit_sub",
        require_args=True,
    )
    bot.add_handler(
        remove_subscriber,
        "rm_sub",
        require_args=True,
    )
    bot.add_handler(
        bridge,
        "bridge",
        require_args=True,
    )
    bot.add_handler(
        unbridge,
        "unbridge",
        require_args=True,
    )
    bot.add_handler(
        subscribe,
        "subscribe",
        require_args=True,
    )
    bot.add_handler(
        unsubscribe,
        "unsubscribe",
        require_args=True,
    )

    bot.add_handler(
        add_subreddit_subscriber,
        "add2rsub",
        require_args=True,
    )
    bot.add_handler(
        edit_subreddit_subscription,
        "edit_rsub",
        require_args=True,
    )
    bot.add_handler(
        remove_subreddit_subscriber,
        "rm_rsub",
        require_args=True,
    )
    bot.add_handler(
        subscribe_subreddit,
        "rsubscribe",
        require_args=True,
    )
    bot.add_handler(
        unsubscribe_subreddit,
        "runsubscribe",
        require_args=True,
    )
