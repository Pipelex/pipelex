from typing import Callable, Literal

import pytest
from pydantic import Field

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.interpreter_hub import get_native_concept
from pipelex.pipe_operators.compose.construct_blueprint import ConstructBlueprint
from pipelex.pipe_operators.compose.exceptions import StructuredContentComposerValidationError
from pipelex.pipe_operators.compose.structured_content_composer import StructuredContentComposer
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle

_TEMPLATING_STYLE = TemplatingStyle(tag_style=TagStyle.XML)


class SourceWithOptionalNote(StructuredContent):
    """A source whose note may hold nothing."""

    note: str | None = Field(default=None, description="An optional note")


class TargetWithPresenceVariants(StructuredContent):
    """A target fed the same source field three ways: defaulted, may hold nothing, required."""

    defaulted_note: str = Field(default="fallback", description="A defaulted note")
    optional_note: str | None = Field(default=None, description="An optional note")


class TargetWithRequiredNote(StructuredContent):
    """A target whose note is required."""

    required_note: str = Field(description="A required note")


class TargetWithNullableNotes(StructuredContent):
    """A Python-declared target whose notes admit `None`, one required and one defaulted to a value."""

    required_nullable_note: str | None = Field(description="A required note that admits None")
    defaulted_nullable_note: str | None = Field(default="fallback", description="A defaulted note that admits None")


class TargetWithNullableLiteral(StructuredContent):
    """A Python-declared target whose note is a `Literal` listing `None`, defaulted to a value."""

    literal_note: Literal["fallback", None] = Field(default="fallback", description="A note whose Literal admits None")  # ruff: ignore[redundant-none-literal] — a Literal listing None is the test subject


@pytest.mark.asyncio(loop_scope="class")
class TestStructuredContentComposerSourceHoldingNothing:
    """A path reaching a field that holds nothing feeds the target field `None`, unless it refuses `None` but has a default.

    A generated defaulted field refuses `None`, so nulling it would fail the composition; left unset, it takes its
    default. A field whose annotation admits `None` keeps it, required or defaulted, and a required one refusing
    it is refused.
    """

    @pytest.fixture
    def working_memory_with_empty_note(self, load_empty_library: Callable[[], None]) -> WorkingMemory:
        load_empty_library()
        return WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=SourceWithOptionalNote(),
                name="source",
            ),
        )

    async def test_a_defaulted_target_takes_its_default_and_an_optional_one_holds_nothing(self, working_memory_with_empty_note: WorkingMemory):
        blueprint = ConstructBlueprint.make_from_raw({"defaulted_note": {"from": "source.note"}, "optional_note": {"from": "source.note"}})

        composer = StructuredContentComposer(
            templating_style=_TEMPLATING_STYLE,
            construct_blueprint=blueprint,
            working_memory=working_memory_with_empty_note,
            output_class=TargetWithPresenceVariants,
        )
        result = await composer.compose()

        assert isinstance(result, TargetWithPresenceVariants)
        assert result.defaulted_note == "fallback"
        assert result.optional_note is None

    async def test_a_required_target_is_refused(self, working_memory_with_empty_note: WorkingMemory):
        blueprint = ConstructBlueprint.make_from_raw({"required_note": {"from": "source.note"}})

        composer = StructuredContentComposer(
            templating_style=_TEMPLATING_STYLE,
            construct_blueprint=blueprint,
            working_memory=working_memory_with_empty_note,
            output_class=TargetWithRequiredNote,
        )
        with pytest.raises(StructuredContentComposerValidationError, match="required_note"):
            await composer.compose()

    async def test_a_target_that_admits_none_keeps_it(self, working_memory_with_empty_note: WorkingMemory):
        blueprint = ConstructBlueprint.make_from_raw(
            {"required_nullable_note": {"from": "source.note"}, "defaulted_nullable_note": {"from": "source.note"}}
        )

        composer = StructuredContentComposer(
            templating_style=_TEMPLATING_STYLE,
            construct_blueprint=blueprint,
            working_memory=working_memory_with_empty_note,
            output_class=TargetWithNullableNotes,
        )
        result = await composer.compose()

        assert isinstance(result, TargetWithNullableNotes)
        assert result.required_nullable_note is None
        assert result.defaulted_nullable_note is None

    async def test_a_literal_target_listing_none_keeps_it(self, working_memory_with_empty_note: WorkingMemory):
        blueprint = ConstructBlueprint.make_from_raw({"literal_note": {"from": "source.note"}})

        composer = StructuredContentComposer(
            templating_style=_TEMPLATING_STYLE,
            construct_blueprint=blueprint,
            working_memory=working_memory_with_empty_note,
            output_class=TargetWithNullableLiteral,
        )
        result = await composer.compose()

        assert isinstance(result, TargetWithNullableLiteral)
        assert result.literal_note is None
