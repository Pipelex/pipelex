import io

import pytest
from PIL import Image

from pipelex.tools.misc.image_utils import ImageFormat, pil_image_to_bytes


class TestPilImageToBytes:
    @pytest.mark.parametrize(
        ("image_format", "expected_pil_format", "expected_magic_bytes"),
        [
            (ImageFormat.PNG, "PNG", b"\x89PNG"),
            (ImageFormat.JPEG, "JPEG", b"\xff\xd8"),
            (ImageFormat.WEBP, "WEBP", b"RIFF"),
        ],
    )
    def test_converts_to_requested_format(
        self,
        image_format: ImageFormat,
        expected_pil_format: str,
        expected_magic_bytes: bytes,
    ):
        """The output bytes reopen as the requested format and start with its magic bytes."""
        pil_image = Image.new("RGB", (4, 4), color=(10, 20, 30))

        image_bytes = pil_image_to_bytes(pil_image, image_format=image_format)

        assert isinstance(image_bytes, bytes)
        assert image_bytes.startswith(expected_magic_bytes)
        reopened = Image.open(io.BytesIO(image_bytes))
        assert reopened.format == expected_pil_format
        assert reopened.size == (4, 4)

    def test_none_format_defaults_to_png(self):
        """Passing image_format=None encodes as PNG."""
        pil_image = Image.new("RGB", (4, 4), color=(200, 100, 50))

        image_bytes = pil_image_to_bytes(pil_image, image_format=None)

        assert image_bytes.startswith(b"\x89PNG")
        reopened = Image.open(io.BytesIO(image_bytes))
        assert reopened.format == "PNG"

    def test_png_round_trip_preserves_pixels(self):
        """PNG is lossless: pixel values survive the encode/decode round trip."""
        pil_image = Image.new("RGB", (4, 4), color=(123, 45, 67))
        pil_image.putpixel((0, 0), (255, 0, 0))
        pil_image.putpixel((3, 3), (0, 0, 255))

        image_bytes = pil_image_to_bytes(pil_image, image_format=ImageFormat.PNG)

        reopened = Image.open(io.BytesIO(image_bytes))
        assert reopened.getpixel((0, 0)) == (255, 0, 0)
        assert reopened.getpixel((3, 3)) == (0, 0, 255)
        assert reopened.getpixel((1, 1)) == (123, 45, 67)
        assert reopened.getpixel((2, 2)) == (123, 45, 67)
