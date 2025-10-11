import pytest

from pipelex.tools.misc.string_utils import has_text


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("!!!", False),
        ("   ", False),
        ("Hello!", True),
        ("123", True),
        ("@#$%^", False),
        ('" "', False),
        ("```\n```", False),
    ],
)
def test_has_text(case: str, expected: bool) -> None:
    assert has_text(case) == expected, f"has_text('{case}') should be {expected}"
