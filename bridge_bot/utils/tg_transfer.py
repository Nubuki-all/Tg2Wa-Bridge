import asyncio
from io import BytesIO
from random import randint
from typing import Union

from telethon import TelegramClient
from telethon.tl.types import (
    Document,
    InputDocumentFileLocation,
    InputFileLocation,
    InputPeerPhotoFileLocation,
    InputPhotoFileLocation,
)

from .fast_telethon import download_file as _download_file
from .fast_telethon import upload_file as _upload_file
from .log_utils import logger

TypeLocation = Union[
    Document,
    InputDocumentFileLocation,
    InputPeerPhotoFileLocation,
    InputFileLocation,
    InputPhotoFileLocation,
]


async def download_file(
    client: TelegramClient,
    location: TypeLocation,
    out: str | type[bytes],
    event=None,
    progress_callback: callable = None,
    retries: int = 5,
) -> bytes | None:
    try:
        if isinstance(out, str):
            with open(out, "wb") as file:
                return await _download_file(client, location, file, progress_callback)
        file = BytesIO()
        await _download_file(client, location, file, progress_callback)
        return file.getvalue()
    except Exception as e:
        await logger(e=f"Fast_Telethon returned: {e}", warning=True)
        ee = "Retrying"
        ee += " with the default telethon downloader…" if not retries else "…"
        await logger(e=ee)
        await asyncio.sleep(randint(3, 9))
        if retries:
            return await download_file(
                client, location, out, event, progress_callback, (retries - 1)
            )
        return await event.download_media(file=out)


async def upload_file(
    client: TelegramClient,
    file: str | bytes,
    progress_callback: callable = None,
):
    try:
        if isinstance(file, str):
            with open(file, "rb") as out:
                return await _upload_file(client, out, progress_callback=progress_bar)
        out = BytesIO(file)
        return await _upload_file(client, out, progress_callback=progress_bar)
    except Exception as e:
        await logger(e=f"Fast_Telethon returned: {e}", warning=True)
