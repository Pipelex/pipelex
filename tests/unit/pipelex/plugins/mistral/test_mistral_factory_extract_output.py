"""Tests for MistralFactory OCR response conversion: base64 cleaning, extracted image building, and ExtractOutput assembly."""

from __future__ import annotations

import base64

import pytest
from mistralai.models import OCRImageObject, OCRPageObject, OCRResponse, OCRUsageInfo

from pipelex.plugins.mistral.mistral_exceptions import MistralExtractResponseError
from pipelex.plugins.mistral.mistral_factory import MistralFactory

JPEG_BODY = b"\xff\xd8\xff\xe0\x00\x10JFIF-jpeg-payload-bytes"
PNG_BODY = b"\x89PNG\r\n\x1a\npng-payload-bytes"


def _encode(raw_bytes: bytes) -> str:
    return base64.b64encode(raw_bytes).decode("ascii")


def _make_ocr_image_obj(
    *,
    image_base64: str | None,
    top_left_x: int | None = None,
    top_left_y: int | None = None,
    bottom_right_x: int | None = None,
    bottom_right_y: int | None = None,
) -> OCRImageObject:
    return OCRImageObject(
        id="img-0.jpeg",
        top_left_x=top_left_x,
        top_left_y=top_left_y,
        bottom_right_x=bottom_right_x,
        bottom_right_y=bottom_right_y,
        image_base64=image_base64,
    )


