"""The format-key vocabulary and the non-raising identification helpers in `filetype_utils`.

A format key is what every format check compares: a file's key, derived from its MIME type, against
the keys a model declares it reads. Every image type is the `image` family; any other identified
type is its extension; no type, or the generic octet-stream, has no key.
"""

import base64
from pathlib import Path

import pytest

from pipelex.tools.misc.filetype_utils import (
    FILE_HEAD_NB_BYTES,
    describe_file_format,
    describe_format_key,
    describe_format_keys,
    format_key_from_mime_type,
    guess_file_type_from_bytes,
    identify_mime_type,
)

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

DOCUMENTS_DIR = Path("tests/data/documents")
IMAGES_DIR = Path("tests/data/images")


class TestFileFormatKeys:
    @pytest.mark.parametrize(
        ("mime_type", "expected_key"),
        [
            ("application/pdf", "pdf"),
            (DOCX_MIME, "docx"),
            (PPTX_MIME, "pptx"),
            (XLSX_MIME, "xlsx"),
            ("application/msword", "doc"),
            ("application/vnd.ms-powerpoint", "ppt"),
            ("application/vnd.ms-excel", "xls"),
            ("image/png", "image"),
            ("image/jpeg", "image"),
            ("image/webp", "image"),
            ("image/svg+xml", "image"),
            ("text/html", "html"),
            ("text/markdown", "md"),
            ("text/plain; charset=utf-8", "txt"),
            ("APPLICATION/PDF", "pdf"),
        ],
    )
    def test_identified_types_have_a_key(self, mime_type: str, expected_key: str):
        assert format_key_from_mime_type(mime_type=mime_type) == expected_key

    @pytest.mark.parametrize("mime_type", [None, "", "   ", "application/octet-stream", "application/x-unheard-of"])
    def test_unknown_types_have_no_key(self, mime_type: str | None):
        assert format_key_from_mime_type(mime_type=mime_type) is None

    def test_identifies_a_pdf(self):
        raw_bytes = (DOCUMENTS_DIR / "solar_system.pdf").read_bytes()
        file_type = guess_file_type_from_bytes(raw_bytes=raw_bytes)
        assert file_type is not None
        assert file_type.mime == "application/pdf"

    def test_identifies_a_docx_from_its_head_alone(self):
        head = (DOCUMENTS_DIR / "CV-ELIAS-THORNE.docx").read_bytes()[:FILE_HEAD_NB_BYTES]
        file_type = guess_file_type_from_bytes(raw_bytes=head)
        assert file_type is not None
        assert file_type.mime == DOCX_MIME

    def test_returns_none_for_plain_text_instead_of_raising(self):
        assert guess_file_type_from_bytes(raw_bytes=b"# A Markdown title\n\nSome text.") is None

    def test_returns_none_for_no_bytes(self):
        assert guess_file_type_from_bytes(raw_bytes=b"") is None

    def test_the_sniffed_type_wins_over_the_declared_one(self):
        pdf_head = (DOCUMENTS_DIR / "solar_system.pdf").read_bytes()[:FILE_HEAD_NB_BYTES]
        assert identify_mime_type(head=pdf_head, declared_mime_type="image/png") == "application/pdf"

    def test_the_declared_type_stands_when_the_sniff_fails(self):
        assert identify_mime_type(head=b"plain words", declared_mime_type="text/markdown") == "text/markdown"

    def test_no_head_keeps_the_declared_type(self):
        assert identify_mime_type(head=None, declared_mime_type="application/pdf") == "application/pdf"

    def test_nothing_known_gives_none(self):
        assert identify_mime_type(head=b"plain words", declared_mime_type=None) is None

    def test_a_declared_office_type_refines_a_sniffed_zip(self):
        """An Office Open XML file is a zip: when the sniffer sees only the container, the declared Office type is the more precise truth."""
        zip_head = b"PK\x03\x04" + b"\x00" * 26 + b"unrelated/entry.bin" + b"\x00" * 64
        sniffed = guess_file_type_from_bytes(raw_bytes=zip_head)
        assert sniffed is not None, "precondition: the sniffer sees a zip container"
        assert sniffed.mime == "application/zip"
        assert identify_mime_type(head=zip_head, declared_mime_type=DOCX_MIME) == DOCX_MIME
        assert identify_mime_type(head=zip_head, declared_mime_type="image/png") == "application/zip"

    def test_a_png_data_url_holding_a_pdf_is_a_pdf(self):
        pdf_bytes = (DOCUMENTS_DIR / "solar_system.pdf").read_bytes()
        decoded = base64.b64decode(base64.b64encode(pdf_bytes))
        assert identify_mime_type(head=decoded[:FILE_HEAD_NB_BYTES], declared_mime_type="image/png") == "application/pdf"

    def test_an_image_is_identified_as_one(self):
        png_head = (IMAGES_DIR / "logo-tiny.png").read_bytes()[:FILE_HEAD_NB_BYTES]
        assert identify_mime_type(head=png_head, declared_mime_type=None) == "image/png"

    @pytest.mark.parametrize(
        ("format_key", "expected"),
        [
            ("pdf", "a PDF document"),
            ("docx", "a Word document"),
            ("pptx", "a PowerPoint presentation"),
            ("xlsx", "an Excel workbook"),
            ("doc", "a Word 97-2003 document"),
            ("html", "an HTML page"),
            ("image", "an image"),
            ("zip", "a .zip file"),
        ],
    )
    def test_describes_a_key_in_plain_words(self, format_key: str, expected: str):
        assert describe_format_key(format_key=format_key) == expected

    @pytest.mark.parametrize(
        ("format_key", "mime_type", "expected"),
        [
            ("pdf", "application/pdf", "a PDF document (.pdf)"),
            ("docx", DOCX_MIME, "a Word document (.docx)"),
            ("image", "image/png", "an image (image/png)"),
            ("md", "text/markdown", "a .md file (.md)"),
        ],
    )
    def test_describes_a_file_with_the_type_that_tells_it_apart(self, format_key: str, mime_type: str, expected: str):
        assert describe_file_format(format_key=format_key, mime_type=mime_type) == expected

    @pytest.mark.parametrize(
        ("format_keys", "expected"),
        [
            ({"pdf"}, "PDF"),
            ({"image", "pdf"}, "PDF and images"),
            ({"html", "xlsx", "pptx", "docx", "pdf"}, "PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx) and HTML"),
            ({"web_page"}, "web pages"),
            ({"md", "pdf"}, "PDF and .md"),
            (set[str](), "no file format"),
        ],
    )
    def test_describes_a_set_of_readable_formats_in_a_stable_order(self, format_keys: set[str], expected: str):
        assert describe_format_keys(format_keys=format_keys) == expected
