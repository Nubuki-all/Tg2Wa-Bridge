import shutil
from dataclasses import dataclass

from telethon import utils
from telethon.tl import types

from bridge_bot import bot, heavy_proc_lock

from .bot_utils import read_binary
from .log_utils import logger
from .media_utils import all_vid_streams_avc, convert_to_avc
from .os_utils import s_remove

# Same limit the other forwarders use before falling back to a document.
MAX_WA_MEDIA = 100000000


@dataclass
class RichMedia:
    kind: str  # image, video, gif, audio, voice or document
    data: bytes
    filename: str | None = None
    spoiler: bool = False


def child_blocks(block):
    """Yields the blocks nested inside a container block."""
    cover = getattr(block, "cover", None)
    if cover is not None:
        yield cover
    for field in ("blocks", "items"):
        for child in getattr(block, field, None) or []:
            if isinstance(child, types.TypePageBlock):
                yield child
            else:
                # List items that hold blocks.
                yield from getattr(child, "blocks", None) or []


def media_refs(blocks):
    """Yields (media id, spoiler) for each media block, in reading order."""
    for block in blocks:
        if isinstance(block, types.PageBlockPhoto):
            yield block.photo_id, bool(block.spoiler)
        elif isinstance(block, types.PageBlockVideo):
            yield block.video_id, bool(block.spoiler)
        elif isinstance(block, types.PageBlockAudio):
            yield block.audio_id, False
        elif isinstance(block, types.PageBlockDocument):
            yield block.document_id, False
        else:
            yield from media_refs(child_blocks(block))


def document_kind(doc) -> str:
    if any(isinstance(a, types.DocumentAttributeAnimated) for a in doc.attributes):
        return "gif"
    if utils.is_video(doc):
        return "video"
    if utils.is_audio(doc):
        for attr in doc.attributes:
            if isinstance(attr, types.DocumentAttributeAudio) and attr.voice:
                return "voice"
        return "audio"
    if utils.is_image(doc):
        return "image"
    return "document"


def document_filename(doc) -> str:
    for attr in doc.attributes:
        if isinstance(attr, types.DocumentAttributeFilename):
            return attr.file_name
    return f"{doc.id}{utils.get_extension(doc)}"


async def download_video(client, doc, name) -> bytes:
    """Downloads a video, converting it to AVC when WhatsApp can't play it."""
    if shutil.disk_usage("/").free <= doc.size:
        return await client.download_media(doc, file=bytes)
    in_ = f"temp/{name}.mp4"
    out_ = f"temp/{name}-1.mp4"
    try:
        await client.download_media(doc, file=in_)
        if not await all_vid_streams_avc(in_):
            async with heavy_proc_lock:
                await convert_to_avc(in_, out_)
            return await read_binary(out_)
        return await read_binary(in_)
    finally:
        s_remove(in_, out_)


async def download_rich_media(event) -> list[RichMedia]:
    """Downloads the photos and documents shown in a rich message."""
    rich = event.rich_message
    photos = {photo.id: photo for photo in rich.photos or []}
    documents = {doc.id: doc for doc in rich.documents or []}
    media, seen = [], set()
    for media_id, spoiler in media_refs(rich.blocks):
        if media_id in seen:
            continue
        seen.add(media_id)
        try:
            if photo := photos.get(media_id):
                data = await event.client.download_media(photo, file=bytes)
                media.append(RichMedia("image", data, spoiler=spoiler))
                continue
            if not (doc := documents.get(media_id)):
                continue
            kind = document_kind(doc)
            if kind in ("video", "gif") and doc.size <= MAX_WA_MEDIA:
                data = await download_video(
                    event.client, doc, f"{event.chat_id}:{event.id}:{doc.id}"
                )
            else:
                data = await event.client.download_media(doc, file=bytes)
            if len(data) > MAX_WA_MEDIA and kind != "document":
                kind = "document"
            media.append(RichMedia(kind, data, document_filename(doc), spoiler))
        except Exception:
            await logger(Exception)
    return media


async def send_rich_media(wa_jid, item: RichMedia, quoted=None):
    """Sends one downloaded rich message attachment to WA."""
    if item.kind == "image":
        return await bot.client.send_image(
            wa_jid, item.data, quoted=quoted, spoiler=item.spoiler
        )
    if item.kind in ("video", "gif"):
        gif = item.kind == "gif"
        return await bot.client.send_video(
            wa_jid,
            item.data,
            quoted=quoted,
            gifplayback=gif,
            is_gif=gif,
            spoiler=item.spoiler,
        )
    if item.kind in ("audio", "voice"):
        return await bot.client.send_audio(
            wa_jid, item.data, item.kind == "voice", quoted=quoted
        )
    return await bot.client.send_document(
        wa_jid, item.data, quoted=quoted, filename=item.filename
    )
