import json

import pytest
from pydantic import ValidationError

from pipelex.core.stuffs.rating_content import RatingContent
from pipelex.tools.templating.text_format import TextFormat


class TestRatingContent:
    """`Rating` requires its level index; `label` names the selected level, and `confidence`, `probabilities` and `position` are optional measures."""

    def test_requires_the_level(self):
        with pytest.raises(ValidationError, match="level"):
            RatingContent.model_validate({})

    def test_measures_are_absent_by_default(self):
        content = RatingContent(level=2)
        assert content.label is None
        assert content.confidence is None
        assert content.probabilities is None
        assert content.position is None

    def test_accepts_every_measure(self):
        content = RatingContent(level=1, confidence=0.6, probabilities={"0": 0.1, "1": 0.6, "2": 0.3}, position=1.2)
        assert content.level == 1
        assert content.position == 1.2
        assert content.probabilities == {"0": 0.1, "1": 0.6, "2": 0.3}

    def test_accepts_the_label_of_the_selected_level(self):
        content = RatingContent(level=1, label="Workaround available")
        assert content.level == 1
        assert content.label == "Workaround available"

    @pytest.mark.parametrize("label", [1, 1.5, True, ["Cosmetic"]])
    def test_refuses_a_label_that_is_not_a_text(self, label: object):
        with pytest.raises(ValidationError, match="label"):
            RatingContent.model_validate({"level": 1, "label": label})

    def test_refuses_a_negative_level(self):
        with pytest.raises(ValidationError, match="level"):
            RatingContent(level=-1)

    def test_refuses_a_negative_position(self):
        with pytest.raises(ValidationError, match="position"):
            RatingContent(level=0, position=-0.5)

    @pytest.mark.parametrize("confidence", [-0.1, 1.1])
    def test_refuses_a_confidence_outside_the_unit_interval(self, confidence: float):
        with pytest.raises(ValidationError, match="confidence"):
            RatingContent(level=0, confidence=confidence)

    def test_refuses_a_probability_outside_the_unit_interval(self):
        with pytest.raises(ValidationError, match="probabilities"):
            RatingContent(level=0, probabilities={"0": 1.2})

    def test_renders_as_its_level_without_a_label(self):
        content = RatingContent(level=3, position=2.7)
        assert content.rendered_plain() == "3"
        assert content.rendered_markdown() == "3"
        assert content.rendered_html() == "3"
        assert content.rendered_for_prompt() == "3"
        assert content.rendered_for_prompt(text_format=TextFormat.MARKDOWN) == "3"
        assert content.rendered_for_prompt(text_format=TextFormat.HTML) == "3"
        assert str(content) == "3"

    def test_renders_as_its_label_when_it_has_one(self):
        """`$severity` in a later prompt reads the level's name, not its index."""
        content = RatingContent(level=1, label="Workaround available", position=1.2)
        assert content.rendered_plain() == "Workaround available"
        assert content.rendered_markdown() == "Workaround available"
        assert content.rendered_html() == "Workaround available"
        assert content.rendered_for_prompt() == "Workaround available"
        assert content.rendered_for_prompt(text_format=TextFormat.MARKDOWN) == "Workaround available"
        assert content.rendered_for_prompt(text_format=TextFormat.HTML) == "Workaround available"
        assert str(content) == "Workaround available"

    @pytest.mark.asyncio(loop_scope="class")
    async def test_renders_as_its_label_in_a_template(self):
        """The async path a Jinja2 template's `format` filter takes reaches the same renderers."""
        labelled = RatingContent(level=2, label="Fully blocked")
        unlabelled = RatingContent(level=2)
        for text_format in (TextFormat.PLAIN, TextFormat.MARKDOWN, TextFormat.HTML):
            assert await labelled.rendered_for_template_async(text_format=text_format) == "Fully blocked"
            assert await unlabelled.rendered_for_template_async(text_format=text_format) == "2"

    def test_renders_html_with_the_label_escaped(self):
        assert RatingContent(level=0, label="<b>Minor</b> & cosmetic").rendered_html() == "&lt;b&gt;Minor&lt;/b&gt; &amp; cosmetic"

    def test_renders_as_its_level_when_the_label_is_empty(self):
        """An empty label names nothing, so the rating falls back to its level rather than rendering as nothing."""
        content = RatingContent(level=2, label="")
        assert content.rendered_plain() == "2"
        assert content.rendered_markdown() == "2"
        assert content.rendered_html() == "2"

    def test_rendered_json_writes_the_present_members_only(self):
        assert json.loads(RatingContent(level=0).rendered_json()) == {"level": 0}
        assert json.loads(RatingContent(level=2, position=1.8).rendered_json()) == {"level": 2, "position": 1.8}
        assert json.loads(RatingContent(level=1, label="Workaround available").rendered_json()) == {"level": 1, "label": "Workaround available"}
        assert json.loads(RatingContent(level=1, label="Workaround available", confidence=0.6).rendered_for_prompt(text_format=TextFormat.JSON)) == {
            "level": 1,
            "label": "Workaround available",
            "confidence": 0.6,
        }

    def test_rendered_json_keeps_the_pinned_member_order(self):
        """The label follows the level, as the standard's pinned definition orders them."""
        rendered = RatingContent(level=1, label="Workaround available", confidence=0.6).rendered_json()
        assert list(json.loads(rendered)) == ["level", "label", "confidence"]

    def test_smart_dump_writes_absent_members_null(self):
        assert RatingContent(level=1).smart_dump() == {"level": 1, "label": None, "confidence": None, "probabilities": None, "position": None}

    def test_smart_dump_writes_the_label(self):
        assert RatingContent(level=1, label="Workaround available").smart_dump() == {
            "level": 1,
            "label": "Workaround available",
            "confidence": None,
            "probabilities": None,
            "position": None,
        }

    def test_short_desc_names_the_level(self):
        assert RatingContent(level=2).short_desc == "a rating (level 2)"

    @pytest.mark.parametrize(
        "measures",
        [{"confidence": False}, {"confidence": "0.5"}, {"probabilities": {"0": True}}, {"position": True}, {"position": "1.5"}],
    )
    def test_refuses_a_measure_that_is_not_a_number(self, measures: dict[str, object]):
        with pytest.raises(ValidationError):
            RatingContent.model_validate({"level": 1, **measures})

    def test_reads_integer_measures_as_numbers(self):
        content = RatingContent.model_validate({"level": 1, "confidence": 1, "probabilities": {"0": 0, "1": 1}, "position": 1})
        assert content.position == 1.0
        assert content.probabilities == {"0": 0.0, "1": 1.0}
