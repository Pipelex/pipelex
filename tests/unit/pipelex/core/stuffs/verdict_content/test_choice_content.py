import json

import pytest
from pydantic import ValidationError

from pipelex.core.stuffs.choice_content import ChoiceContent


class TestChoiceContent:
    """`Choice` requires its option key; `confidence` and `probabilities` are optional measures within [0, 1]."""

    def test_requires_the_choice(self):
        with pytest.raises(ValidationError, match="choice"):
            ChoiceContent.model_validate({})

    def test_measures_are_absent_by_default(self):
        content = ChoiceContent(choice="billing")
        assert content.confidence is None
        assert content.probabilities is None

    def test_accepts_every_measure(self):
        content = ChoiceContent(choice="billing", confidence=0.7, probabilities={"billing": 0.8, "technical": 0.2})
        assert content.choice == "billing"
        assert content.confidence == 0.7
        assert content.probabilities == {"billing": 0.8, "technical": 0.2}

    @pytest.mark.parametrize("confidence", [-0.1, 1.1])
    def test_refuses_a_confidence_outside_the_unit_interval(self, confidence: float):
        with pytest.raises(ValidationError, match="confidence"):
            ChoiceContent(choice="billing", confidence=confidence)

    @pytest.mark.parametrize("probability", [-0.1, 1.1])
    def test_refuses_a_probability_outside_the_unit_interval(self, probability: float):
        with pytest.raises(ValidationError, match="probabilities"):
            ChoiceContent(choice="billing", probabilities={"billing": probability})

    def test_renders_as_its_key(self):
        content = ChoiceContent(choice="billing", confidence=0.7)
        assert content.rendered_plain() == "billing"
        assert content.rendered_markdown() == "billing"
        assert content.rendered_html() == "billing"
        assert content.rendered_for_prompt() == "billing"

    def test_html_rendering_escapes_the_key(self):
        assert ChoiceContent(choice="<b>").rendered_html() == "&lt;b&gt;"

    def test_rendered_json_writes_the_present_members_only(self):
        assert json.loads(ChoiceContent(choice="billing").rendered_json()) == {"choice": "billing"}
        assert json.loads(ChoiceContent(choice="billing", probabilities={"billing": 1.0}).rendered_json()) == {
            "choice": "billing",
            "probabilities": {"billing": 1.0},
        }

    def test_smart_dump_writes_absent_members_null(self):
        assert ChoiceContent(choice="billing").smart_dump() == {"choice": "billing", "confidence": None, "probabilities": None}

    def test_short_desc_names_the_choice(self):
        assert ChoiceContent(choice="billing").short_desc == "a choice (billing)"
