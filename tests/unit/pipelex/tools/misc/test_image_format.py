import pytest

from pipelex.tools.misc.image_utils import ImageFormat


class TestImageFormat:
    @pytest.mark.parametrize(
        ("image_format", "expected_transparent", "expected_is_png", "expected_is_jpeg"),
        [
            (ImageFormat.PNG, True, True, False),
            (ImageFormat.JPEG, False, False, True),
            (ImageFormat.WEBP, False, False, False),
        ],
    )
    def test_format_predicates(
        self,
        image_format: ImageFormat,
        expected_transparent: bool,
        expected_is_png: bool,
        expected_is_jpeg: bool,
    ):
        """Each member answers the is_transparent_compatible/is_png/is_jpeg predicate matrix."""
        assert image_format.is_transparent_compatible is expected_transparent
        assert image_format.is_png is expected_is_png
        assert image_format.is_jpeg is expected_is_jpeg

    @pytest.mark.parametrize(
        ("image_format", "expected_extension"),
        [
            (ImageFormat.PNG, "png"),
            (ImageFormat.JPEG, "jpg"),
            (ImageFormat.WEBP, "webp"),
        ],
    )
    def test_as_file_extension(self, image_format: ImageFormat, expected_extension: str):
        """as_file_extension returns the exact extension string; note JPEG maps to 'jpg'."""
        assert image_format.as_file_extension == expected_extension

    @pytest.mark.parametrize(
        ("image_format", "expected_mime_type"),
        [
            (ImageFormat.PNG, "image/png"),
            (ImageFormat.JPEG, "image/jpeg"),
            (ImageFormat.WEBP, "image/webp"),
        ],
    )
    def test_as_mime_type(self, image_format: ImageFormat, expected_mime_type: str):
        """as_mime_type returns the exact MIME type string for each member."""
        assert image_format.as_mime_type == expected_mime_type

    @pytest.mark.parametrize("image_format", list(ImageFormat))
    def test_from_mime_type_round_trip(self, image_format: ImageFormat):
        """from_mime_type returns the exact member for its own MIME type."""
        assert ImageFormat.from_mime_type(image_format.as_mime_type) is image_format

    def test_from_mime_type_raises_on_unknown(self):
        """from_mime_type raises ValueError for an unknown image MIME type."""
        with pytest.raises(ValueError, match="Unsupported image MIME type: image/tiff"):
            ImageFormat.from_mime_type("image/tiff")

    def test_get_supported_mime_types(self):
        """get_supported_mime_types returns the exact frozenset of image MIME types."""
        supported = ImageFormat.get_supported_mime_types()
        assert isinstance(supported, frozenset)
        assert supported == frozenset({"image/png", "image/jpeg", "image/webp"})

    @pytest.mark.parametrize("image_format", list(ImageFormat))
    def test_is_supported_mime_type_true_for_members(self, image_format: ImageFormat):
        """Every member's MIME type is reported as supported."""
        assert ImageFormat.is_supported_mime_type(image_format.as_mime_type) is True

    @pytest.mark.parametrize(
        "mime_type",
        [
            "image/tiff",
            "application/pdf",
            "garbage",
            "",
        ],
    )
    def test_is_supported_mime_type_false_for_unsupported(self, mime_type: str):
        """Non-image MIME types and garbage are reported as unsupported."""
        assert ImageFormat.is_supported_mime_type(mime_type) is False

    @pytest.mark.parametrize("image_format", list(ImageFormat))
    def test_raise_if_unsupported_mime_type_passes_on_valid(self, image_format: ImageFormat):
        """Supported MIME types do not raise."""
        ImageFormat.raise_if_unsupported_mime_type(image_format.as_mime_type)

    def test_raise_if_unsupported_mime_type_image_prefix_branch(self):
        """An image/* MIME type that is not supported hits the 'Unsupported image MIME type' message."""
        with pytest.raises(ValueError, match="Unsupported image MIME type: image/tiff") as exc_info:
            ImageFormat.raise_if_unsupported_mime_type("image/tiff")
        error_message = str(exc_info.value)
        assert "image/jpeg" in error_message
        assert "image/png" in error_message
        assert "image/webp" in error_message

    def test_raise_if_unsupported_mime_type_non_image_branch(self):
        """A non-image MIME type hits the 'Invalid image MIME type' message with the expected-format hint."""
        with pytest.raises(ValueError, match="Invalid image MIME type: application/pdf") as exc_info:
            ImageFormat.raise_if_unsupported_mime_type("application/pdf")
        error_message = str(exc_info.value)
        assert "Expected format 'image/<subtype>'" in error_message
        assert "image/jpeg" in error_message
        assert "image/png" in error_message
        assert "image/webp" in error_message
