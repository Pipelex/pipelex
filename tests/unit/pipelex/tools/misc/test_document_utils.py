import pytest

from pipelex.tools.misc.document_utils import DocumentFormat


class TestDocumentFormat:
    @pytest.mark.parametrize(
        ("document_format", "expected_is_pdf", "expected_is_docx", "expected_is_pptx"),
        [
            (DocumentFormat.PDF, True, False, False),
            (DocumentFormat.DOCX, False, True, False),
            (DocumentFormat.PPTX, False, False, True),
        ],
    )
    def test_format_predicates(
        self,
        document_format: DocumentFormat,
        expected_is_pdf: bool,
        expected_is_docx: bool,
        expected_is_pptx: bool,
    ):
        """Each member answers the full is_pdf/is_docx/is_pptx predicate matrix."""
        assert document_format.is_pdf is expected_is_pdf
        assert document_format.is_docx is expected_is_docx
        assert document_format.is_pptx is expected_is_pptx

    @pytest.mark.parametrize(
        ("document_format", "expected_extension"),
        [
            (DocumentFormat.PDF, "pdf"),
            (DocumentFormat.DOCX, "docx"),
            (DocumentFormat.PPTX, "pptx"),
        ],
    )
    def test_as_file_extension(self, document_format: DocumentFormat, expected_extension: str):
        """as_file_extension returns the exact extension string for each member."""
        assert document_format.as_file_extension == expected_extension

    @pytest.mark.parametrize(
        ("document_format", "expected_mime_type"),
        [
            (DocumentFormat.PDF, "application/pdf"),
            (DocumentFormat.DOCX, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            (DocumentFormat.PPTX, "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ],
    )
    def test_as_mime_type(self, document_format: DocumentFormat, expected_mime_type: str):
        """as_mime_type returns the exact MIME type string for each member."""
        assert document_format.as_mime_type == expected_mime_type

    def test_get_supported_mime_types(self):
        """get_supported_mime_types returns the exact frozenset of document MIME types."""
        supported = DocumentFormat.get_supported_mime_types()
        assert isinstance(supported, frozenset)
        assert supported == frozenset(
            {
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            }
        )

    @pytest.mark.parametrize("document_format", list(DocumentFormat))
    def test_is_supported_mime_type_true_for_members(self, document_format: DocumentFormat):
        """Every member's MIME type is reported as supported."""
        assert DocumentFormat.is_supported_mime_type(document_format.as_mime_type) is True

    @pytest.mark.parametrize(
        "mime_type",
        [
            "image/png",
            "not-a-mime-type",
            "",
            "application/PDF",
        ],
    )
    def test_is_supported_mime_type_false_for_unsupported(self, mime_type: str):
        """Non-document MIME types and garbage are reported as unsupported."""
        assert DocumentFormat.is_supported_mime_type(mime_type) is False

    @pytest.mark.parametrize("document_format", list(DocumentFormat))
    def test_raise_if_unsupported_mime_type_passes_on_valid(self, document_format: DocumentFormat):
        """Supported MIME types do not raise."""
        DocumentFormat.raise_if_unsupported_mime_type(document_format.as_mime_type)

    def test_raise_if_unsupported_mime_type_raises_with_supported_list(self):
        """Unsupported MIME types raise ValueError naming the offender and listing supported types."""
        with pytest.raises(ValueError, match="Unsupported document MIME type: image/png") as exc_info:
            DocumentFormat.raise_if_unsupported_mime_type("image/png")
        error_message = str(exc_info.value)
        assert "application/pdf" in error_message
        assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in error_message
        assert "application/vnd.openxmlformats-officedocument.presentationml.presentation" in error_message

    @pytest.mark.parametrize("document_format", list(DocumentFormat))
    def test_from_mime_type_round_trip(self, document_format: DocumentFormat):
        """from_mime_type returns the exact member for its own MIME type."""
        assert DocumentFormat.from_mime_type(document_format.as_mime_type) is document_format

    @pytest.mark.parametrize(
        "mime_type",
        [
            "image/png",
            "application/msword",
            "garbage",
        ],
    )
    def test_from_mime_type_raises_on_unknown(self, mime_type: str):
        """from_mime_type raises ValueError for unknown MIME types."""
        with pytest.raises(ValueError, match=f"Unsupported document MIME type: {mime_type}"):
            DocumentFormat.from_mime_type(mime_type)
