"""Validate real image bytes, not just Telegram MIME metadata. RAM only."""
import base64
from io import BytesIO
from pathlib import PurePath
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from config import Config


class ImageError(ValueError):
    """Messages are safe to display to the user."""


def image_attachment(message):
    if message.photo:
        return max(message.photo, key=lambda photo: photo.width * photo.height)
    document = message.document
    if document:
        extension = PurePath(document.file_name or "").suffix.lower()
        if (document.mime_type or "").startswith("image/") or extension in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            return document
    return None


class LimitedBuffer(BytesIO):
    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit

    def write(self, data):
        if self.tell() + len(data) > self.limit:
            raise ImageError("Image is too large. Send a smaller image or crop the question.")
        return super().write(data)


def validate_image(data: bytes, config: Config) -> str:
    if not data or len(data) > config.max_image_bytes:
        raise ImageError(f"Send an image smaller than {config.max_image_mb} MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as check:
                fmt = check.format
                if fmt not in {"PNG", "JPEG", "WEBP", "GIF"}:
                    raise ImageError("Use PNG, JPEG, WebP, or a non-animated GIF. Convert HEIC to JPEG first.")
                if check.width * check.height > config.max_image_pixels:
                    raise ImageError("Image dimensions are too large. Crop the question and resend.")
                if getattr(check, "is_animated", False):
                    raise ImageError("Send a still image, not an animation.")
                check.verify()
            with Image.open(BytesIO(data)) as decoded:
                decoded.load()  # Detect truncated/corrupt payloads before billing the API.
                if decoded.getexif().get(274, 1) != 1:
                    oriented = ImageOps.exif_transpose(decoded)
                    with LimitedBuffer(config.max_image_bytes) as output:
                        oriented.save(output, format=fmt)
                        data = output.getvalue()
    except ImageError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImageError("This image cannot be read. Send a clear PNG, JPEG, or WebP image.") from None
    mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}[fmt]
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


async def download_image(bot, attachment, config: Config) -> str:
    if attachment.file_size is not None and attachment.file_size > config.max_image_bytes:
        raise ImageError(f"Send an image smaller than {config.max_image_mb} MB.")
    file = await bot.get_file(attachment.file_id)
    if file.file_size is not None and file.file_size > config.max_image_bytes:
        raise ImageError(f"Send an image smaller than {config.max_image_mb} MB.")
    with LimitedBuffer(config.max_image_bytes) as buffer:
        await file.download_to_memory(buffer)
        data = buffer.getvalue()
    # PIL decoding is CPU work; leave the event loop free for Telegram updates.
    import asyncio
    return await asyncio.to_thread(validate_image, data, config)
