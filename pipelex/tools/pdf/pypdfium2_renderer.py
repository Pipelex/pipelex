from __future__ import annotations

import asyncio
import pathlib
from typing import TYPE_CHECKING, cast

import pypdfium2 as pdfium
from pypdfium2 import PdfImage
from pypdfium2.raw import FPDF_PAGEOBJ_IMAGE, FPDFBitmap_BGRA

from pipelex.cogt.extract.bounding_box import BoundingBox
from pipelex.cogt.extract.extract_output import ExtractedImageFromPage
from pipelex.cogt.image.image_size import ImageSize
from pipelex.system.exceptions import ToolError
from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx
from pipelex.tools.misc.image_utils import ImageFormat, pil_image_to_bytes
from pipelex.tools.uri.resolved_uri import (
    ResolvedHttpUrl,
    ResolvedLocalPath,
)
from pipelex.tools.uri.uri_resolver import resolve_uri

if TYPE_CHECKING:
    from PIL import Image

PDFIUM2_REFERENCE_DPI = 72
DEFAULT_IMAGE_EXTRACTION_MAX_DEPTH = 15

# PDF filter name for direct JPEG extraction
# Note: JPEG2000 (JPXDecode) could also be extracted directly, but ImageFormat
# doesn't support jp2 output, so JPEG2000 images go through bitmap extraction
FILTER_JPEG = "DCTDecode"


class PyPdfium2RendererError(ToolError):
    pass


PdfInput = str | pathlib.Path | bytes


async def _resolve_pdf_uri_to_input(pdf_uri: str) -> PdfInput:
    """Resolve a PDF URI to PdfInput (path or bytes).

    Handles HTTP URLs and local paths only. For pipelex-storage:// or base64 data URLs,
    resolve them at the worker level before calling this.

    Args:
        pdf_uri: URI string (local path or HTTP URL)

    Returns:
        PdfInput: file path string for local files, bytes for HTTP URLs

    Raises:
        PyPdfium2RendererError: If the URI type is not supported (storage or base64)
    """
    pdf_input: PdfInput
    resolved_uri = resolve_uri(pdf_uri)
    match resolved_uri:
        case ResolvedHttpUrl():
            pdf_input = await fetch_file_from_url_httpx(url=resolved_uri.url)
        case ResolvedLocalPath():
            pdf_input = resolved_uri.path
        case _:
            msg = f"Unsupported URI type for PDF: {type(resolved_uri).__name__}."
            raise PyPdfium2RendererError(msg)
    return pdf_input


def _extract_image_from_pdf_object(
    image_obj: PdfImage,
    output_format: ImageFormat | None,
) -> ExtractedImageFromPage:
    """Extract an image from a PdfImage object, preferring direct extraction when possible.

    For JPEG images embedded in PDFs, this extracts the original compressed bytes directly
    without decompressing and re-compressing, which is faster and preserves quality.

    For other formats, falls back to bitmap extraction with PIL encoding.

    Args:
        image_obj: A PdfImage object from pypdfium2
        output_format: Desired output format (PNG, JPEG, WEBP), or None to preserve
            the original format when possible (JPEG) or default to PNG

    Returns:
        ExtractedImageFromPage with the extracted image data and page coordinates
    """
    # Get image dimensions directly from the PDF object
    width, height = image_obj.get_size()

    # Get the position on the page (left, bottom, right, top) in PDF coordinates
    # PDF uses bottom-left as origin, so we map:
    # - left → top_left_x
    # - top → top_left_y
    # - right → bottom_right_x
    # - bottom → bottom_right_y
    left, bottom, right, top = image_obj.get_pos()
    bounding_box = BoundingBox.make_from_two_corners(
        top_left_x=left,
        top_left_y=top,
        bottom_right_x=right,
        bottom_right_y=bottom,
    )

    # Get the filters applied to this image to determine compression type
    filters = cast("list[str]", image_obj.get_filters())

    # Check if we can extract directly as JPEG:
    # - Image must be JPEG (DCTDecode filter)
    # - AND output_format is None (preserve original) or explicitly JPEG
    is_embedded_jpeg = FILTER_JPEG in filters
    wants_jpeg = output_format is None or output_format.is_jpeg

    if is_embedded_jpeg and wants_jpeg:
        # Direct extraction: get the compressed JPEG bytes without decompressing
        # get_data returns a ctypes array (c_ubyte) that can be converted to bytes
        actual_bytes = bytes(image_obj.get_data(decode_simple=True))  # pyright: ignore[reportUnknownArgumentType]

        return ExtractedImageFromPage(
            size=ImageSize(width=width, height=height),
            actual_bytes=actual_bytes,
            image_format=ImageFormat.JPEG,
            bounding_box=bounding_box,
        )

    # Fallback: use bitmap extraction with PIL encoding
    # This is needed when:
    # - The image is not JPEG (raw, PNG, etc.)
    # - A specific non-JPEG output format is requested (e.g., PNG, WEBP)
    effective_format = output_format or ImageFormat.PNG
    bitmap = image_obj.get_bitmap()
    pil_image: Image.Image = bitmap.to_pil()
    actual_bytes = pil_image_to_bytes(pil_image=pil_image, image_format=effective_format)

    return ExtractedImageFromPage(
        size=ImageSize(width=width, height=height),
        actual_bytes=actual_bytes,
        image_format=effective_format,
        bounding_box=bounding_box,
    )


