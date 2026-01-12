import pytest

from pipelex.pipe_operators.llm.image_reference import ImageReference, ImageReferenceKind


class TestImageReference:
    """Tests for ImageReference and ImageReferenceKind models."""

    def test_create_direct_reference(self) -> None:
        """Test creating a DIRECT image reference."""
        ref = ImageReference(
            variable_path="portrait",
            kind=ImageReferenceKind.DIRECT,
        )

        assert ref.variable_path == "portrait"
        assert ref.kind == ImageReferenceKind.DIRECT
        assert ref.nested_image_paths is None

    def test_create_direct_list_reference(self) -> None:
        """Test creating a DIRECT_LIST image reference."""
        ref = ImageReference(
            variable_path="photos",
            kind=ImageReferenceKind.DIRECT_LIST,
        )

        assert ref.variable_path == "photos"
        assert ref.kind == ImageReferenceKind.DIRECT_LIST
        assert ref.nested_image_paths is None

    def test_create_nested_reference_with_paths(self) -> None:
        """Test creating a NESTED image reference with nested paths."""
        ref = ImageReference(
            variable_path="page",
            kind=ImageReferenceKind.NESTED,
            nested_image_paths=["text_and_images.images", "page_view"],
        )

        assert ref.variable_path == "page"
        assert ref.kind == ImageReferenceKind.NESTED
        assert ref.nested_image_paths == ["text_and_images.images", "page_view"]

    def test_create_nested_reference_without_paths(self) -> None:
        """Test that NESTED reference can be created without nested paths (edge case)."""
        ref = ImageReference(
            variable_path="document",
            kind=ImageReferenceKind.NESTED,
        )

        assert ref.variable_path == "document"
        assert ref.kind == ImageReferenceKind.NESTED
        assert ref.nested_image_paths is None

    def test_str_representation_direct(self) -> None:
        """Test string representation for DIRECT reference."""
        ref = ImageReference(
            variable_path="avatar",
            kind=ImageReferenceKind.DIRECT,
        )

        result = str(ref)

        assert "DIRECT" in result
        assert "avatar" in result

    def test_str_representation_direct_list(self) -> None:
        """Test string representation for DIRECT_LIST reference."""
        ref = ImageReference(
            variable_path="gallery",
            kind=ImageReferenceKind.DIRECT_LIST,
        )

        result = str(ref)

        assert "DIRECT_LIST" in result
        assert "gallery" in result

    def test_str_representation_nested(self) -> None:
        """Test string representation for NESTED reference."""
        ref = ImageReference(
            variable_path="document",
            kind=ImageReferenceKind.NESTED,
            nested_image_paths=["cover", "pages.images"],
        )

        result = str(ref)

        assert "NESTED" in result
        assert "document" in result
        assert "cover" in result
        assert "pages.images" in result

    def test_nested_path_variable(self) -> None:
        """Test creating a reference with dotted variable path (e.g., doc.cover)."""
        ref = ImageReference(
            variable_path="doc.cover",
            kind=ImageReferenceKind.DIRECT,
        )

        assert ref.variable_path == "doc.cover"
        assert ref.kind == ImageReferenceKind.DIRECT


class TestImageReferenceKind:
    """Tests for ImageReferenceKind enum."""

    def test_direct_value(self) -> None:
        """Test DIRECT enum value."""
        assert ImageReferenceKind.DIRECT == "direct"
        assert ImageReferenceKind.DIRECT.value == "direct"

    def test_direct_list_value(self) -> None:
        """Test DIRECT_LIST enum value."""
        assert ImageReferenceKind.DIRECT_LIST == "direct_list"
        assert ImageReferenceKind.DIRECT_LIST.value == "direct_list"

    def test_nested_value(self) -> None:
        """Test NESTED enum value."""
        assert ImageReferenceKind.NESTED == "nested"
        assert ImageReferenceKind.NESTED.value == "nested"

    def test_kind_is_strenum(self) -> None:
        """Test that the kind can be used as a string directly."""
        kind = ImageReferenceKind.DIRECT

        # StrEnum allows direct comparison with strings
        assert kind == "direct"
        # And can be used in string formatting
        assert f"Kind: {kind}" == "Kind: direct"

    @pytest.mark.parametrize(
        ("kind", "expected_str"),
        [
            (ImageReferenceKind.DIRECT, "direct"),
            (ImageReferenceKind.DIRECT_LIST, "direct_list"),
            (ImageReferenceKind.NESTED, "nested"),
        ],
    )
    def test_all_kinds_have_string_values(self, kind: ImageReferenceKind, expected_str: str) -> None:
        """Test all ImageReferenceKind values have expected string representations."""
        assert kind == expected_str
