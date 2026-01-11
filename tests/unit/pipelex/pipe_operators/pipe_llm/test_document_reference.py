import pytest

from pipelex.pipe_operators.llm.document_reference import DocumentReference, DocumentReferenceKind


class TestDocumentReference:
    """Tests for DocumentReference and DocumentReferenceKind models."""

    def test_create_direct_reference(self) -> None:
        """Test creating a DIRECT document reference."""
        ref = DocumentReference(
            variable_path="report",
            kind=DocumentReferenceKind.DIRECT,
        )

        assert ref.variable_path == "report"
        assert ref.kind == DocumentReferenceKind.DIRECT

    def test_create_direct_list_reference(self) -> None:
        """Test creating a DIRECT_LIST document reference."""
        ref = DocumentReference(
            variable_path="documents",
            kind=DocumentReferenceKind.DIRECT_LIST,
        )

        assert ref.variable_path == "documents"
        assert ref.kind == DocumentReferenceKind.DIRECT_LIST

    def test_str_representation_direct(self) -> None:
        """Test string representation for DIRECT reference."""
        ref = DocumentReference(
            variable_path="contract",
            kind=DocumentReferenceKind.DIRECT,
        )

        result = str(ref)

        assert "DIRECT" in result
        assert "contract" in result

    def test_str_representation_direct_list(self) -> None:
        """Test string representation for DIRECT_LIST reference."""
        ref = DocumentReference(
            variable_path="attachments",
            kind=DocumentReferenceKind.DIRECT_LIST,
        )

        result = str(ref)

        assert "DIRECT_LIST" in result
        assert "attachments" in result

    def test_nested_path_variable(self) -> None:
        """Test creating a reference with dotted variable path (e.g., submission.pdf)."""
        ref = DocumentReference(
            variable_path="submission.pdf",
            kind=DocumentReferenceKind.DIRECT,
        )

        assert ref.variable_path == "submission.pdf"
        assert ref.kind == DocumentReferenceKind.DIRECT


class TestDocumentReferenceKind:
    """Tests for DocumentReferenceKind enum."""

    def test_direct_value(self) -> None:
        """Test DIRECT enum value."""
        assert DocumentReferenceKind.DIRECT == "direct"
        assert DocumentReferenceKind.DIRECT.value == "direct"

    def test_direct_list_value(self) -> None:
        """Test DIRECT_LIST enum value."""
        assert DocumentReferenceKind.DIRECT_LIST == "direct_list"
        assert DocumentReferenceKind.DIRECT_LIST.value == "direct_list"

    def test_kind_is_strenum(self) -> None:
        """Test that the kind can be used as a string directly."""
        kind = DocumentReferenceKind.DIRECT

        # StrEnum allows direct comparison with strings
        assert kind == "direct"
        # And can be used in string formatting
        assert f"Kind: {kind}" == "Kind: direct"

    @pytest.mark.parametrize(
        ("kind", "expected_str"),
        [
            (DocumentReferenceKind.DIRECT, "direct"),
            (DocumentReferenceKind.DIRECT_LIST, "direct_list"),
        ],
    )
    def test_all_kinds_have_string_values(self, kind: DocumentReferenceKind, expected_str: str) -> None:
        """Test all DocumentReferenceKind values have expected string representations."""
        assert kind == expected_str
