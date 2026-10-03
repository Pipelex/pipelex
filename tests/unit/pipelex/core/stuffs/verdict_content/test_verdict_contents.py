import json

import pytest
from pydantic import ValidationError

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.choice_content import ChoiceContent
from pipelex.core.stuffs.rating_content import RatingContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
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


class TestVerdictAccessors:
    """A Python caller reads a verdict back through typed accessors, as it reads a `YesNo`."""

    def test_stuff_and_memory_accessors_narrow_a_choice(self):
        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.CHOICE),
            content=ChoiceContent(choice="billing"),
            name="team",
        )
        assert stuff.is_choice
        assert not stuff.is_rating
        assert stuff.as_choice.choice == "billing"
        memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)
        assert memory.get_stuff_as_choice("team").choice == "billing"
        assert memory.main_stuff_as_choice.choice == "billing"

    def test_stuff_and_memory_accessors_narrow_a_rating(self):
        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.RATING),
            content=RatingContent(level=2),
            name="grade",
        )
        assert stuff.is_rating
        assert not stuff.is_choice
        assert stuff.as_rating.level == 2
        memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)
        assert memory.get_stuff_as_rating("grade").level == 2
        assert memory.main_stuff_as_rating.level == 2
