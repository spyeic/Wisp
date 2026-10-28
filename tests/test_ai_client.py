from dataclasses import replace
import json

import httpx
from openai import AsyncOpenAI
import pytest

from ai_client import AIClient, AIError, DEFAULT_IMAGE_REQUEST, SYSTEM_PROMPT, make_user_message


def response_body(solution, status="completed", content=None):
    return {"id": "resp_test", "object": "response", "created_at": 1700000000,
            "model": "gpt-5.4-2026-03-05", "status": status,
            "output": [{"id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
                        "content": content if content is not None else [{"type": "output_text", "text": solution.model_dump_json(), "annotations": []}]}]}


def test_language_and_caption():
    assert make_user_message(None, "image")["content"][0]["text"] == DEFAULT_IMAGE_REQUEST
    for text in ["Explain question 3.", "请用中文解释第三题", "Respond in English"]:
        assert make_user_message(text, "image")["content"][0]["text"] == text
    assert "中文" in make_user_message(None, "image", "zh")["content"][0]["text"]
    assert "Chinese text follow-ups receive" in SYSTEM_PROMPT
    assert "English text follow-ups receive English" in SYSTEM_PROMPT


@pytest.fixture(params=["openai", "deepseek"])
def provider_config(config, request):
    return replace(config, ai_provider=request.param, deepseek_api_key="deepseek-test-key")


async def test_actual_sdk_serialization_and_parsing(provider_config, solution, monkeypatch):
    config = provider_config
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response_body(solution))
    monkeypatch.setenv("OPENAI_BASE_URL", "https://wrong-host.invalid")
    monkeypatch.setenv("OPENAI_ORG_ID", "openai-test-org")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "openai-test-project")
    monkeypatch.setattr("ai_client.AsyncOpenAI", lambda **kwargs: AsyncOpenAI(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), **kwargs))
    ai = AIClient(config)
    try:
        image = "data:image/png;base64,AAAA"
        result = await ai.solve([], make_user_message(None, image))
        assert result == solution and len(requests) == 1
        assert str(requests[0].url) == config.ai_base_url + "/responses"
        assert requests[0].headers["authorization"] == "Bearer " + config.ai_api_key
        if config.ai_provider == "deepseek":
            assert not requests[0].headers.get("OpenAI-Organization")
            assert not requests[0].headers.get("OpenAI-Project")
        body = json.loads(requests[0].content)
        if config.ai_provider == "openai":
            assert body["store"] is False
        else:
            assert "store" not in body
        assert body["input"][0]["content"][1] == {"type": "input_image", "image_url": image, "detail": "high"}
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        assert body["reasoning"] == {"effort": "high"}
        assert body["model"] == config.ai_model
        assert body["max_output_tokens"] == config.max_output_tokens
    finally:
        await ai.close()


@pytest.mark.parametrize("failure", ["incomplete", "refusal", "invalid", "empty", "429", "500", "401", "network", "timeout"])
async def test_sdk_failures_no_retry(provider_config, solution, failure):
    config = provider_config
    calls = []
    def handler(request):
        calls.append(request)
        if failure == "network":
            raise httpx.ConnectError("private request detail", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("private request detail", request=request)
        if failure.isdigit():
            return httpx.Response(int(failure), json={"error": {"message": "private request detail", "type": "api_error"}})
        content = None
        if failure == "refusal":
            content = [{"type": "refusal", "refusal": "Cannot answer"}]
        elif failure == "invalid":
            content = [{"type": "output_text", "text": '{"language":', "annotations": []}]
        elif failure == "empty":
            content = []
        return httpx.Response(200, json=response_body(solution, status="incomplete" if failure == "incomplete" else "completed", content=content))
    sdk = AsyncOpenAI(api_key="fake", max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    ai = AIClient(config, sdk)
    try:
        with pytest.raises(AIError) as error:
            await ai.solve([], make_user_message("question", None))
        assert "private request detail" not in str(error.value)
        assert len(calls) == 1
    finally:
        await ai.close()


async def test_hard_timeout(config):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    async def slow(**kwargs):
        await asyncio.sleep(10)
    client = SimpleNamespace(responses=SimpleNamespace(parse=AsyncMock(side_effect=slow)))
    ai = AIClient(replace(config, request_timeout_seconds=0.01), client)
    with pytest.raises(AIError, match="timed out"):
        await ai.solve([], make_user_message("question", None))
    client.responses.parse.assert_awaited_once()


@pytest.mark.parametrize("in_history", [False, True])
async def test_text_only_deepseek_rejects_current_or_history_images(config, in_history):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    client = SimpleNamespace(responses=SimpleNamespace(parse=AsyncMock()))
    ai = AIClient(replace(config, ai_provider="deepseek", deepseek_model="deepseek-v4-pro"), client)
    image = make_user_message(None, "data:image/png;base64,AAAA")
    history, user = ([image], make_user_message("Explain it", None)) if in_history else ([], image)
    with pytest.raises(AIError, match="does not support images"):
        await ai.solve(history, user)
    client.responses.parse.assert_not_awaited()


async def test_deepseek_followup_preserves_image_and_hides_reasoning(config, solution):
    config = replace(config, ai_provider="deepseek", deepseek_api_key="fake")
    bodies = []
    def handler(request):
        bodies.append(json.loads(request.content))
        response = response_body(solution)
        response["model"] = "deepseek-flash"
        response["output"].insert(0, {"type": "reasoning", "id": "reasoning_1", "summary": [],
                                      "content": [{"type": "reasoning_text", "text": "PRIVATE_REASONING"}]})
        return httpx.Response(200, json=response)
    sdk = AsyncOpenAI(api_key="fake", base_url=config.ai_base_url, max_retries=0,
                      http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    ai = AIClient(config, sdk)
    try:
        image = make_user_message(None, "data:image/png;base64,AAAA")
        first = await ai.solve([], image)
        history = [image, {"role": "assistant", "content": first.model_dump_json()}]
        second = await ai.solve(history, make_user_message("Explain step 2", None))
        assert second == solution
        assert bodies[1]["input"][0]["content"][1]["image_url"].endswith(",AAAA")
        assert "PRIVATE_REASONING" not in str(bodies) + second.model_dump_json()
        assert len(bodies) == 2
    finally:
        await ai.close()


async def test_deepseek_text_only_model_and_separate_effort(config, solution):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    client = SimpleNamespace(responses=SimpleNamespace(parse=AsyncMock(
        return_value=SimpleNamespace(status="completed", output_parsed=solution))))
    config = replace(config, ai_provider="deepseek", deepseek_model="deepseek-v4-pro",
                     deepseek_reasoning_effort="max", reasoning_effort="low")
    ai = AIClient(config, client)
    assert await ai.solve([], make_user_message("Solve x + 1 = 2", None)) == solution
    assert client.responses.parse.call_args.kwargs["model"] == "deepseek-v4-pro"
    assert client.responses.parse.call_args.kwargs["reasoning"] == {"effort": "max"}
