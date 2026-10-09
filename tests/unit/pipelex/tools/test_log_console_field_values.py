from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from pipelex.tools.log.console_fields import FIELD_VALUE_MAX_LENGTH, TRUNCATION_MARK, format_field_value, format_layout_value


class _Sample(BaseModel):
    code: str
    count: int


class TestConsoleFieldValues:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (7, "7"),
            (0.5, "0.5"),
            (True, "true"),
            (None, "null"),
            ("alpha", "alpha"),
            ("two words", '"two words"'),
            ("", '""'),
            ('say "hi" now', '"say \\"hi\\" now"'),
            ("line\nbreak", '"line\\nbreak"'),
            ("\x1b[31mred", '"\\x1b[31mred"'),
            ({"key": "value", "nested": [1, 2]}, '{"key":"value","nested":[1,2]}'),
            (["a", "b"], '["a","b"]'),
            (("a", 1), '["a",1]'),
            (math.nan, "NaN"),
            ({"ratio": math.inf}, '{"ratio":"Infinity"}'),
            (_Sample(code="x", count=2), '{"code":"x","count":2}'),
            (Path("reports/march.csv"), "reports/march.csv"),
        ],
        ids=[
            "int",
            "float",
            "bool",
            "none",
            "bare string",
            "spaced string",
            "empty string",
            "quotes",
            "newline",
            "escape",
            "mapping",
            "list",
            "tuple",
            "nan",
            "nested infinity",
            "model",
            "path",
        ],
    )
    def test_a_value_renders_compactly_on_one_line(self, value: Any, expected: str) -> None:
        assert format_field_value(value=value) == expected

    def test_a_layout_substitutes_a_string_as_itself_and_still_on_one_line(self) -> None:
        assert format_layout_value(value="two words") == "two words"
        assert format_layout_value(value="line\nbreak") == "line\\nbreak"
        assert format_layout_value(value=7) == "7"

    def test_a_value_json_refuses_renders_as_its_repr(self) -> None:
        circular: dict[str, Any] = {}
        circular["self"] = circular

        assert format_field_value(value=circular) == "{'self': {...}}"

    def test_a_long_value_is_cut_short_at_the_limit_with_a_mark(self) -> None:
        rendered = format_field_value(value=list(range(200)))

        assert len(rendered) == FIELD_VALUE_MAX_LENGTH
        assert rendered.endswith(TRUNCATION_MARK)
        assert rendered.startswith("[0,1,2,")
