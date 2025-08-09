from datetime import datetime as dt

from telethon import events

from bridge_bot import bot, conf
from bridge_bot.utils.log_utils import logger
from bridge_bot.utils.msg_utils import event_handler, user_is_owner


async def up(event, args, client):
    """ping bot!"""
    user = event.from_user.id if client else event.sender_id
    if not user_is_owner(user):
        return
    ist = dt.now()
    msg = await event.reply("…")
    st = dt.now()
    ims = (st - ist).microseconds / 1000
    msg1 = "*Pong! ——* _{}ms_"
    if not client:
        msg1 = msg1.replace("*", "**").replace("_", "__")
    st = dt.now()
    await msg.edit(msg1.format(ims))
    ed = dt.now()
    ms = (ed - st).microseconds / 1000
    await msg.edit(f"1. {msg1.format(ims)}\n2. {msg1.format(ms)}")


async def up_tg(event):
    return await event_handler(event, up)


async def getcmds(event, args, client):
    """
    Get list of commands

    Arguments:
        None
    """
    user = event.from_user.id
    if not user_is_owner(user):
        return
    try:
        pre = conf.CMD_PREFIX
        msg = f"""{pre}manage - *[Owner] Manage bot*
{pre}tools - *[Owner] List tools commands*
{pre}ping - *Check if bot is alive*
{pre}bash - *[Dev.] Run bash commands*
{pre}eval - *[Dev.] Evaluate python commands*"""
        await event.reply(msg)
    except Exception as e:
        await logger(Exception)
        return await event.reply(f"*Error:*\n{e}")


def add_stuff_handlers():
    bot.add_handler(getcmds, "cmds")
    bot.add_handler(up, "ping")
    bot.tg_client.add_event_handler(up_tg, events.NewMessage(pattern="/ping"))
