import pytest

from pipelex.tools.misc.exceptions import DeclaredMediaTypeError
from pipelex.tools.misc.filetype_utils import declared_media_type


class TestDeclaredMediaType:
    @pytest.mark.parametrize(
        ("topic", "media_type", "expected"),
        [
            ("bare type", "image/png", "image/png"),
            ("header with a charset", "text/plain;charset=utf-8", "text/plain"),
            ("parameters with spaces", "text/plain ; charset=utf-8", "text/plain"),
            ("a parameter without a value", "text/plain;flowed", "text/plain"),
            ("a parameter holding a space", "application/pdf;name=annual report.pdf", "application/pdf"),
            ("mixed case", "Image/PNG", "image/png"),
            ("structured suffix", "application/vnd.api+json", "application/vnd.api+json"),
            ("surrounding whitespace", "  application/pdf\n", "application/pdf"),
            ("nothing declared", None, None),
            ("empty", "", None),
            ("blank", "   ", None),
        ],
    )
    def test_a_declared_type_is_reduced_to_its_bare_type(self, topic: str, media_type: str | None, expected: str | None) -> None:
        assert declared_media_type(media_type=media_type) == expected, topic

    @pytest.mark.parametrize(
        ("topic", "media_type"),
        [
            ("comma in the type", "image/png,text/plain"),
            ("comma in the parameters", "application/pdf;,text/plain"),
            ("missing subtype", "image"),
            ("empty subtype", "image/"),
            ("empty type", "/png"),
            ("space inside a token", "image/p ng"),
            ("two slashes", "image/png/x"),
            ("control character", "image/png\x00"),
            ("control character in the parameters", "text/plain;charset=utf-8\x07"),
            ("parameters only", ";charset=utf-8"),
            ("letter outside ASCII", "imagé/png"),
        ],
    )
    def test_a_declared_type_that_is_not_one_media_type_is_refused(self, topic: str, media_type: str) -> None:
        with pytest.raises(DeclaredMediaTypeError) as exc_info:
            declared_media_type(media_type=media_type)
        assert media_type not in str(exc_info.value), topic