class PyPdfium2Renderer:
    """Thread-safe PDF page renderer built on pypdfium2.

    • All entry into the native PDFium library is protected by a single
      asyncio.Lock, so the enclosing *process* is safe even if other
      libraries spin up worker threads.

    • Heavy work runs inside `asyncio.to_thread`, keeping the event-loop
      responsive for the rest of your application.
    """

    _pdfium_lock: asyncio.Lock = asyncio.Lock()  # shared per process

    # ---- internal blocking helper ------------------------------------
    # TODO: Needs UT
    @staticmethod
    def _render_pdf_pages_sync(pdf_input: PdfInput, scale: float) -> list[Image.Image]:
        pdf_doc = pdfium.PdfDocument(pdf_input)
        images: list[Image.Image] = []
        for index in range(len(pdf_doc)):
            page = pdf_doc[index]

            pil_img: Image.Image = page.render(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                scale=scale,  # pyright: ignore[reportArgumentType]
                force_bitmap_format=FPDFBitmap_BGRA,  # always 4-channel
                rev_byteorder=True,  # so we get RGBA
            ).to_pil()

            images.append(pil_img)  # pyright: ignore[reportUnknownArgumentType]
            page.close()
        pdf_doc.close()
        return images

    # TODO: Needs UT
    @staticmethod
    def _extract_text_from_pdf_pages_sync(pdf_input: PdfInput) -> list[str]:
        pdf_doc = pdfium.PdfDocument(pdf_input)
        texts: list[str] = []
        for index in range(len(pdf_doc)):
            pdf_page = pdf_doc[index]
            text = pdf_page.get_textpage().get_text_bounded()  # pyright: ignore[reportUnknownMemberType]
            texts.append(text)  # pyright: ignore[reportUnknownArgumentType]
            pdf_page.close()
        pdf_doc.close()
        return texts

    @staticmethod
    def _extract_embedded_images_from_page_sync(
        pdf_input: PdfInput,
        page_index: int,
        max_depth: int = DEFAULT_IMAGE_EXTRACTION_MAX_DEPTH,
        output_format: ImageFormat | None = None,
    ) -> list[ExtractedImageFromPage]:
        """Extract embedded images from a single PDF page.

        Args:
            pdf_input: PDF file path, bytes, or pathlib.Path
            page_index: Zero-based page index
            max_depth: Maximum depth to descend into Form XObjects (default 15)
            output_format: Output format for images, or None to preserve original
                format when possible (JPEG) or default to PNG

        Returns:
            List of ExtractedImageFromPage for each extracted image, with page coordinates
        """
        pdf_doc = pdfium.PdfDocument(pdf_input)
        page = pdf_doc[page_index]
        images: list[ExtractedImageFromPage] = []

        for obj in page.get_objects(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            filter=[FPDF_PAGEOBJ_IMAGE],
            max_depth=max_depth,
        ):
            # obj is a PdfImage when filter is FPDF_PAGEOBJ_IMAGE
            assert isinstance(obj, PdfImage)
            raw_details = _extract_image_from_pdf_object(image_obj=obj, output_format=output_format)
            images.append(raw_details)

        page.close()
        pdf_doc.close()
        return images

    @staticmethod
    def _extract_embedded_images_from_pdf_sync(
        pdf_input: PdfInput,
        max_depth: int = DEFAULT_IMAGE_EXTRACTION_MAX_DEPTH,
        output_format: ImageFormat | None = None,
    ) -> dict[int, list[ExtractedImageFromPage]]:
        """Extract embedded images from all pages of a PDF.

        Args:
            pdf_input: PDF file path, bytes, or pathlib.Path
            max_depth: Maximum depth to descend into Form XObjects (default 15)
            output_format: Output format for images, or None to preserve original
                format when possible (JPEG) or default to PNG

        Returns:
            Dictionary mapping page index (1-based) to list of ExtractedImageFromPage
        """
        pdf_doc = pdfium.PdfDocument(pdf_input)
        all_images: dict[int, list[ExtractedImageFromPage]] = {}

        for page_index, page in enumerate(pdf_doc):
            page_images: list[ExtractedImageFromPage] = []

            for obj in page.get_objects(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                filter=[FPDF_PAGEOBJ_IMAGE],
                max_depth=max_depth,
            ):
                # obj is a PdfImage when filter is FPDF_PAGEOBJ_IMAGE
                assert isinstance(obj, PdfImage)
                raw_details = _extract_image_from_pdf_object(image_obj=obj, output_format=output_format)
                page_images.append(raw_details)

            # Use 1-based page index for consistency with other page-related APIs
            all_images[page_index + 1] = page_images
            page.close()

        pdf_doc.close()
        return all_images

    # ---- public async façade -----------------------------------------
    async def render_pdf_pages(self, pdf_input: PdfInput, dpi: int) -> list[Image.Image]:
        scale = dpi / PDFIUM2_REFERENCE_DPI
        """Render *one* page and return PNG bytes."""
        async with self._pdfium_lock:
            return await asyncio.to_thread(self._render_pdf_pages_sync, pdf_input, scale)

    async def extract_text_from_pdf_pages(self, pdf_input: PdfInput) -> list[str]:
        """Extract text from all pages of a PDF."""
        async with self._pdfium_lock:
            return await asyncio.to_thread(self._extract_text_from_pdf_pages_sync, pdf_input)

    async def render_pdf_pages_from_uri(self, pdf_uri: str, dpi: int) -> list[Image.Image]:
        pdf_input = await _resolve_pdf_uri_to_input(pdf_uri)
        return await self.render_pdf_pages(pdf_input=pdf_input, dpi=dpi)

    async def extract_text_from_pdf_pages_from_uri(self, pdf_uri: str) -> list[str]:
        """Extract text from all pages of a PDF from URI."""
        pdf_input = await _resolve_pdf_uri_to_input(pdf_uri)
        return await self.extract_text_from_pdf_pages(pdf_input=pdf_input)

    async def extract_embedded_images_from_page(
        self,
        pdf_input: PdfInput,
        page_index: int,
        max_depth: int = DEFAULT_IMAGE_EXTRACTION_MAX_DEPTH,
        output_format: ImageFormat | None = None,
    ) -> list[ExtractedImageFromPage]:
        """Extract embedded images from a single PDF page.

        Args:
            pdf_input: PDF file path, bytes, or pathlib.Path
            page_index: Zero-based page index
            max_depth: Maximum depth to descend into Form XObjects (default 15)
            output_format: Output format for images, or None to preserve original
                format when possible (JPEG) or default to PNG

        Returns:
            List of ExtractedImageFromPage for each extracted image, with page coordinates
        """
        async with self._pdfium_lock:
            return await asyncio.to_thread(
                self._extract_embedded_images_from_page_sync,
                pdf_input,
                page_index,
                max_depth,
                output_format,
            )

    async def extract_embedded_images_from_pdf(
        self,
        pdf_input: PdfInput,
        max_depth: int = DEFAULT_IMAGE_EXTRACTION_MAX_DEPTH,
        output_format: ImageFormat | None = None,
    ) -> dict[int, list[ExtractedImageFromPage]]:
        """Extract embedded images from all pages of a PDF.

        Args:
            pdf_input: PDF file path, bytes, or pathlib.Path
            max_depth: Maximum depth to descend into Form XObjects (default 15)
            output_format: Output format for images, or None to preserve original
                format when possible (JPEG) or default to PNG

        Returns:
            Dictionary mapping page index (1-based) to list of ExtractedImageFromPage
        """
        async with self._pdfium_lock:
            return await asyncio.to_thread(
                self._extract_embedded_images_from_pdf_sync,
                pdf_input,
                max_depth,
                output_format,
            )

    async def extract_embedded_images_from_pdf_uri(
        self,
        pdf_uri: str,
        max_depth: int = DEFAULT_IMAGE_EXTRACTION_MAX_DEPTH,
        output_format: ImageFormat | None = None,
    ) -> dict[int, list[ExtractedImageFromPage]]:
        """Extract embedded images from all pages of a PDF from URI.

        Args:
            pdf_uri: PDF URI (local path or HTTP URL)
            max_depth: Maximum depth to descend into Form XObjects (default 15)
            output_format: Output format for images, or None to preserve original
                format when possible (JPEG) or default to PNG

        Returns:
            Dictionary mapping page index (1-based) to list of ExtractedImageFromPage
        """
        pdf_input = await _resolve_pdf_uri_to_input(pdf_uri)
        return await self.extract_embedded_images_from_pdf(
            pdf_input=pdf_input,
            max_depth=max_depth,
            output_format=output_format,
        )


pypdfium2_renderer = PyPdfium2Renderer()