class TestMistralFactoryExtractOutput:
    # ---- _clean_mistral_image_base64 ----

    @pytest.mark.parametrize(
        ("_topic", "raw_bytes"),
        [
            ("already_jpeg", JPEG_BODY),
            ("already_png", PNG_BODY),
        ],
    )
    def test_clean_base64_already_clean_returned_unchanged(self, _topic: str, raw_bytes: bytes) -> None:
        """Data already starting with a JPEG or PNG magic number is returned as the exact same base64 string."""
        base64_str = _encode(raw_bytes)
        cleaned = MistralFactory._clean_mistral_image_base64(base64_str)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert cleaned == base64_str

    @pytest.mark.parametrize(
        ("_topic", "image_body"),
        [
            ("jpeg_with_metadata", JPEG_BODY),
            ("png_with_metadata", PNG_BODY),
        ],
    )
    def test_clean_base64_strips_prepended_metadata(self, _topic: str, image_body: bytes) -> None:
        """Metadata bytes prepended before the image magic number are stripped, leaving exactly the image bytes."""
        base64_str = _encode(b"METADATA" + image_body)
        cleaned = MistralFactory._clean_mistral_image_base64(base64_str)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert base64.b64decode(cleaned) == image_body

    @pytest.mark.parametrize(
        ("_topic", "raw_bytes"),
        [
            ("no_magic_at_all", b"\x00\x01\x02\x03" * 10),
            ("magic_beyond_scan_window", b"\x00" * 33 + JPEG_BODY),
        ],
    )
    def test_clean_base64_no_magic_in_window_returns_original(self, _topic: str, raw_bytes: bytes) -> None:
        """When no image magic number appears in the first 32 bytes, the original string is returned untouched."""
        base64_str = _encode(raw_bytes)
        cleaned = MistralFactory._clean_mistral_image_base64(base64_str)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert cleaned == base64_str

    def test_clean_base64_invalid_input_returns_original(self) -> None:
        """An input that fails base64 decoding is returned unmodified (ValueError branch)."""
        invalid_base64 = "not-valid-base64!!!"
        cleaned = MistralFactory._clean_mistral_image_base64(invalid_base64)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert cleaned == invalid_base64

    # ---- make_extracted_image_from_page_from_mistral_ocr_image_obj ----

    def test_make_extracted_image_missing_base64_raises(self) -> None:
        """An OCR image object without base64 data raises MistralExtractResponseError."""
        ocr_image_obj = _make_ocr_image_obj(image_base64=None, top_left_x=0, top_left_y=0, bottom_right_x=10, bottom_right_y=10)
        with pytest.raises(MistralExtractResponseError, match="does not have an image base64"):
            MistralFactory.make_extracted_image_from_page_from_mistral_ocr_image_obj(ocr_image_obj)

    def test_make_extracted_image_full_coords(self) -> None:
        """Full corner coordinates produce an ImageSize (bottom-right minus top-left) and a four-corner BoundingBox; mime type is pinned to JPEG."""
        jpeg_base64 = _encode(JPEG_BODY)
        ocr_image_obj = _make_ocr_image_obj(
            image_base64=jpeg_base64,
            top_left_x=10,
            top_left_y=20,
            bottom_right_x=110,
            bottom_right_y=220,
        )

        extracted_image = MistralFactory.make_extracted_image_from_page_from_mistral_ocr_image_obj(ocr_image_obj)

        assert extracted_image.base64_str == jpeg_base64
        assert extracted_image.mime_type == "image/jpeg"
        assert extracted_image.size is not None
        assert extracted_image.size.width == 100
        assert extracted_image.size.height == 200
        bounding_box = extracted_image.bounding_box
        assert bounding_box is not None
        assert bounding_box.top_left_x == 10
        assert bounding_box.top_left_y == 20
        assert bounding_box.top_right_x == 110
        assert bounding_box.top_right_y == 20
        assert bounding_box.bottom_right_x == 110
        assert bounding_box.bottom_right_y == 220
        assert bounding_box.bottom_left_x == 10
        assert bounding_box.bottom_left_y == 220

    @pytest.mark.parametrize(
        ("_topic", "top_left_x", "top_left_y", "bottom_right_x", "bottom_right_y"),
        [
            ("all_coords_missing", None, None, None, None),
            ("only_top_left", 10, 20, None, None),
            ("only_x_pair", 10, None, 110, None),
        ],
    )
    def test_make_extracted_image_partial_coords(
        self,
        _topic: str,
        top_left_x: int | None,
        top_left_y: int | None,
        bottom_right_x: int | None,
        bottom_right_y: int | None,
    ) -> None:
        """Partial corner coordinates yield no size and no bounding box, but the image itself is still extracted."""
        jpeg_base64 = _encode(JPEG_BODY)
        ocr_image_obj = _make_ocr_image_obj(
            image_base64=jpeg_base64,
            top_left_x=top_left_x,
            top_left_y=top_left_y,
            bottom_right_x=bottom_right_x,
            bottom_right_y=bottom_right_y,
        )

        extracted_image = MistralFactory.make_extracted_image_from_page_from_mistral_ocr_image_obj(ocr_image_obj)

        assert extracted_image.size is None
        assert extracted_image.bounding_box is None
        assert extracted_image.base64_str == jpeg_base64
        assert extracted_image.mime_type == "image/jpeg"

    # ---- make_extract_output_from_mistral_response ----

    @pytest.mark.asyncio
    async def test_make_extract_output_from_mistral_response(self) -> None:
        """An OCR response with a page carrying an image and a page without is converted to ExtractOutput keyed by page index."""
        jpeg_base64 = _encode(JPEG_BODY)
        page_with_image = OCRPageObject(
            index=0,
            markdown="# Page with image",
            images=[
                _make_ocr_image_obj(
                    image_base64=jpeg_base64,
                    top_left_x=5,
                    top_left_y=6,
                    bottom_right_x=15,
                    bottom_right_y=26,
                )
            ],
            dimensions=None,
        )
        page_without_image = OCRPageObject(
            index=2,
            markdown="# Page without image",
            images=[],
            dimensions=None,
        )
        mistral_response = OCRResponse(
            pages=[page_with_image, page_without_image],
            model="mistral-ocr-latest",
            usage_info=OCRUsageInfo(pages_processed=2),
        )

        extract_output = await MistralFactory.make_extract_output_from_mistral_response(mistral_extract_response=mistral_response)

        assert set(extract_output.pages.keys()) == {0, 2}
        first_page = extract_output.pages[0]
        assert first_page.text == "# Page with image"
        assert len(first_page.extracted_images) == 1
        extracted_image = first_page.extracted_images[0]
        assert extracted_image.base64_str == jpeg_base64
        assert extracted_image.size is not None
        assert extracted_image.size.width == 10
        assert extracted_image.size.height == 20
        second_page = extract_output.pages[2]
        assert second_page.text == "# Page without image"
        assert second_page.extracted_images == []
