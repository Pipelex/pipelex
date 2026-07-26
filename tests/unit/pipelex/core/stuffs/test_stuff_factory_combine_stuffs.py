from pathlib import Path
from typing import TYPE_CHECKING, Callable

import pytest
from pydantic import Field

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.stuffs.exceptions import StuffFactoryError
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.method_hub import get_concept_library
from pipelex.system.registries.class_registry_utils import ClassRegistryUtils

if TYPE_CHECKING:
    from pipelex.core.stuffs.stuff_content import StuffContent


class SentimentAndWordCount(StructuredContent):
    """A structured content combining sentiment and word count results."""

    sentiment_result: TextContent = Field(description="Sentiment analysis result")
    word_count_result: TextContent = Field(description="Word count result")


class SingleFieldContent(StructuredContent):
    """A structured content with a single field."""

    summary: TextContent = Field(description="Summary text")


DOMAIN_CODE = "test_combine"


@pytest.fixture(scope="class")
def setup_combine_concepts(load_test_library: Callable[[list[Path]], None]):
    """Register structured content classes and create concepts for combine_stuffs tests."""
    load_test_library([Path(__file__).parent])
    ClassRegistryUtils.register_classes_in_file(
        file_path=Path(__file__).parent / "test_stuff_factory_combine_stuffs.py",
        base_class=StructuredContent,
        is_include_imported=False,
    )

    concept_library = get_concept_library()

    concept_sentiment_and_word_count = ConceptFactory.make(
        concept_code="SentimentAndWordCount",
        domain_code=DOMAIN_CODE,
        description="Combined sentiment and word count",
        structure_class_name="SentimentAndWordCount",
    )
    concept_library.add_new_concept(concept=concept_sentiment_and_word_count)

    concept_single_field = ConceptFactory.make(
        concept_code="SingleFieldContent",
        domain_code=DOMAIN_CODE,
        description="Single field content",
        structure_class_name="SingleFieldContent",
    )
    concept_library.add_new_concept(concept=concept_single_field)

    yield

    concept_library.remove_concepts_by_concept_refs(
        concept_refs=[
            f"{DOMAIN_CODE}.SentimentAndWordCount",
            f"{DOMAIN_CODE}.SingleFieldContent",
        ]
    )


@pytest.mark.usefixtures("setup_combine_concepts")
class TestStuffFactoryCombineStuffs:
    """Tests for StuffFactory.combine_stuffs method."""

    def test_combine_two_text_contents(self):
        """Test combining two TextContent fields into a StructuredContent stuff."""
        concept = get_concept_library().get_required_concept(concept_ref=f"{DOMAIN_CODE}.SentimentAndWordCount")

        stuff_contents: dict[str, StuffContent] = {
            "sentiment_result": TextContent(text="positive"),
            "word_count_result": TextContent(text="42"),
        }

        result = StuffFactory.combine_stuffs(
            concept=concept,
            stuff_contents=stuff_contents,
            name="combined_analysis",
        )

        assert result.stuff_name == "combined_analysis"
        assert isinstance(result.content, SentimentAndWordCount)
        assert result.content.sentiment_result.text == "positive"
        assert result.content.word_count_result.text == "42"
        assert result.concept.code == "SentimentAndWordCount"
        assert result.concept.domain_code == DOMAIN_CODE

    def test_combine_single_field(self):
        """Test combining a single TextContent field."""
        concept = get_concept_library().get_required_concept(concept_ref=f"{DOMAIN_CODE}.SingleFieldContent")

        stuff_contents: dict[str, StuffContent] = {
            "summary": TextContent(text="This is a summary"),
        }

        result = StuffFactory.combine_stuffs(
            concept=concept,
            stuff_contents=stuff_contents,
            name="single_field_stuff",
        )

        assert isinstance(result.content, SingleFieldContent)
        assert result.content.summary.text == "This is a summary"

    def test_combine_without_name_auto_generates(self):
        """Test that omitting the name parameter still produces a valid Stuff."""
        concept = get_concept_library().get_required_concept(concept_ref=f"{DOMAIN_CODE}.SingleFieldContent")

        stuff_contents: dict[str, StuffContent] = {
            "summary": TextContent(text="auto-named"),
        }

        result = StuffFactory.combine_stuffs(
            concept=concept,
            stuff_contents=stuff_contents,
        )

        assert result.stuff_name is not None
        assert len(result.stuff_name) > 0
        assert isinstance(result.content, SingleFieldContent)

    def test_combine_with_missing_field_raises_error(self):
        """Test that missing a required field raises StuffFactoryError."""
        concept = get_concept_library().get_required_concept(concept_ref=f"{DOMAIN_CODE}.SentimentAndWordCount")

        stuff_contents: dict[str, StuffContent] = {
            "sentiment_result": TextContent(text="positive"),
            # missing word_count_result
        }

        with pytest.raises(StuffFactoryError, match="Error combining stuffs"):
            StuffFactory.combine_stuffs(
                concept=concept,
                stuff_contents=stuff_contents,
                name="incomplete",
            )

    def test_combine_with_wrong_content_type_raises_error(self):
        """Test that passing wrong content type for a field raises StuffFactoryError."""
        concept = get_concept_library().get_required_concept(concept_ref=f"{DOMAIN_CODE}.SentimentAndWordCount")

        stuff_contents: dict[str, StuffContent] = {
            "sentiment_result": TextContent(text="positive"),
            "word_count_result": "not_a_stuff_content",  # type: ignore[dict-item]
        }

        with pytest.raises(StuffFactoryError, match="Error combining stuffs"):
            StuffFactory.combine_stuffs(
                concept=concept,
                stuff_contents=stuff_contents,
                name="wrong_type",
            )
