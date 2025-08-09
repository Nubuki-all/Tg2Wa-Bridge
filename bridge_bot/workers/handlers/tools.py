import asyncio

from telethon import functions
from telethon.tl.types import InputStickerSetShortName

from bridge_bot.config import bot, conf
from bridge_bot.utils.bot_utils import download_sticker
from bridge_bot.utils.log_utils import logger
from bridge_bot.utils.media_utils import convert_to_wa_sticker
from bridge_bot.utils.msg_utils import user_is_owner
from bridge_bot.utils.stickerpack import create_stickerpack


async def download_stickers(stickers):
    funcs = [download_sticker(sticker) for sticker in stickers]
    return await asyncio.gather(*funcs)


async def convert_stickers(stickers, pack_name):
    funcs = [
        convert_to_wa_sticker(sticker, file_name, pack_name, return_type=True)
        for sticker, file_name in stickers
    ]
    return await asyncio.gather(*funcs)


async def tools(event, args, client):
    """Help Function for the tools module"""
    try:
        pre = conf.CMD_PREFIX
        s = "\n"
        msg = (
            f"{pre}get_stickerpack - *Tranfer stickerpack from Telegram to Whatsapp*"
            f"{s}"
        )
        await event.reply(msg)
    except Exception:
        await logger(Exception)


ctg_err_str = "*Please supply a valid telegram sticker link!*"
sticker_link_prefix = "https://t.me/addstickers/"


async def convert_tg_stickers(event, args, client):
    """
    Convert Telegram stickersets to Whatsapp sticker packs
    Argument:
        Link to stickersets;
            https://t.me/addstickers/{shortname}
    """
    try:
        if not user_is_owner(event.from_user.id):
            return
        if not args.startswith(sticker_link_prefix):
            return await event.reply(ctg_err_str)
        shortname = args.replace(sticker_link_prefix, "")
        if not shortname:
            return await event.reply(ctg_err_str)
        stickerset = await bot.tg_client(
            functions.messages.GetStickerSetRequest(
                InputStickerSetShortName(shortname), hash=0
            )
        )
        stick_doc = stickerset.documents
        await event.react("📥")
        stickers = await download_stickers(stick_doc)
        pack_name = stickerset.set.title
        await event.react("👩🏻‍🏭")
        stickers = await convert_stickers(stickers, pack_name)
        await event.react("🗂️")
        stickerpacks = await create_stickerpack(event, stickers, pack_name)
        await event.react("📤")
        for stickerpack in stickerpacks:
            await event.reply(message=stickerpack)
        await event.react("✅")
    except Exception as e:
        await logger(Exception)
        await event.reply(f"*Error:*\n{e}")


def add_tools_handlers():
    bot.add_handler(tools, "tools")
    bot.add_handler(convert_tg_stickers, "get_stickerpack")
