import mimetypes

import pytest
from pytest_mock import MockerFixture

from pipelex.tools.misc.filetype_utils import mime_type_of_file_name

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


class TestMimeTypeOfFileName:
    @pytest.mark.parametrize(
        ("file_name", "expected"),
        [
            ("report.docx", _DOCX),
            ("budget.XLSX", _XLSX),
            ("org/run/assets/bundle/abc/deck.pptx", _PPTX),
            ("summary.html", "text/html"),
            ("invoice.pdf", "application/pdf"),
            ("data.json", "application/json"),
            ("archive.unknown-extension", None),
            ("no-extension", None),
        ],
    )
    def test_the_type_follows_the_extension(self, file_name: str, expected: str | None) -> None:
        assert mime_type_of_file_name(file_name=file_name) == expected

    @pytest.mark.parametrize(
        ("file_name", "expected"),
        [
            ("notes.md", "text/markdown"),
            ("org/assets/README.MD", "text/markdown"),
            ("notes.markdown", "text/markdown"),
            ("config.yaml", "application/yaml"),
            ("config.yml", "application/yaml"),
            ("minutes.odt", "application/vnd.oasis.opendocument.text"),
            ("budget.ods", "application/vnd.oasis.opendocument.spreadsheet"),
            ("deck.odp", "application/vnd.oasis.opendocument.presentation"),
        ],
    )
    def test_a_type_only_a_later_python_knows_is_known_on_every_python(self, file_name: str, expected: str) -> None:
        """Python 3.11's table has no Markdown, and only 3.14's has YAML and OpenDocument, yet every Python answers alike.

        The hosted platform types an upload from its name with this function on its own Python, so a runtime on another
        one must give the same answer. The suite runs on each supported Python, which is what proves it.
        """
        assert mime_type_of_file_name(file_name=file_name) == expected

    @pytest.mark.parametrize(("file_name", "expected"), [("report.docx", _DOCX), ("budget.xlsx", _XLSX), ("deck.pptx", _PPTX)])
    def test_the_office_types_never_depend_on_the_hosts_mimetypes_table(self, mocker: MockerFixture, file_name: str, expected: str) -> None:
        """A host whose `mime.types` knows no office type, as a slim server image's does not, still gets them."""
        mocker.patch.object(mimetypes, "guess_type", return_value=(None, None))
        mocker.patch.dict(mimetypes.types_map, {}, clear=True)

        assert mime_type_of_file_name(file_name=file_name) == expected
