import asyncio
import base64
import time
import uuid
from typing import List

import magic
from neonize.utils.enum import MediaType
from wand.image import Image as wand_image

from bridge_bot import StickerPackMessage
from bridge_bot.config import bot

from .bot_utils import prepare_zip_file_content, sync_to_async

sem = asyncio.Semaphore(50)


async def upload_sticker(client, sticker, animated, zip_dict):
    async with sem:
        upload = await client.upload(sticker)
    b64 = base64.b64encode(upload.FileSHA256)
    file_name = b64.decode("ascii").replace("/", "-") + ".webp"
    # b64 = base64.urlsafe_b64encode(upload.FileSHA256)
    # file_name = b64.decode("ascii") + ".webp"
    mimetype = magic.from_buffer(sticker, mime=True)
    zip_dict.update({file_name: sticker})
    return StickerPackMessage.Sticker(
        fileName=file_name,
        isAnimated=animated,  # Debug
        accessibilityLabel="",
        isLottie=False,
        mimetype=mimetype,
    )


def webp_to_img(webp):
    with wand_image(blob=webp, format="webp") as img:
        with img.convert("png") as img2:
            img2 = img2.image_get()
            img2.sample(252, 252)
            return img2.make_blob(format="png")


async def create_stickerpack(
    event, stickers: list, pack_name: str
) -> List[StickerPackMessage]:
    def ensure_non_broken_packs(stickers):
        return [sticker for sticker in stickers if len(sticker[0]) < 1000000]

    stickers = ensure_non_broken_packs(stickers)
    CHUNK_SIZE = 60
    chunks = [stickers[i : i + CHUNK_SIZE] for i in range(0, len(stickers), CHUNK_SIZE)]
    tasks = []
    for idx, chunk in enumerate(chunks):
        pack_suffix = f" ({idx + 1})" if len(chunks) > 1 else ""
        task = _process_single_pack(
            event=event,
            stickers=chunk,
            pack_name=pack_name + pack_suffix,
        )
        tasks.append(task)

    return await asyncio.gather(*tasks)


async def _process_single_pack(
    event,
    stickers: list,
    pack_name: str,
):
    """Helper function to process a single sticker pack chunk"""
    zip_dict = {}

    # Upload all stickers concurrently
    funcs = [
        upload_sticker(event.client, sticker, animated, zip_dict)
        for sticker, animated in stickers
    ]
    sticker_metadata = await asyncio.gather(*funcs)

    # Generate unique pack ID
    sticker_id = f"{uuid.uuid4()}"

    tray_icon = f"{sticker_id}.png"
    cover = await sync_to_async(webp_to_img, stickers[0][0])
    zip_dict.update({tray_icon: cover})

    file_size = 0
    for f in zip_dict.values():
        file_size += len(f)

    # Create zip archive
    sticker_pack = await sync_to_async(prepare_zip_file_content, zip_dict)

    # Create cover from first sticker
    thumbnail = await event.client.upload(cover)

    # Generate img hash
    img_hash = base64.b64encode(thumbnail.FileSHA256).decode("utf-8").replace("/", "-")

    # Upload sticker pack
    upload = await event.client.upload(sticker_pack, MediaType.MediaStickerPack)

    return StickerPackMessage(
        stickerPackID=sticker_id,
        name=pack_name,
        publisher=bot.client.me.PushName,
        stickers=sticker_metadata,
        # fileLength=upload.FileLength,
        fileLength=file_size,
        fileSHA256=upload.FileSHA256,
        fileEncSHA256=upload.FileEncSHA256,
        mediaKey=upload.MediaKey,
        directPath=upload.DirectPath,
        mediaKeyTimestamp=int(time.time()),
        trayIconFileName=tray_icon,
        thumbnailDirectPath=thumbnail.DirectPath,
        thumbnailSHA256=thumbnail.FileSHA256,
        thumbnailEncSHA256=thumbnail.FileEncSHA256,
        thumbnailHeight=252,
        thumbnailWidth=252,
        imageDataHash=img_hash,
        stickerPackSize=upload.FileLength,
        stickerPackOrigin=StickerPackMessage.StickerPackOrigin.USER_CREATED,
    )
