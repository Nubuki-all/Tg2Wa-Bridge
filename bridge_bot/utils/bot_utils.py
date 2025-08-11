import asyncio
import datetime
import io
import itertools
import zipfile
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from hashlib import sha256

import aiohttp
import pytz
from ffmpeg.asyncio import FFmpeg
from telethon import functions
from telethon.tl.types import (
    DocumentAttributeFilename,
    DocumentAttributeSticker,
    InputStickerSetEmpty,
)

from bridge_bot import bot

THREADPOOL = ThreadPoolExecutor(max_workers=1000)


def gfn(fn):
    "gets module path"
    return ".".join([fn.__module__, fn.__qualname__])


async def sync_to_async(func, *args, wait=True, **kwargs):
    pfunc = partial(func, *args, **kwargs)
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(THREADPOOL, pfunc)
    return await future if wait else future


class DummyListener:
    def __init__(self):
        self.completed = False
        self.error = None
        self.is_cancelled = False
        self.link = None
        self.name = None
        self.response = None
        self.size = 0


def list_to_str(lst: list, sep=" ", start: int = None, md=True):
    string = str()
    t_start = start if isinstance(start, int) else 1
    for i, count in zip(lst, itertools.count(t_start)):
        if start is None:
            string += str(i) + sep
            continue
        entry = f"`{i}`"
        string += f"{count}. {entry} {sep}"

    return string.rstrip(sep)


def split_text(text: str, split="\n", pre=False, list_size=4000):
    current_list = ""
    message_list = []
    for string in text.split(split):
        line = string + split if not pre else split + string
        if len(current_list) + len(line) <= list_size:
            current_list += line
        else:
            # Add current_list to account_list
            message_list.append(current_list)
            # Reset the current_list with a new "line".
            current_list = line
    # Add the last line into list.
    message_list.append(current_list)
    return message_list


async def get_json(link):
    async with aiohttp.ClientSession() as requests:
        result = await requests.get(link)
        return await result.json()


async def get_text(link):
    async with aiohttp.ClientSession() as requests:
        result = await requests.get(link)
        return await result.text()


tz = pytz.timezone("Africa/Lagos")


def get_timestamp(date: str):
    return (
        datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=tz)
        .timestamp()
    )


def get_date(value, start=False):
    if len(value.split()) == 3:
        index = len(value) // 2
        return value[:index] if start else value[index:]
    else:
        if start:
            if len(value.split()[0]) == 10:
                index = 19
                add_v = str()
            else:
                index = 10
                add_v = " 00:00:00"
            return value[:index] + add_v
        else:
            if len(value.split()[1]) == 8:
                index = 10
                add_v = str()
            else:
                index = 19
                add_v = " 00:00:00"
            return value[index:] + add_v


def get_date_from_ts(timestamp):
    try:
        date = datetime.datetime.fromtimestamp(timestamp, tz)
        return date.strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return 0


def time_formatter(seconds: float) -> str:
    """humanize time"""
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = (
        ((str(days) + "d, ") if days else "")
        + ((str(hours) + "h, ") if hours else "")
        + ((str(minutes) + "m, ") if minutes else "")
        + ((str(seconds) + "s, ") if seconds else "")
    )
    return tmp[:-2]


async def png_to_jpg(png: bytes):
    ffmpeg = (
        FFmpeg()
        .option("y")
        .input("pipe:0")
        .output(
            "pipe:1",
            f="mjpeg",
        )
    )
    return await ffmpeg.execute(png)


def get_sha256(string: str):
    return sha256(string.encode("utf-8")).hexdigest()


def trunc_string(string: str, limit: int):
    return (string[: limit - 2] + "…") if len(string) > limit else string


def split_list_in_half(list_: list):
    return (list_[: len(list_) // 2], list_[len(list_) // 2 :])


async def get_sticker_pack(event):
    for attrib in event.sticker.attributes:
        if isinstance(attrib, DocumentAttributeSticker):
            stickerset = attrib.stickerset
            break
    else:
        raise Exception(
            "Could not find the sticker attribute in the list of attributes."
        )
    if isinstance(stickerset, InputStickerSetEmpty):
        return None
    return await event.client(
        functions.messages.GetStickerSetRequest(stickerset, hash=0)
    )


def get_filename_from_doc(document):
    for attrib in document.attributes:
        if isinstance(attrib, DocumentAttributeFilename):
            return attrib.file_name
    else:
        raise Exception("No file_name found for sticker!")


async def download_sticker(document):
    bytes_ = await bot.tg_client.download_media(document, file=bytes)
    return bytes_, get_filename_from_doc(document)


def compare_inner_dict_value(outer_dict: dict, key, target: str) -> bool:
    return any(
        target == inner_dict[key]
        for inner_dict in outer_dict.values()
        if key in inner_dict
    )


def remove_inactive_wasubs():
    gcs = []
    active_wa_bridges = bot.group_dict.setdefault("active_wa_bridges", [])
    active_wa_subs = bot.group_dict.setdefault("active_wa_subs", [])
    subscribed = bot.group_dict.setdefault("subscribed_channels", {})
    for gc_id in list(active_wa_subs):
        for s in subscribed.values():
            if gc_id in s.get("chats"):
                break
        else:
            active_wa_subs.remove(gc_id)
            if gc_id not in active_wa_bridges:
                gcs.append(gc_id)
    return gcs


async def read_binary(file):
    def stdlib_read(file):
        with open(file, "rb") as f:
            return f.read()

    return await sync_to_async(stdlib_read, file)


async def write_binary(file, bytes_):
    def stdlib_write(file, bytes_):
        with open(file, "wb") as f:
            f.write(bytes_)

    return await sync_to_async(stdlib_write, file, bytes_)


def prepare_zip_file_content(file_name_content: dict) -> bytes:
    """
    returns Zip bytes
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for file_name, file_data in file_name_content.items():
            zip_file.writestr(file_name, file_data)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def human_format_num(num):
    num = float("{:.3g}".format(num))
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    return "{}{}".format(
        "{:f}".format(num).rstrip("0").rstrip("."), ["", "K", "M", "B", "T"][magnitude]
    )