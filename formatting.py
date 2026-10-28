"""Answer-first, plain-text output. Splitting never discards content."""
from typing import Literal

from pydantic import BaseModel, ConfigDict
from telegram.constants import MessageLimit


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    answer: str
    explanation: str


class Solution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Literal["en", "zh"]
    answers: list[Answer]


def utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def split_text(text: str, limit: int) -> list[str]:
    """Prefer lines, then spaces; use UTF-16 units conservatively for Telegram."""
    if limit < 2:
        raise ValueError("limit must be at least 2")
    remaining = text.strip()
    result = []
    while remaining:
        if utf16_length(remaining) <= limit:
            result.append(remaining)
            break
        units = 0
        end = 0
        for char in remaining:
            size = 2 if ord(char) > 0xFFFF else 1
            if units + size > limit:
                break
            units += size
            end += 1
        # Do not generate a tiny fragment merely because a heading has a newline.
        cut = remaining.rfind("\n", 0, end + 1)
        if cut < end // 3:
            cut = remaining.rfind(" ", 0, end + 1)
        if cut < end // 3:
            cut = end
        result.append(remaining[:cut].rstrip("\n"))
        # Consume only the split separator. lstrip() would destroy indentation
        # on a code line that starts the next Telegram message.
        separator = remaining[cut:cut + 1]
        remaining = remaining[cut + 1:] if separator in {"\n", " "} else remaining[cut:]
        remaining = remaining.lstrip("\n")
    return result


def format_solution(solution: Solution) -> list[str]:
    if not solution.answers or any(not item.answer.strip() for item in solution.answers):
        raise ValueError("No complete answer")
    zh = solution.language == "zh"
    multi = len(solution.answers) > 1
    blocks = []
    for index, item in enumerate(solution.answers, 1):
        label = item.label.strip() or str(index)
        prefix = f"{label}. " if multi else ("答案：" if zh else "Answer: ")
        answer = item.answer.strip()
        explanation = item.explanation.strip()
        block = prefix + answer
        # Suppress a verbatim restatement without modifying mathematical content.
        if explanation and explanation != answer:
            block += "\n" + explanation
        blocks.append(block)
    if multi:
        blocks[0] = ("答案：\n" if zh else "Answers:\n") + blocks[0]

    # Pack full question blocks into one message whenever possible. Only split
    # for Telegram's hard limit, preserving question boundaries when they fit.
    limit = int(MessageLimit.MAX_TEXT_LENGTH)
    messages = []
    current = ""
    for block in blocks:
        if current and utf16_length(current + "\n\n" + block) <= limit:
            current += "\n\n" + block
            continue
        if current:
            messages.append(current)
        chunks = split_text(block, limit)
        messages.extend(chunks[:-1])
        current = chunks[-1]
    if current:
        messages.append(current)
    return messages
