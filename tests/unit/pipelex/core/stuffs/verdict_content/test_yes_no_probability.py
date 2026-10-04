import json

import pytest
from pydantic import ValidationError

from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.tools.templating.text_format import TextFormat


class TestYesNoProbability:
    """`YesNo` gains an optional `probability`: absent unless the producer reports one, and always within [0, 1]."""

    def test_probability_is_absent_by_default(self):
        assert YesNoContent(yes_no=True).probability is None

    @pytest.mark.parametrize("probability", [0.0, 0.42, 1.0])
    def test_accepts_a_probability_within_the_unit_interval(self, probability: float):
        assert YesNoContent(yes_no=True, probability=probability).probability == probability

    @pytest.mark.parametrize("probability", [-0.01, 1.01, 1.5])
    def test_refuses_a_probability_outside_the_unit_interval(self, probability: float):
        with pytest.raises(ValidationError, match="probability"):
            YesNoContent(yes_no=True, probability=probability)

    def test_rendered_json_carries_a_reported_probability(self):
        assert json.loads(YesNoContent(yes_no=False, probability=0.12).rendered_json()) == {"yes_no": False, "probability": 0.12}

    def test_rendered_json_leaves_an_absent_probability_out(self):
        assert json.loads(YesNoContent(yes_no=True).rendered_json()) == {"yes_no": True}

    def test_renders_as_the_verdict_whatever_the_probability(self):
        content = YesNoContent(yes_no=True, probability=0.83)
        assert content.rendered_plain() == "yes"
        assert content.rendered_for_prompt(text_format=TextFormat.MARKDOWN) == "yes"
        assert content.rendered_html() == "yes"

    def test_smart_dump_writes_an_absent_probability_null(self):
        assert YesNoContent(yes_no=True).smart_dump() == {"yes_no": True, "probability": None}

    @pytest.mark.parametrize("probability", [True, False, "0.9"])
    def test_refuses_a_probability_that_is_not_a_number(self, probability: object):
        # A stray `true` coerced to 1.0 would read as a confident yes.
        with pytest.raises(ValidationError):
            YesNoContent.model_validate({"yes_no": True, "probability": probability})

    def test_reads_an_integer_probability_as_a_number(self):
        assert YesNoContent.model_validate({"yes_no": True, "probability": 1}).probability == 1.0
