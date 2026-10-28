"""Bounded in-memory turns; images expire even in an active conversation."""
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
import time

from config import Config


@dataclass
class Turn:
    user: dict
    assistant: str
    created_at: float


def text_size(turn: Turn) -> int:
    return len(turn.assistant) + sum(len(part.get("text", "")) for part in turn.user["content"])


class ConversationStore:
    def __init__(self, config: Config, clock=time.monotonic):
        self.config = config
        self.clock = clock
        self.turns: dict[int, deque[Turn]] = {}

    def prune(self) -> None:
        now = self.clock()
        for uid in list(self.turns):
            turns = self.turns[uid]
            while turns and now - turns[0].created_at >= self.config.history_ttl_seconds:
                turns.popleft()
            while len(turns) * 2 > self.config.max_history_messages or sum(map(text_size, turns)) > self.config.max_history_chars:
                turns.popleft()
            images_left = self.config.max_history_images
            for turn in reversed(turns):
                content = []
                for part in reversed(turn.user["content"]):
                    if part["type"] == "input_image":
                        if images_left:
                            images_left -= 1
                        else:
                            part = {"type": "input_text", "text": "[Earlier image removed from memory. Do not invent unreadable or unavailable details.]"}
                    content.append(part)
                turn.user["content"] = list(reversed(content))
            if not turns:
                del self.turns[uid]

    def history(self, user_id: int) -> list[dict]:
        self.prune()
        messages = []
        for turn in self.turns.get(user_id, []):
            messages.extend([deepcopy(turn.user), {"role": "assistant", "content": turn.assistant}])
        return messages

    def add(self, user_id: int, user: dict, assistant: str) -> None:
        self.turns.setdefault(user_id, deque()).append(Turn(deepcopy(user), assistant, self.clock()))
        self.prune()

    def clear(self, user_id: int) -> None:
        self.turns.pop(user_id, None)
