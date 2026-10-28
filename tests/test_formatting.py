import pytest

from formatting import Answer, Solution, format_solution, split_text, utf16_length


def test_answer_before_steps(solution):
    result = format_solution(solution)
    assert result == ["Answer: x = 5\n1. 2x + 3 = 13\n2. 2x = 10\n3. x = 5"]


def test_five_questions_each_appears_once_with_explanation():
    solution = Solution(language="en", answers=[
        Answer(label=str(i), answer=answer, explanation=f"Explanation {i}")
        for i, answer in enumerate(["A", "C", "B", "D", "A"], 1)
    ])
    result = format_solution(solution)
    assert len(result) == 1
    assert result[0] == "Answers:\n1. A\nExplanation 1\n\n2. C\nExplanation 2\n\n3. B\nExplanation 3\n\n4. D\nExplanation 4\n\n5. A\nExplanation 5"


def test_trivial_and_chinese():
    result = format_solution(Solution(language="zh", answers=[Answer(label="1", answer="正确", explanation="")]))
    assert result == ["答案：正确"]


@pytest.mark.parametrize("text", ["word " * 3000, "x" * 9000, "🙂" * 3000, "中文" * 3000, "a\n" * 3000])
def test_long_split_keeps_all_non_whitespace(text):
    result = split_text(text, 250)
    assert result and all(0 < utf16_length(chunk) <= 250 for chunk in result)
    assert "".join("".join(result).split()) == "".join(text.split())


def test_screenshot_sized_reply_stays_in_one_message():
    answers = [Answer(label=f"2({i})", answer="a" * 240, explanation="Useful explanation. " * 8) for i in "abcd"]
    result = format_solution(Solution(language="en", answers=answers))
    assert len(result) == 1
    for label in ["2(a)", "2(b)", "2(c)", "2(d)"]:
        assert result[0].count(label) == 1


def test_long_questions_split_only_at_telegram_limit():
    answers = [Answer(label=str(i), answer="a" * 1600, explanation="detail") for i in range(3)]
    result = format_solution(Solution(language="en", answers=answers))
    assert len(result) == 2
    assert "0. " in result[0] and "1. " in result[0]
    assert result[1].startswith("2. ")
    assert all(utf16_length(chunk) <= 4096 for chunk in result)
    assert "".join(result).count("a") == 4803  # Includes 'detail' three times.


@pytest.mark.parametrize("answer", ["x" * 10000, "🙂" * 5000])
def test_oversized_single_answer_preserves_all_content(answer):
    result = format_solution(Solution(language="en", answers=[Answer(label="1", answer=answer, explanation="")]))
    assert len(result) > 1
    assert all(utf16_length(chunk) <= 4096 for chunk in result)
    assert "".join(result) == "Answer: " + answer


def test_duplicate_explanation_omitted():
    result = format_solution(Solution(language="en", answers=[Answer(label="1", answer="True", explanation="True")]))
    assert result == ["Answer: True"]


def test_plain_math_preserved():
    answer = "dy/dx = (a+b)/(c+d); x^2 >= 0; sqrt(x)"
    assert format_solution(Solution(language="en", answers=[Answer(label="1", answer=answer, explanation="")])) == ["Answer: " + answer]


def test_split_preserves_code_indentation_after_newline():
    text = "def solve(x):\n    if x > 0:\n        return x\n    return 0"
    result = split_text(text, 28)
    assert "\n".join(result) == text


def test_reject_empty():
    with pytest.raises(ValueError):
        format_solution(Solution(language="en", answers=[]))
