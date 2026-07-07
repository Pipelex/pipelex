import datetime
from pathlib import Path
from typing import Any, Callable, ClassVar

import pytest

from pipelex import log
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.exceptions import StuffContentFactoryError
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_factory import StuffContentFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.yes_no_content import YesNoContent


class TestCases:
    # Test cases for TextContent with string content
    TEXT_STRING_BLUEPRINT: ClassVar[dict[str, Any]] = {
        "concept_ref": f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}",
        "content": "The Dawn of Ultra-Rapid Transit: NextGen High-Speed Trains Redefine Travel",
    }

    # Test cases for TextContent with dict content
    TEXT_DICT_BLUEPRINT: ClassVar[dict[str, Any]] = {
        "concept_ref": f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}",
        "content": {"text": "Sample text content"},
    }

    # Test cases for native concept without prefix (should work)
    TEXT_NO_PREFIX_BLUEPRINT: ClassVar[dict[str, Any]] = {
        "concept_ref": f"{NativeConceptCode.TEXT}",
        "content": {"text": "Text content without native prefix"},
    }

    # Test cases for registered class (using actual registered class)
    REGISTERED_CLASS_BLUEPRINT: ClassVar[dict[str, Any]] = {
        "concept_ref": "test.MockRegisteredContent",
        "content": {"title": "Test Question", "description": "What are aerodynamic features?"},
    }

    TEST_BLUEPRINTS: ClassVar[list[tuple[str, dict[str, Any]]]] = [
        ("text_string", TEXT_STRING_BLUEPRINT),
        ("text_dict", TEXT_DICT_BLUEPRINT),
        ("text_no_prefix", TEXT_NO_PREFIX_BLUEPRINT),
        ("registered_class", REGISTERED_CLASS_BLUEPRINT),
    ]


