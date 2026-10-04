import pytest

from pipelex.tools.misc.filetype_utils import UNKNOWN_FILE_TYPE, mime_type_to_extension


class TestMimeTypeToExtension:
    @pytest.mark.parametrize(
        ("mime_type", "expected_extension"),
        [
            # Every supported Python answers these the same way, whatever its own MIME table holds
            ("text/markdown", "md"),
            ("text/markdown; charset=utf-8", "md"),
            ("TEXT/Markdown", "md"),
            ("text/plain", "txt"),
            ("text/csv", "csv"),
            ("text/html", "html"),
            ("application/pdf", "pdf"),
            ("image/jpeg", "jpeg"),
            ("", UNKNOWN_FILE_TYPE),
        ],
    )
    def test_extension_for_mime_type(self, mime_type: str, expected_extension: str) -> None:
        assert mime_type_to_extension(mime_type) == expected_extension
