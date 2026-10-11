"""An LLM setting's `max_tokens` is an integer, `"auto"` or absent; any other value is refused.

Any other value used to be turned into the model's default without a word.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.cogt.llm.llm_setting import LLMSetting


class TestLLMSettingMaxTokens:
    @pytest.mark.parametrize(("value", "expected"), [(None, None), ("auto", None), (4096, 4096)])
    def test_none_auto_and_an_integer_are_accepted(self, value: Any, expected: int | None) -> None:
        assert LLMSetting.model_validate({"model": "test-model", "temperature": 0.5, "max_tokens": value}).max_tokens == expected

    @pytest.mark.parametrize(
        "value",
        [pytest.param("foo", id="a_string"), pytest.param(3.5, id="a_float"), pytest.param(True, id="a_boolean")],
    )
    def test_any_other_value_is_refused_rather_than_read_as_the_default(self, value: Any) -> None:
        with pytest.raises(ValidationError) as exc_info:
            LLMSetting.model_validate({"model": "test-model", "temperature": 0.5, "max_tokens": value})

        assert exc_info.value.errors()[0]["loc"][0] == "max_tokens"
