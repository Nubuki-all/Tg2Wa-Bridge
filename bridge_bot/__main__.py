from bridge_bot.utils.os_utils import re_x

from . import (
    LOGS,
    ConnectedEv,
    DisconnectedEv,
    LoggedOutEv,
    MessageEv,
    NewAClient,
    PairStatusEv,
    bot,
    conf,
    time,
    traceback,
)
from .startup.after import on_startup
from .utils.events import POLL, Event, on_message
from .utils.os_utils import re_x
from .utils.sudo_button_utils import poll_as_button_handler
from .workers.handlers.dev import add_dev_handlers
from .workers.handlers.forward_to_wa import add_forward_handlers
from .workers.handlers.manage import add_manage_handlers
from .workers.handlers.stuff import add_stuff_handlers
from .workers.handlers.tg_to_wa import add_tg_bridge_handlers
from .workers.handlers.tools import add_tools_handlers
from .workers.handlers.wa_to_tg import add_wa_bridge_handlers

############ CLIENT ############


@bot.client.event(ConnectedEv)
async def on_connected(_: NewAClient, __: ConnectedEv):
    bot.is_connected = True


@bot.client.event(PairStatusEv)
async def on_paired(_: NewAClient, message: PairStatusEv):
    LOGS.info(message)


@bot.client.event(LoggedOutEv)
async def on_logout(_: NewAClient, __: LoggedOutEv):
    bot.is_connected = False
    LOGS.info("Bot has been logged out.")
    LOGS.info("Restarting…")
    time.sleep(10)
    re_x()


@bot.client.event(DisconnectedEv)
async def _(_: NewAClient, __: DisconnectedEv):
    if not bot.is_connected:
        LOGS.info("Restarting…")
        time.sleep(1)
        re_x()


@bot.register(POLL)
async def _(client: NewAClient, message: Event):
    await poll_as_button_handler(message)


@bot.client.event(MessageEv)
async def _(client: NewAClient, message: MessageEv):
    await on_message(client, message)


############ FILTERED ############


add_dev_handlers()
add_manage_handlers()
add_stuff_handlers()
add_tools_handlers()


############ AUTO ############

add_forward_handlers()
add_tg_bridge_handlers()
add_wa_bridge_handlers()


########### START ############


async def start_bot():
    try:
        await bot.tg_client.start(bot_token=conf.BOT_TOKEN)
        if bot.tg_client2:
            await bot.tg_client2.start()
        (
            await bot.client.PairPhone(conf.PH_NUMBER, show_push_notification=True)
            if conf.PH_NUMBER
            else await bot.client.connect()
        )
        await on_startup()
        # await bot.tg_client.catch_up()
        # if bot.tg_client2:
        # await bot.tg_client2.catch_up()
        await bot.client.idle()
    except Exception:
        LOGS.critical(traceback.format_exc())
        LOGS.critical("Cannot recover from error, exiting…")
        exit()


bot.client.loop.run_until_complete(start_bot())
