from dataclasses import replace
from io import BytesIO
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock

from PIL import Image
import pytest
from telegram import Update

from config import Config
from formatting import Answer, Solution


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("PTB_TIMEDELTA", "true")
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must not access the network")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


@pytest.fixture
def config():
    return replace(Config("123456:test-token", "test-key", frozenset({42, 43})), message_interval_ms=0)


@pytest.fixture
def solution():
    return Solution(language="en", answers=[Answer(label="1", answer="x = 5", explanation="1. 2x + 3 = 13\n2. 2x = 10\n3. x = 5")])


def image_bytes(fmt="PNG", size=(32, 32)):
    buffer = BytesIO()
    Image.new("RGB", size, "white").save(buffer, format=fmt)
    return buffer.getvalue()


def update(kind="photo", user_id=42, message_id=1, caption=None, chat_type="private", **extra):
    message = {"message_id": message_id, "date": 1700000000,
               "chat": {"id": user_id, "type": chat_type},
               "from": {"id": user_id, "is_bot": False, "first_name": "Test"}}
    if kind == "photo":
        message["photo"] = [
            {"file_id": "small", "file_unique_id": "s", "width": 8, "height": 8, "file_size": 80},
            {"file_id": "large", "file_unique_id": "l", "width": 32, "height": 32, "file_size": 200},
        ]
    elif kind == "document":
        message["document"] = {"file_id": "doc", "file_unique_id": "d", "file_name": "screenshot.png", "mime_type": "image/png", "file_size": 200}
    elif kind == "text":
        message["text"] = "Explain question 3."
    if caption is not None:
        message["caption"] = caption
    message.update(extra)
    return Update.de_json({"update_id": message_id + 100, "message": message}, None)


@pytest.fixture
def context():
    data = image_bytes()
    file = SimpleNamespace(file_size=len(data), download_to_memory=AsyncMock(side_effect=lambda out: out.write(data)))
    bot = SimpleNamespace(get_file=AsyncMock(return_value=file), send_message=AsyncMock(), send_chat_action=AsyncMock())
    return SimpleNamespace(bot=bot)
