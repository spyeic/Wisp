from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
import base64

from PIL import Image
import pytest

from conftest import image_bytes, update
from images import ImageError, LimitedBuffer, download_image, image_attachment, validate_image


def test_largest_telegram_photo():
    assert image_attachment(update().message).file_id == "large"


def test_document_extension_fallback():
    message = update("document", document={"file_id": "d", "file_unique_id": "d", "file_name": "SCREENSHOT.PNG", "mime_type": "application/octet-stream"}).message
    assert image_attachment(message).file_id == "d"


def test_pdf_not_image():
    message = update("document", document={"file_id": "d", "file_unique_id": "d", "file_name": "paper.pdf", "mime_type": "application/pdf"}).message
    assert image_attachment(message) is None


@pytest.mark.parametrize("fmt,mime", [("PNG", "png"), ("JPEG", "jpeg"), ("WEBP", "webp"), ("GIF", "gif")])
def test_supported_image_bytes(config, fmt, mime):
    data = image_bytes(fmt)
    result = validate_image(data, config)
    assert result.startswith(f"data:image/{mime};base64,")
    assert base64.b64decode(result.split(",")[1]) == data


@pytest.mark.parametrize("data", [b"not a real image", b"%PDF-1.7", b"", b"\x89PNG\r\n\x1a\ninvalid"])
def test_invalid_image(config, data):
    with pytest.raises(ImageError):
        validate_image(data, config)


def test_pixel_limit(config):
    with pytest.raises(ImageError, match="dimensions"):
        validate_image(image_bytes(), replace(config, max_image_pixels=100))


def test_animation_rejected(config):
    buf = BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, format="GIF", save_all=True, append_images=[Image.new("RGB", (4, 4), "blue")])
    with pytest.raises(ImageError, match="animation"):
        validate_image(buf.getvalue(), config)


def test_orientation(config):
    buf = BytesIO()
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (20, 10)).save(buf, format="JPEG", exif=exif)
    result = validate_image(buf.getvalue(), config)
    with Image.open(BytesIO(base64.b64decode(result.split(",")[1]))) as image:
        assert image.size == (10, 20)


async def test_large_metadata_not_downloaded(config, context):
    attachment = SimpleNamespace(file_size=config.max_image_bytes + 1, file_id="large")
    with pytest.raises(ImageError):
        await download_image(context.bot, attachment, config)
    context.bot.get_file.assert_not_awaited()


async def test_unknown_size_checked_on_download(config, context):
    huge = b"0" * (config.max_image_bytes + 1)
    context.bot.get_file.return_value = SimpleNamespace(file_size=None, download_to_memory=AsyncMock(side_effect=lambda out: out.write(huge)))
    with pytest.raises(ImageError):
        await download_image(context.bot, SimpleNamespace(file_size=None, file_id="f"), config)


def test_limited_buffer():
    with LimitedBuffer(10) as buffer:
        buffer.write(b"12345")
        with pytest.raises(ImageError):
            buffer.write(b"123456")
