import pytest

from pipelex.core.stuffs.exceptions import StuffContentTypeError
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.text_content import TextContent


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
