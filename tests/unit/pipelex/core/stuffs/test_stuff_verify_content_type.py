from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, create_model

from pipelex.core.stuffs.exceptions import StuffContentTypeError, StuffContentValidationError
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.text_content import TextContent

# A key of the run's own data, which no message carries.
_PAYLOAD_KEY = "confidential-patient-diagnosis"


class _Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int


# Two classes of one name, as a domain-qualified dynamic class and its bare twin are: the content is converted by validation.
_LooseLedger = create_model("Ledger", __base__=StructuredContent, entries=(dict[str, Any], ...), owner=(dict[str, Any], {"score": 0}))
_Ledger = create_model("Ledger", __base__=StructuredContent, entries=(dict[str, _Entry], ...), owner=(_Entry, _Entry(score=0)))


def _loose_ledger(**fields: Any) -> StructuredContent:
    return _LooseLedger.model_validate(fields)


class TestVerifyContentType:
    def test_verify_content_type_with_list_content_generic_raises_helpful_error(self):
        """Test that passing ListContent[Something] raises a helpful error suggesting get_stuff_as_list().

        This is the bug scenario: content is plain ListContent (like what WorkingMemory stores)
        but the user expects ListContent[Something].
        """
        # This is how content is typically stored in WorkingMemory - as plain ListContent (untyped)
        items = [TextContent(text="hello"), TextContent(text="world")]
        content = ListContent(items=items)  # type: ignore[var-annotated]

        with pytest.raises(StuffContentTypeError) as exc_info:
            Stuff.verify_content_type(content=content, content_type=ListContent[TextContent])

        error_message = str(exc_info.value)
        assert "Cannot use ListContent[TextContent]" in error_message
        assert "get_stuff_as_list" in error_message

    def test_verify_content_type_with_plain_list_content_works(self):
        """Plain ListContent (without generic parameter) should work fine."""
        content = ListContent[TextContent](items=[TextContent(text="hello")])

        result = Stuff.verify_content_type(content=content, content_type=ListContent)  # pyright: ignore[reportUnknownVariableType]

        assert isinstance(result, ListContent)

    def test_verify_content_type_with_matching_type_works(self):
        """Direct type match should work."""
        content = TextContent(text="hello")

        result = Stuff.verify_content_type(content=content, content_type=TextContent)

        assert isinstance(result, TextContent)
        assert result.text == "hello"

    def test_verify_content_type_with_mismatched_type_raises_error(self):
        """Mismatched types should raise StuffContentTypeError."""
        content = TextContent(text="hello")

        with pytest.raises(StuffContentTypeError) as exc_info:
            Stuff.verify_content_type(content=content, content_type=ListContent)

        error_message = str(exc_info.value)
        assert "TextContent" in error_message
        assert "ListContent" in error_message

    @pytest.mark.parametrize(
        ("topic", "content", "expected_error"),
        [
            (
                "an invalid value under a key of the content's own",
                _loose_ledger(entries={_PAYLOAD_KEY: {"score": "high"}}),
                "entries.<key>.score: Input should be a valid integer, unable to parse string as an integer",
            ),
            (
                "an extra key under a key of the content's own",
                _loose_ledger(entries={_PAYLOAD_KEY: {"score": 1, _PAYLOAD_KEY: 2}}),
                "entries.<key>.<key>: Extra inputs are not permitted",
            ),
            (
                "an extra field of a nested model",
                _loose_ledger(entries={}, owner={"score": 1, _PAYLOAD_KEY: 2}),
                "owner.<key>: Extra inputs are not permitted",
            ),
        ],
    )
    def test_a_refused_conversion_names_the_schema_s_fields_never_the_content_s_keys(
        self, topic: str, content: StructuredContent, expected_error: str
    ) -> None:
        """A location quotes the keys a dict of the content holds, which are the run's data: only the schema's names are written."""
        with pytest.raises(StuffContentValidationError) as exc_info:
            Stuff.verify_content_type(content=content, content_type=_Ledger)

        assert exc_info.value.validation_error == expected_error, topic
        assert _PAYLOAD_KEY not in str(exc_info.value), topic
