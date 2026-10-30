import asyncio
import shutil
import uuid
from os import cpu_count, makedirs

from neonize.utils.ffmpeg import AFFmpeg
from neonize.utils.sticker import add_exif
from wand.image import Image as wand_image

from bridge_bot.config import bot

from .bot_utils import read_binary, write_binary
from .log_utils import log, logger
from .os_utils import enshell, file_exists, s_remove, size_of


async def all_vid_streams_avc(file_path):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "csv=p=0",
        file_path,
    ]
    process, stdout, stderr = await enshell(cmd)
    if process.returncode != 0:
        raise RuntimeError(
            # type: ignore
            f"stderr: {stderr} Return code: {process.returncode}"
        )
    output = stdout.strip()
    codecs = output.split("\n")
    return all(codec == "h264" for codec in codecs)  # For mis-mapped videos


async def convert_to_avc(input_path: str, output_path: str):
    """
    Convert video to AVC (H.264) with quality preservation
    using FFmpeg's CRF (Constant Rate Factor) encoding
    """
    cmd = [
        "ffmpeg",
        "-i",
        input_path,
        "-c:v",
        "libx264",  # H.264 encoder
        "-crf",
        "25",  # Quality range (0-51, lower=better)
        "-preset",
        "slow",  # Better compression efficiency
        "-tune",
        "film",  # Optimization for film content
        "-c:a",
        "aac",  # Audio codec
        "-b:a",
        "192k",  # Audio bitrate
        "-movflags",
        "+faststart",  # Web optimization
        "-pix_fmt",
        "yuv420p",  # Widest compatibility
        "-y",  # Overwrite output
        output_path,
    ]

    process, stdout, stderr = await enshell(cmd)
    if process.returncode != 0:
        raise RuntimeError(
            # type: ignore
            f"stderr: {stderr} Return code: {process.returncode}"
        )


