from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.choice_content import ChoiceContent
from pipelex.core.stuffs.rating_content import RatingContent
from pipelex.core.stuffs.stuff_factory import StuffFactory


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
