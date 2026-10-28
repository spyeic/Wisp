import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from openai import AsyncOpenAI
import pytest
from telegram import Update
from telegram.error import NetworkError, RetryAfter
from telegram.ext import MessageHandler

from ai_client import AIClient, AIError, DEFAULT_IMAGE_REQUEST
from bot import WatchBot, send_text
from conftest import update
from formatting import Answer, Solution
from test_ai_client import response_body


def service(config, solution):
    ai = SimpleNamespace(solve=AsyncMock(return_value=solution), close=AsyncMock())
    return WatchBot(config, ai)


@pytest.mark.parametrize("kind", ["photo", "document"])
async def test_image_automatically_calls_ai_no_command(config, solution, context, kind):
    bot = service(config, solution)
    await bot.handle_message(update(kind), context)
    bot.ai.solve.assert_awaited_once()
    history, current = bot.ai.solve.call_args.args
    assert history == []
    assert current["content"][0]["text"] == DEFAULT_IMAGE_REQUEST
    assert current["content"][1]["image_url"].startswith("data:image/png;base64,")
    context.bot.send_message.assert_awaited_once()
    reply = context.bot.send_message.call_args.kwargs["text"]
    assert reply.startswith("Answer: x = 5\n1. 2x + 3 = 13")
    assert reply.endswith("3. x = 5")
    assert all(call.kwargs["parse_mode"] is None for call in context.bot.send_message.call_args_list)


async def test_caption_and_plain_followup_share_image(config, solution, context):
    bot = service(config, solution)
    await bot.handle_message(update(caption="Explain in Chinese."), context)
    assert bot.ai.solve.call_args.args[1]["content"][0]["text"] == "Explain in Chinese."
    await bot.handle_message(update("text", message_id=2), context)
    history, current = bot.ai.solve.call_args.args
    assert len(history) == 2
    assert history[0]["content"][1]["type"] == "input_image"
    assert "x = 5" in history[1]["content"]
    assert current["content"] == [{"type": "input_text", "text": "Explain question 3."}]


@pytest.mark.parametrize("uid,chat_type", [(999, "private"), (42, "group"), (42, "supergroup")])
async def test_whitelist_and_private_chat_before_download(config, solution, context, uid, chat_type):
    bot = service(config, solution)
    await bot.handle_message(update(user_id=uid, chat_type=chat_type), context)
    bot.ai.solve.assert_not_awaited()
    context.bot.get_file.assert_not_awaited()
    assert not bot.conversations.turns and not bot.locks


async def test_duplicate_update_only_one_call(config, solution, context):
    bot = service(config, solution)
    await asyncio.gather(bot.handle_message(update(), context), bot.handle_message(update(), context))
    bot.ai.solve.assert_awaited_once()
    context.bot.get_file.assert_awaited_once()


async def test_edited_message_ignored(config, solution, context):
    bot = service(config, solution)
    edited = Update(update_id=999, edited_message=update().message)
    await bot.handle_message(edited, context)
    bot.ai.solve.assert_not_awaited()


async def test_followup_queued_until_image_finishes(config, solution, context):
    bot = service(config, solution)
    entered, release = asyncio.Event(), asyncio.Event()
    histories = []
    async def solve(history, current):
        histories.append(history)
        if len(histories) == 1:
            entered.set()
            await release.wait()
        return solution
    bot.ai.solve.side_effect = solve
    first = asyncio.create_task(bot.handle_message(update(), context))
    await entered.wait()
    second = asyncio.create_task(bot.handle_message(update("text", message_id=2), context))
    await asyncio.sleep(0)
    assert len(histories) == 1
    release.set()
    await asyncio.gather(first, second)
    assert len(histories[1]) == 2
    assert histories[1][0]["content"][1]["type"] == "input_image"


async def test_rate_limit_no_second_api(config, solution, context):
    bot = service(replace(config, requests_per_minute=1), solution)
    await bot.handle_message(update(), context)
    await bot.handle_message(update("text", message_id=2), context)
    bot.ai.solve.assert_awaited_once()
    assert "Too many requests" in context.bot.send_message.call_args.kwargs["text"]


async def test_pending_queue_bounded(config, solution, context):
    bot = service(config, solution)
    bot.pending[42] = 3
    await bot.handle_message(update(), context)
    bot.ai.solve.assert_not_awaited()
    assert "pending" in context.bot.send_message.call_args.kwargs["text"]