async def is_mp3_audio(file_path: str) -> bool:
    """
    Check if an audio file is MP3 encoded using FFprobe
    Returns True if the first audio stream is MP3, False otherwise
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",  # First audio stream
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        file_path,
    ]

    process, stdout, stderr = await enshell(cmd)
    if process.returncode != 0:
        raise RuntimeError(
            # type: ignore
            f"stderr: {stderr} Return code: {process.returncode}"
        )
    output = stdout.strip().lower()
    # MP3 can be reported as 'mp3' or 'mp2' (for MPEG-1 Layer II/III)
    return output in ["mp3", "mp2"]


vstick_sem = asyncio.Semaphore(20)
astick_sem = asyncio.Semaphore(10)
exif_sem = asyncio.Semaphore(50)


async def convert_to_wa_sticker(sticker, file_name, packname, return_type=False):
    animated = False
    if file_name.endswith("webp"):
        buf = await add_sticker_exif(sticker, packname)
        return buf if not return_type else (buf, animated)
    animated = True
    if file_name.endswith("webm"):
        async with AFFmpeg(sticker) as ffmpeg:
            async with vstick_sem:
                sticker = await ffmpeg.cv_to_webp(
                    enforce_not_broken=True,
                    animated_gif=True,
                    max_sticker_size=712000,
                    is_webm=True,
                )
                if len(sticker) > 1000000:
                    log(
                        e="@webm_to_webp: Sticker larger than limit, trying another method to reduce size"
                    )
                    sticker = await ffmpeg.cv_to_webp(
                        enforce_not_broken=True,
                        animated_gif=False,
                        max_sticker_size=712000,
                        is_webm=True,
                    )
            buf = await add_sticker_exif(sticker, packname)
            return buf if not return_type else (buf, animated)
    if file_name.endswith("tgs"):
        buf = await tgs_to_webp(sticker, packname)
        return buf if not return_type else (buf, animated)
    else:
        raise Exception(f"Unsupported sticker; {file_name}")


async def tgs_to_webp(sticker, packname):
    base = f"temp/{uuid.uuid4()}"
    file = base + ".tgs"
    outfile = base + ".webm"
    await write_binary(file, sticker)
    cmd = [
        "bin/lottie_to_webm.sh",
        file,
        "--output",
        outfile,
        "--quality",
        "80",
    ]
    async with astick_sem:
        process, stdout, stderr = await enshell(cmd)
    if process.returncode != 0:
        raise RuntimeError(
            # type: ignore
            f"stderr: {stderr} Return code: {process.returncode}"
        )
    s_remove(file)
    async with AFFmpeg(outfile) as ffmpeg:
        async with vstick_sem:
            sticker = await ffmpeg.cv_to_webp(
                enforce_not_broken=True,
                animated_gif=True,
                max_sticker_size=712000,
                is_webm=True,
            )
    s_remove(outfile)
    if len(sticker) > 1000000:
        return await _tgs_to_webp(sticker, packname)
    return await add_sticker_exif(sticker, packname)


async def _tgs_to_webp(sticker, packname):
    base = f"temp/{uuid.uuid4()}"
    file = base + ".tgs"
    outfile = base + ".webp"
    await write_binary(file, sticker)
    cmd = [
        "bin/lottie_to_webp.sh",
        file,
        "--output",
        outfile,
        "--quality",
        "xx",
        "--fps",
        "xx",
    ]
    fps = 24
    i = 1
    quality = 50
    while True:
        cmd[5] = f"{quality}"
        cmd[7] = f"{fps}"
        log(e=f"Attempt #{i}, quality={quality}%, fps={fps}")
        async with astick_sem:
            process, stdout, stderr = await enshell(cmd)
        if process.returncode != 0:
            raise RuntimeError(
                # type: ignore
                f"stderr: {stderr} Return code: {process.returncode}"
            )
        fps -= 2
        i += 1
        quality -= 10
        s_size = size_of(outfile)
        if not (quality or s_size < 1000000):
            await logger(
                e="Could not ensure sticker size falls between Whatsapp limits."
            )
            break
        if s_size < 1000000:
            break
        s_remove(outfile)
    s_remove(file)
    sticker = await add_sticker_exif(outfile, packname)
    s_remove(outfile)
    return sticker


async def add_sticker_exif(sticker: str | bytes, packname="Test!"):
    base = f"temp/{uuid.uuid4()}"
    exif_file = base + "_exif"
    temp_file = base + ".webp"
    await write_binary(exif_file, add_exif(packname, bot.client.me.PushName))
    async with AFFmpeg(sticker) as ffmpeg:
        cmd = [
            "webpmux",
            "-set",
            "exif",
            exif_file,
            ffmpeg.filepath,
            "-o",
            temp_file,
        ]
        async with exif_sem:
            await ffmpeg.call(cmd)
    s_remove(exif_file)
    buf = await read_binary(temp_file)
    s_remove(temp_file)
    return buf


async def get_video_thumbnail(file, with_dur=False):
    try:
        output = f"temp/{uuid.uuid4()}.jpg"
        async with AFFmpeg(file) as ffmpeg:
            duration = int((await ffmpeg.extract_info()).format.duration)
            if duration == 0:
                duration = 3
            tduration = duration // 2
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{tduration}",
                "-i",
                ffmpeg.filepath,
                "-vf",
                "thumbnail",
                "-q:v",
                "1",
                "-frames:v",
                "1",
                "-threads",
                f"{cpu_count() // 2}",
                f"{output}",
                "-y",
            ]
            await ffmpeg.call(cmd)
        if not file_exists(output):
            return
        buf = await read_binary(output)
        s_remove(output)
        if with_dur:
            return (buf, duration)
        return buf
    except Exception:
        await logger(Exception)


TG_VIDEO_STICKER_MAX = 256 * 1024
# Longer stickers are cut to just under 10 seconds.
TG_VIDEO_STICKER_MAX_SECONDS = 9.9
TG_VIDEO_STICKER_ATTEMPTS = 5


def _webp_frames(sticker: bytes, folder: str) -> list[tuple[str, float]]:
    """Saves each full frame of an animated WebP; returns (path, seconds)."""
    frames = []
    with wand_image(blob=sticker, format="webp") as img:
        # Frames can cover only part of the canvas; make each one whole.
        img.coalesce()
        for i, frame in enumerate(img.sequence):
            path = f"{folder}/{i:04d}.png"
            with wand_image(image=frame) as page:
                # Temporary file: favour speed over size.
                page.options["png:compression-level"] = "1"
                page.save(filename=path)
            ticks = frame.ticks_per_second or 100
            # Players show frames with no delay for 100ms.
            seconds = frame.delay / ticks if frame.delay else 0.1
            frames.append((path, max(seconds, 0.02)))
    return frames


async def webp_to_tg_video_sticker(sticker: bytes) -> bytes:
    """Converts an animated WebP to a WebM Telegram accepts as a video sticker:
    VP9 with alpha, 512px on the longest side, at most 30 fps and 256 KB.

    Telegram's docs say 3 seconds at most, but longer video stickers are
    common and play fine, so up to TG_VIDEO_STICKER_MAX_SECONDS is kept, and
    the file is written without a duration, like those stickers are."""
    folder = f"temp/{uuid.uuid4()}"
    makedirs(folder)
    try:
        frames = await asyncio.to_thread(_webp_frames, sticker, folder)
        if not frames:
            raise ValueError("Animated sticker has no frames")
        listing = "".join(
            f"file '{path.rsplit('/', 1)[1]}'\nduration {seconds}\n"
            for path, seconds in frames
        )
        # The concat demuxer ignores the last duration unless the file repeats.
        listing += f"file '{frames[-1][0].rsplit('/', 1)[1]}'\n"
        await write_binary(f"{folder}/frames.txt", listing.encode())
        outfile = f"{folder}/sticker.webm"
        duration = min(
            sum(seconds for _, seconds in frames), TG_VIDEO_STICKER_MAX_SECONDS
        )
        # Quality first, with the bitrate capped so the length should fit.
        # VP9 often overshoots a low cap, so each retry scales the cap by how
        # far over the last try was, and lowers the quality a step.
        crf = 35
        bitrate = TG_VIDEO_STICKER_MAX * 8 * 0.9 / duration
        for _ in range(TG_VIDEO_STICKER_ATTEMPTS):
            cmd = [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "concat",
                "-i",
                f"{folder}/frames.txt",
                "-vf",
                "fps=30,scale=512:512:force_original_aspect_ratio=decrease"
                ":force_divisible_by=2:flags=lanczos,format=yuva420p",
                # Also stops the repeated last frame adding a little extra.
                "-t",
                f"{duration:.3f}",
                "-an",
                "-c:v",
                "libvpx-vp9",
                "-crf",
                str(crf),
                "-b:v",
                f"{int(bitrate / 1000)}k",
                "-deadline",
                "good",
                "-cpu-used",
                "4",
                "-row-mt",
                "1",
                # Don't write the duration into the file.
                "-live",
                "1",
                "-y",
                outfile,
            ]
            async with vstick_sem:
                process, stdout, stderr = await enshell(cmd)
            if process.returncode != 0:
                raise RuntimeError(
                    f"stderr: {stderr} Return code: {process.returncode}"
                )
            webm = await read_binary(outfile)
            if not webm:
                raise RuntimeError(f"ffmpeg wrote an empty sticker; stderr: {stderr}")
            if len(webm) <= TG_VIDEO_STICKER_MAX:
                return webm
            log(
                e=f"@webp_to_tg_video_sticker: {len(webm)} bytes at crf {crf}, "
                f"{int(bitrate / 1000)}k; over Telegram's limit, trying smaller"
            )
            bitrate *= TG_VIDEO_STICKER_MAX * 0.9 / len(webm)
            crf = min(crf + 5, 50)
        raise RuntimeError(
            f"Sticker still {len(webm)} bytes after "
            f"{TG_VIDEO_STICKER_ATTEMPTS} tries"
        )
    finally:
        shutil.rmtree(folder, ignore_errors=True)
