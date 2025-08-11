import signal

import aiohttp

from bridge_bot import (
    LOGS,
    Message,
    asyncio,
    asyncpraw,
    bot,
    conf,
    jid,
    sys,
    traceback,
    version_file,
)
from bridge_bot.fun.emojis import enmoji, enmoji2
from bridge_bot.fun.quips import enquip, enquip2
from bridge_bot.utils.log_utils import logger
from bridge_bot.utils.msg_store import initialize_all_sessions
from bridge_bot.utils.msg_utils import send_presence
from bridge_bot.utils.reddit import auto_fetch_reddit_posts


async def onrestart():
    try:
        if sys.argv[1] == "restart":
            msg = "*Restarted!*"
        elif sys.argv[1].startswith("update"):
            s = sys.argv[1].split()[1]
            if s == "True":
                with open(version_file, "r") as file:
                    v = file.read()
                msg = f"*Updated to >>>* {v}"
            else:
                msg = "*No major update found!*\n" f"Bot restarted! {enmoji()}"
        else:
            return
        chat_id, msg_id, server = map(str, sys.argv[2].split(":"))
        await bot.client.edit_message(
            jid.build_jid(chat_id, server), msg_id, Message(conversation=msg)
        )
    except Exception:
        await logger(Exception)


async def onstart(text="*Please restart me.*"):
    i = conf.OWNER.split()[0]
    await bot.client.send_message(
        jid.build_jid(i),
        text,
    )


async def on_termination():
    try:
        dead_msg = f"*I'm* {enquip2()} {enmoji2()}"
        i = conf.OWNER.split()[0]
        await bot.client.send_message(
            jid.build_jid(i),
            dead_msg,
        )
    except Exception:
        pass
    # More cleanup code?
    await bot.client.stop()


async def save_tg_client_id():
    if not bot.tg_client2:
        return
    m = await bot.tg_client.get_me()
    bot.tg_client_ids.append(m.id)


async def update_presence():
    while True:
        try:
            await send_presence()
            await asyncio.sleep(5)
            await send_presence(False)
        except Exception:
            pass
        await asyncio.sleep(300)


async def initialize_reddit_client():
    try:
        init_reddit = False
        if conf.R_CLI_ID or conf.R_CLI_SECRET or conf.R_USER_NAME:
            if not (conf.R_CLI_ID and conf.R_CLI_SECRET and conf.R_USER_NAME):
                LOGS.warning(
                    "Missing a required env for Reddit, skipping initializing for the Reddit client."
                )
            else:
                init_reddit = True
        if init_reddit:
            bot.reddit = asyncpraw.Reddit(
                client_id=conf.R_CLI_ID,
                client_secret=conf.R_CLI_SECRET,
                requestor_kwargs={"session": bot.requests},
                user_agent=f"python:Tg2wa:{bot.version} (by u/{conf.R_USER_NAME})",
            )
    except Exception:
        LOGS.error(traceback.format_exc())


async def on_startup():
    try:
        await save_tg_client_id()
        loop = asyncio.get_running_loop()
        bot.requests = aiohttp.ClientSession(loop=loop)
        for signame in {"SIGINT", "SIGTERM", "SIGABRT"}:
            loop.add_signal_handler(
                getattr(signal, signame),
                lambda: asyncio.create_task(on_termination()),
            )
        await initialize_all_sessions()
        await initialize_reddit_client()
        while not bot.is_connected:
            await asyncio.sleep(0.5)
        # scheduler.start()
        if len(sys.argv) == 3:
            await onrestart()
        else:
            await onstart(f"*I'm {enquip()} {enmoji()}*")
        asyncio.create_task(update_presence())
        asyncio.create_task(auto_fetch_reddit_posts())
        LOGS.info("Bot has started.")
    except Exception:
        await logger(Exception)
