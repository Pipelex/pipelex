"""`TemplatingStyle` rejects unknown keys, directly and through the authoring surface that embeds it.

Every sibling authoring model is `extra="forbid"`; a misspelled optional key on the templating style
must be a validation error, not a silently different prompt shape.
"""

from typing import Any

import pytest
from kajson import kajson
from pydantic import ValidationError

from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat

_BASE_TABLE: dict[str, Any] = {
    "description": "templating style strictness test",
    "inputs": {"topic": "native.Text"},
    "output": "native.Text",
    "prompt": "Here is the topic:\n@topic",
}


class TestTemplatingStyleStrictness:
    def test_misspelled_optional_key_is_rejected(self):
        with pytest.raises(ValidationError, match="text_formt"):
            TemplatingStyle.model_validate({"tag_style": "xml", "text_formt": "markdown"})

    def test_well_formed_table_still_parses(self):
        style = TemplatingStyle.model_validate({"tag_style": "xml", "text_format": "markdown"})
        assert style == TemplatingStyle(tag_style=TagStyle.XML, text_format=TextFormat.MARKDOWN)

    def test_misspelled_key_is_rejected_through_pipe_llm_blueprint(self):
        with pytest.raises(ValidationError, match="text_formt"):
            PipeLLMBlueprint.model_validate({**_BASE_TABLE, "templating_style": {"tag_style": "xml", "text_formt": "markdown"}})

    def test_kajson_round_trip_survives_strictness(self):
        style = TemplatingStyle(tag_style=TagStyle.SQUARE_BRACKETS, text_format=TextFormat.MARKDOWN)
        assert kajson.loads(kajson.dumps(style)) == style