@pytest.mark.parametrize("error", [AIError("AI temporarily unavailable."), RuntimeError("sensitive-token question image")])
async def test_failure_no_history_or_secret_leak(config, solution, context, caplog, error):
    bot = service(config, solution)
    bot.ai.solve.side_effect = error
    await bot.handle_message(update(), context)
    await bot.handle_message(update(), context)
    bot.ai.solve.assert_awaited_once()  # Duplicate failure also doesn't rebill.
    assert not bot.conversations.turns
    sent = context.bot.send_message.call_args.kwargs["text"]
    assert "Answer:" not in sent
    assert "sensitive-token" not in sent + caplog.text
    assert bot.pending[42] == 0


async def test_corrupt_document_no_ai(config, solution, context):
    bot = service(config, solution)
    context.bot.get_file.return_value.download_to_memory.side_effect = lambda out: out.write(b"not image")
    await bot.handle_message(update("document"), context)
    bot.ai.solve.assert_not_awaited()
    assert "cannot be read" in context.bot.send_message.call_args.kwargs["text"]


async def test_telegram_download_error(config, solution, context):
    bot = service(config, solution)
    context.bot.get_file.side_effect = NetworkError("private token")
    await bot.handle_message(update(), context)
    bot.ai.solve.assert_not_awaited()
    assert "failed" in context.bot.send_message.call_args.kwargs["text"]


async def test_delivery_failure_never_reinvokes_ai(config, solution, context):
    solution.answers[0].explanation = "Long explanation. " * 400
    bot = service(config, solution)
    context.bot.send_message.side_effect = [None, NetworkError("secret"), None]
    await bot.handle_message(update(), context)
    bot.ai.solve.assert_awaited_once()
    assert len(bot.conversations.history(42)) == 2
    assert "missing" in context.bot.send_message.call_args.kwargs["text"]


async def test_telegram_retry_after_retries_only_delivery(context):
    context.bot.send_message.side_effect = [RetryAfter(0), None]
    await send_text(context.bot, 42, "Answer: B")
    assert context.bot.send_message.await_count == 2


async def test_handler_registration(config, solution):
    bot = service(config, solution)
    app = bot.application()
    handler = next(handler for handler in app.handlers[0] if isinstance(handler, MessageHandler))
    for kind in ["photo", "document", "text"]:
        assert handler.check_update(update(kind))
    assert not handler.check_update(update("text", text="/unrecognized", entities=[{"type": "bot_command", "offset": 0, "length": 13}]))
    assert not handler.check_update(update(chat_type="group"))


async def test_start_and_reset_no_ai(config, solution, context):
    bot = service(config, solution)
    await bot.start(update("text", user_id=999), context)
    assert "999" in context.bot.send_message.call_args.kwargs["text"]
    await bot.handle_message(update(), context)
    await bot.reset(update("text", message_id=2), context)
    assert bot.conversations.history(42) == []
    bot.ai.solve.assert_awaited_once()


@pytest.mark.parametrize("provider", ["openai", "deepseek"])
async def test_mocked_full_path_five_questions_then_followup(config, context, provider):
    """Real PTB Update + image validation + real OpenAI SDK over MockTransport."""
    config = replace(config, ai_provider=provider, deepseek_api_key="fake")
    results = [Solution(language="en", answers=[Answer(label=str(i), answer=a, explanation="") for i, a in enumerate(["A", "C", "B", "D", "A"], 1)]),
               Solution(language="en", answers=[Answer(label="3", answer="B", explanation="The third answer follows from the given condition.")])]
    bodies = []
    def transport(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=response_body(results[len(bodies) - 1]))
    sdk = AsyncOpenAI(api_key="fake", base_url=config.ai_base_url, max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)))
    ai = AIClient(config, sdk)
    bot = WatchBot(config, ai)
    try:
        await bot.handle_message(update(), context)
        await bot.handle_message(update("text", message_id=2), context)
        assert len(bodies) == 2
        assert bodies[1]["input"][0]["content"][1]["type"] == "input_image"
        assert bodies[1]["input"][-1]["content"][0]["text"] == "Explain question 3."
        messages = [call.kwargs["text"] for call in context.bot.send_message.call_args_list]
        assert messages[0] == "Answers:\n1. A\n\n2. C\n\n3. B\n\n4. D\n\n5. A"
        assert messages[1] == "Answer: B\nThe third answer follows from the given condition."
        assert len(messages) == 2
    finally:
        await ai.close()