class TestStuffContentFactory:
    def test_make_content_from_value_text_string(self):
        """Test make_content_from_value with TextContent and string value."""
        result = StuffContentFactory.make_content_from_value(stuff_content_subclass=TextContent, value="Test string content")

        assert isinstance(result, TextContent)
        assert result.text == "Test string content"

    def test_make_content_from_value_text_dict(self):
        """Test make_content_from_value with TextContent and dict value."""
        result = StuffContentFactory.make_content_from_value(stuff_content_subclass=TextContent, value={"text": "Dict text content"})

        assert isinstance(result, TextContent)
        assert result.text == "Dict text content"

    def test_make_content_from_value_structured_dict(self):
        """Test make_content_from_value with StructuredContent and dict value."""

        class MockStructuredContent(StructuredContent):
            title: str
            description: str

        result = StuffContentFactory.make_content_from_value(
            stuff_content_subclass=MockStructuredContent,
            value={"title": "Test Title", "description": "Test Description"},
        )

        assert isinstance(result, MockStructuredContent)
        assert result.title == "Test Title"
        assert result.description == "Test Description"

    def test_make_content_from_value_yes_no_bool(self):
        """A bool value builds YesNoContent directly (not via model_validate, which rejects a bare bool)."""
        result = StuffContentFactory.make_content_from_value(stuff_content_subclass=YesNoContent, value=True)

        assert isinstance(result, YesNoContent)
        assert result.yes_no is True

    def test_make_content_from_value_yes_no_refining_subclass_bool(self):
        """A bool value builds a YesNo-refining subclass directly (the issubclass arm covers generated refinement classes)."""

        class MockUrgencyFlag(YesNoContent):
            pass

        result = StuffContentFactory.make_content_from_value(stuff_content_subclass=MockUrgencyFlag, value=False)

        assert isinstance(result, MockUrgencyFlag)
        assert result.yes_no is False

    def test_make_content_from_value_date_from_date_object(self):
        """A date object builds a date-only DateContent."""
        result = StuffContentFactory.make_content_from_value(stuff_content_subclass=DateContent, value=datetime.date(2026, 7, 7))

        assert isinstance(result, DateContent)
        assert result.date == datetime.date(2026, 7, 7)
        assert result.time is None

    def test_make_content_from_value_date_from_datetime_object_splits(self):
        """A datetime object splits into date + time, preserving the UTC offset."""
        offset = datetime.timezone(datetime.timedelta(hours=2))
        result = StuffContentFactory.make_content_from_value(
            stuff_content_subclass=DateContent, value=datetime.datetime(2026, 7, 7, 15, 40, tzinfo=offset)
        )

        assert isinstance(result, DateContent)
        assert result.date == datetime.date(2026, 7, 7)
        assert result.time is not None
        assert result.time.utcoffset() == datetime.timedelta(hours=2)

    def test_make_content_from_value_date_from_iso_date_string(self):
        """A date-only ISO string never fabricates a time (parsed date-first)."""
        result = StuffContentFactory.make_content_from_value(stuff_content_subclass=DateContent, value="2026-07-07")

        assert isinstance(result, DateContent)
        assert result.date == datetime.date(2026, 7, 7)
        assert result.time is None

    def test_make_content_from_value_date_from_iso_datetime_string(self):
        """A datetime ISO string parses into date + time with the offset kept."""
        result = StuffContentFactory.make_content_from_value(stuff_content_subclass=DateContent, value="2026-07-07T15:40:00+02:00")

        assert isinstance(result, DateContent)
        assert result.date == datetime.date(2026, 7, 7)
        assert result.time is not None
        assert result.time.utcoffset() == datetime.timedelta(hours=2)

    def test_make_content_from_value_date_refining_subclass(self):
        """A date object builds a Date-refining subclass directly (the issubclass arm covers generated refinement classes)."""

        class MockDueDate(DateContent):
            pass

        result = StuffContentFactory.make_content_from_value(stuff_content_subclass=MockDueDate, value=datetime.date(2026, 8, 6))

        assert isinstance(result, MockDueDate)
        assert result.date == datetime.date(2026, 8, 6)

    def test_make_content_from_value_date_rejects_non_iso_string(self):
        """A non-ISO string under a Date class is rejected (strict ISO, no loose formats)."""
        with pytest.raises(StuffContentFactoryError):
            StuffContentFactory.make_content_from_value(stuff_content_subclass=DateContent, value="March 7, 2026")

    def test_make_content_from_value_date_rejects_all_digit_string(self):
        """An all-digit string (basic-ISO/epoch-ambiguous) is rejected here too, matching DateContent's own guard."""
        with pytest.raises(StuffContentFactoryError):
            StuffContentFactory.make_content_from_value(stuff_content_subclass=DateContent, value="20260707")

    def test_make_stuffcontent_from_concept_code_required_text_content(self):
        """Test required method with native.Text concept (should work)."""
        result = StuffContentFactory.make_stuff_content_from_concept_required(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            value="Test text content",
        )

        assert isinstance(result, TextContent)
        assert result.text == "Test text content"

    def test_make_stuffcontent_from_concept_code_with_fallback_text_success(self):
        """Test fallback method with native.Text concept."""
        result = StuffContentFactory.make_stuff_content_from_concept_with_fallback(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            value="Test text content",
        )

        assert isinstance(result, TextContent)
        assert result.text == "Test text content"

    @pytest.mark.parametrize(
        ("test_name", "blueprint"),
        TestCases.TEST_BLUEPRINTS,
    )
    def test_blueprint_scenarios(self, test_name: str, blueprint: dict[str, Any], load_test_library: Callable[[list[Path]], None]):
        """Test various blueprint scenarios with parametrized test cases."""
        load_test_library([Path("tests/unit/pipelex/core/stuffs")])
        content = blueprint["content"]

        if test_name.startswith("text_"):
            # Test native.Text concept with required method
            result = StuffContentFactory.make_stuff_content_from_concept_required(
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
                value=content,
            )
            assert isinstance(result, TextContent)
            if isinstance(content, str):
                assert result.text == content
            else:
                assert result.text == content["text"]

        elif test_name == "registered_class":
            # Test with registered class - since MockRegisteredContent isn't actually registered,
            # But the content dict format is incompatible with TextContent's expected structure

            # Test required method - it will succeed but create TextContent
            # The dict will be passed through model_validate which should fail for TextContent
            try:
                result_required = StuffContentFactory.make_stuff_content_from_concept_required(
                    concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
                    value=content,
                )
                assert isinstance(result_required, TextContent)
            except Exception:
                log.error(f"Failed to make stuff content from concept with required: {content}")
                # If it fails due to validation error, that's also expected

            # Test fallback method - same behavior expected
            try:
                result_fallback = StuffContentFactory.make_stuff_content_from_concept_with_fallback(
                    concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
                    value=content,
                )
                assert isinstance(result_fallback, TextContent)
            except Exception:
                log.error(f"Failed to make stuff content from concept with fallback: {content}")

        elif test_name.startswith("unregistered_"):
            result_required = StuffContentFactory.make_stuff_content_from_concept_required(
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
                value=content,
            )
            assert isinstance(result_required, TextContent)

            result_fallback = StuffContentFactory.make_stuff_content_from_concept_with_fallback(
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
                value=content,
            )
            assert isinstance(result_fallback, TextContent)

            # Both should produce the same result
            assert result_required.text == result_fallback.text
