import json

import pytest
from pydantic import ValidationError

from pipelex.core.stuffs.rating_content import RatingContent


class TestRatingContent:
    """`Rating` requires its level index; `confidence`, `probabilities` and `position` are optional measures."""

    def test_requires_the_level(self):
        with pytest.raises(ValidationError, match="level"):
            RatingContent.model_validate({})

    def test_measures_are_absent_by_default(self):
        content = RatingContent(level=2)
        assert content.confidence is None
        assert content.probabilities is None
        assert content.position is None

    def test_accepts_every_measure(self):
        content = RatingContent(level=1, confidence=0.6, probabilities={"0": 0.1, "1": 0.6, "2": 0.3}, position=1.2)
        assert content.level == 1
        assert content.position == 1.2
        assert content.probabilities == {"0": 0.1, "1": 0.6, "2": 0.3}

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

    def test_renders_as_its_level(self):
        content = RatingContent(level=3, position=2.7)
        assert content.rendered_plain() == "3"
        assert content.rendered_markdown() == "3"
        assert content.rendered_html() == "3"
        assert content.rendered_for_prompt() == "3"

    def test_rendered_json_writes_the_present_members_only(self):
        assert json.loads(RatingContent(level=0).rendered_json()) == {"level": 0}
        assert json.loads(RatingContent(level=2, position=1.8).rendered_json()) == {"level": 2, "position": 1.8}

    def test_smart_dump_writes_absent_members_null(self):
        assert RatingContent(level=1).smart_dump() == {"level": 1, "confidence": None, "probabilities": None, "position": None}

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
