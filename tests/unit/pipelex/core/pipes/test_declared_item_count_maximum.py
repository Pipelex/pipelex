import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.dry_mock import build_mock_objects, dry_img_gen_image_contents
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.declared_item_count import ensure_declared_item_count_allowed, ensure_mock_item_count_allowed, get_max_declared_item_count
from pipelex.core.pipes.declared_item_count_scope import scoped_max_declared_item_count, validate_max_declared_item_count
from pipelex.core.pipes.exceptions import DeclaredItemCountLimitError
from pipelex.core.pipes.inputs.input_stuff_specs import TypedNamedStuffSpec
from pipelex.core.stuffs.text_content import TextContent
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.system.exceptions import RunParameterError


def _text_list_spec(*, count: int) -> TypedNamedStuffSpec:
    return TypedNamedStuffSpec(
        variable_name="items",
        concept=ConceptFactory.make(
            concept_code=NativeConceptCode.TEXT, domain_code="native", description="A text", structure_class_name="TextContent"
        ),
        multiplicity=count,
        structure_class=TextContent,
    )


class TestDeclaredItemCountMaximum:
    def test_outside_every_scope_the_maximum_is_the_deployments(self) -> None:
        assert get_max_declared_item_count() == 1000

    def test_a_scope_states_the_maximum_and_none_keeps_the_one_in_force(self) -> None:
        with scoped_max_declared_item_count(maximum=5000):
            assert get_max_declared_item_count() == 5000
            with scoped_max_declared_item_count(maximum=None):
                assert get_max_declared_item_count() == 5000
            with scoped_max_declared_item_count(maximum=3):
                assert get_max_declared_item_count() == 3
            assert get_max_declared_item_count() == 5000
        assert get_max_declared_item_count() == 1000

    @pytest.mark.parametrize("maximum", [0, -5, 1_000_000_000, True])
    def test_a_maximum_no_runtime_may_set_is_refused(self, maximum: int) -> None:
        with pytest.raises(RunParameterError, match="maximum declared item count"):
            validate_max_declared_item_count(value=maximum)
        with pytest.raises(RunParameterError), scoped_max_declared_item_count(maximum=maximum):
            pass

    def test_the_refusal_names_the_slot_the_count_and_the_maximum(self) -> None:
        ensure_declared_item_count_allowed(count=1000, slot="the output of the pipe 'make_ideas'", maximum=1000)
        with pytest.raises(DeclaredItemCountLimitError) as exc_info:
            ensure_declared_item_count_allowed(count=1001, slot="the output of the pipe 'make_ideas'", maximum=1000)

        refusal = exc_info.value
        assert refusal.error_code == PipelexErrorCode.DEPLOYMENT_DECLARED_COUNT_OVER_LIMIT
        assert refusal.problem_params() == {"slot": "the output of the pipe 'make_ideas'", "count": 1001, "limit": 1000}
        assert "at most 1000 items for one slot" in str(refusal)

    def test_the_mock_builders_refuse_past_the_maximum_and_never_shorten(self, mocker: MockerFixture) -> None:
        """The dry run's second line: each builder refuses a count past the maximum in force before building anything."""
        with scoped_max_declared_item_count(maximum=2):
            ensure_mock_item_count_allowed(count=2, slot="a slot")
            assert len(build_mock_objects(TextContent, count=2)) == 2
            mock_stuff = WorkingMemoryFactory.make_mock_stuff(_text_list_spec(count=2))
            assert len(mock_stuff.as_list_of_fixed_content_type(TextContent).items) == 2

            with pytest.raises(DeclaredItemCountLimitError, match="mock 'TextContent' objects"):
                build_mock_objects(TextContent, count=3)
            with pytest.raises(DeclaredItemCountLimitError, match="the mock input 'items'"):
                WorkingMemoryFactory.make_mock_stuff(_text_list_spec(count=3))
            with pytest.raises(DeclaredItemCountLimitError, match="mock images"):
                dry_img_gen_image_contents(mocker.MagicMock(nb_images=3))
