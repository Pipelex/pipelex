import pytest

from pipelex.tools.uri.data_url import ParsedDataUrl, is_data_url, parse_base64_data_url, parse_data_url
from pipelex.tools.uri.data_url_exceptions import DataUrlError


class TestDataUrl:
    @pytest.mark.parametrize(
        ("topic", "uri", "expected"),
        [
            ("plain base64", "data:image/png;base64,aGVsbG8=", ParsedDataUrl(media_type="image/png", is_base64=True, payload="aGVsbG8=")),
            (
                "header with a charset",
                "data:text/plain;charset=utf-8;base64,aGVsbG8=",
                ParsedDataUrl(media_type="text/plain;charset=utf-8", is_base64=True, payload="aGVsbG8="),
            ),
            (
                "comma inside what looks like the header",
                "data:application/pdf;,text/plain;base64,aGVsbG8=",
                ParsedDataUrl(media_type="application/pdf;", is_base64=False, payload="text/plain;base64,aGVsbG8="),
            ),
            (
                "uppercase scheme and marker",
                "DATA:Image/PNG;BASE64,aGVsbG8=",
                ParsedDataUrl(media_type="Image/PNG", is_base64=True, payload="aGVsbG8="),
            ),
            (
                "spaces around the marker",
                "data: image/png ; base64 ,aGVsbG8=",
                ParsedDataUrl(media_type="image/png", is_base64=True, payload="aGVsbG8="),
            ),
            ("empty header, base64", "data:;base64,aGVsbG8=", ParsedDataUrl(media_type="", is_base64=True, payload="aGVsbG8=")),
            ("empty header", "data:,hello", ParsedDataUrl(media_type="", is_base64=False, payload="hello")),
            ("not base64", "data:text/plain,hello", ParsedDataUrl(media_type="text/plain", is_base64=False, payload="hello")),
            (
                "marker not at the end",
                "data:text/plain;base64;charset=utf-8,aGVsbG8=",
                ParsedDataUrl(media_type="text/plain;base64;charset=utf-8", is_base64=False, payload="aGVsbG8="),
            ),
            ("subtype ending in base64", "data:text/xbase64,aGVsbG8=", ParsedDataUrl(media_type="text/xbase64", is_base64=False, payload="aGVsbG8=")),
            ("empty payload", "data:text/plain;base64,", ParsedDataUrl(media_type="text/plain", is_base64=True, payload="")),
        ],
    )
    def test_parse_data_url_reads_the_header_up_to_the_first_comma(self, topic: str, uri: str, expected: ParsedDataUrl) -> None:
        """The header ends at the first comma, and the URL is base64 only when that header ends with the marker."""
        assert parse_data_url(uri=uri) == expected, topic

    @pytest.mark.parametrize(
        ("topic", "uri"),
        [
            ("no comma", "data:image/png;base64aGVsbG8="),
            ("not a data URL", "https://example.com/photo.png"),
            ("scheme with a leading space", " data:image/png;base64,aGVsbG8="),
            ("empty string", ""),
        ],
    )
    def test_parse_data_url_refuses_a_value_that_is_not_one(self, topic: str, uri: str) -> None:
        with pytest.raises(DataUrlError) as exc_info:
            parse_data_url(uri=uri)
        assert "image/png" not in str(exc_info.value), topic

    def test_parse_base64_data_url_refuses_a_url_that_is_not_base64(self) -> None:
        """The refusal names the form that is read and never the header it was given."""
        with pytest.raises(DataUrlError) as exc_info:
            parse_base64_data_url(uri="data:application/pdf;,text/plain;base64,aGVsbG8=")
        message = str(exc_info.value)
        assert "data:<type>/<subtype>[;parameters];base64,<payload>" in message
        assert "application/pdf" not in message
        assert "text/plain" not in message

    def test_parse_base64_data_url_returns_a_base64_url(self) -> None:
        assert parse_base64_data_url(uri="data:text/plain;base64,aGVsbG8=") == ParsedDataUrl(
            media_type="text/plain", is_base64=True, payload="aGVsbG8="
        )

    @pytest.mark.parametrize(
        ("uri", "expected"),
        [
            ("data:image/png;base64,aGVsbG8=", True),
            ("Data:text/plain,hello", True),
            ("data:", True),
            ("dat", False),
            ("https://example.com/data:x", False),
            ("pipelex-storage://u/data:x", False),
        ],
    )
    def test_is_data_url_matches_the_scheme_in_any_ascii_case(self, uri: str, expected: bool) -> None:
        assert is_data_url(uri=uri) is expected
