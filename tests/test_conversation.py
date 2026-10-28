from dataclasses import replace

from ai_client import make_user_message
from conversation import ConversationStore


def test_isolated_and_bounded_pairs(config):
    store = ConversationStore(replace(config, max_history_messages=5))
    for index in range(5):
        store.add(42, make_user_message(str(index), None), str(index))
    history = store.history(42)
    assert len(history) == 4
    assert [item["role"] for item in history] == ["user", "assistant", "user", "assistant"]
    assert history[0]["content"][0]["text"] == "3"
    assert store.history(43) == []


def test_image_available_for_followup_and_old_images_removed(config):
    store = ConversationStore(config)
    for index in range(2):
        store.add(42, make_user_message(None, f"data:image/png;base64,{index}"), "answer")
    history = store.history(42)
    assert "removed" in history[0]["content"][1]["text"]
    assert history[2]["content"][1]["image_url"].endswith(",1")
    # Callers cannot mutate the saved context.
    history[2]["content"].clear()
    assert store.history(42)[2]["content"]


def test_expiry_in_active_conversation(config):
    now = [0]
    store = ConversationStore(replace(config, history_ttl_seconds=60), lambda: now[0])
    store.add(42, make_user_message(None, "image"), "answer")
    now[0] = 30
    store.add(42, make_user_message("why?", None), "because")
    now[0] = 61
    assert len(store.history(42)) == 2
    assert "image_url" not in str(store.history(42))
    now[0] = 91
    store.prune()
    assert store.turns == {}


def test_char_budget_and_clear(config):
    store = ConversationStore(replace(config, max_history_chars=50))
    store.add(42, make_user_message("small", None), "a" * 10)
    store.add(42, make_user_message("big", None), "a" * 40)
    assert len(store.history(42)) == 2
    store.add(42, make_user_message("too big", None), "a" * 60)
    assert store.history(42) == []
    store.add(42, make_user_message("again", None), "ok")
    store.clear(42)
    assert store.history(42) == []
