# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from __future__ import annotations

import asyncio
import pathlib
from typing import List

import pypdfium2 as pdfium
from PIL import Image
from pypdfium2.raw import FPDFBitmap_BGRA

from pipelex.tools.exceptions import ToolException
from pipelex.tools.misc.file_fetching_helpers import fetch_file_from_url_httpx_async
from pipelex.tools.utils.path_utils import clarify_path_or_url


class PyPdfium2RendererError(ToolException):
    pass


PdfInput = str | pathlib.Path | bytes


class PyPdfium2Renderer:
    """
    Thread-safe PDF page renderer built on pypdfium2.

    • All entry into the native PDFium library is protected by a single
      asyncio.Lock, so the enclosing *process* is safe even if other
      libraries spin up worker threads.

    • Heavy work runs inside `asyncio.to_thread`, keeping the event-loop
      responsive for the rest of your application.
    """

    _pdfium_lock: asyncio.Lock = asyncio.Lock()  # shared per process

    # ---- internal blocking helper ------------------------------------
    @staticmethod
    def _render_pdf_pages_sync(pdf_input: PdfInput, dpi: float = 300) -> List[Image.Image]:
        pdf_doc = pdfium.PdfDocument(pdf_input)
        images: List[Image.Image] = []
        for index in range(len(pdf_doc)):
            # page = doc.get_page(index)
            page = pdf_doc[index]

            pil_img: Image.Image = page.render(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                scale=dpi / 72,  # pyright: ignore[reportArgumentType]
                force_bitmap_format=FPDFBitmap_BGRA,  # always 4-channel
                rev_byteorder=True,  # so we get RGBA
            ).to_pil()

            images.append(pil_img)  # pyright: ignore[reportUnknownArgumentType]
            page.close()
        pdf_doc.close()
        return images

    # ---- public async façade -----------------------------------------
    async def render_pdf_pages(self, pdf_input: PdfInput, dpi: int = 300) -> List[Image.Image]:
        """Render *one* page and return PNG bytes."""
        async with self._pdfium_lock:
            return await asyncio.to_thread(self._render_pdf_pages_sync, pdf_input, dpi)

    async def render_pdf_pages_from_uri(self, pdf_uri: str, dpi: int = 300) -> List[Image.Image]:
        pdf_path, pdf_url = clarify_path_or_url(path_or_uri=pdf_uri)  # pyright: ignore
        if pdf_url:
            pdf_bytes = await fetch_file_from_url_httpx_async(url=pdf_url)
            return await self.render_pdf_pages(pdf_input=pdf_bytes, dpi=dpi)
        elif pdf_path:
            return await self.render_pdf_pages(pdf_input=pdf_path, dpi=dpi)
        else:
            raise PyPdfium2RendererError(f"Invalid PDF URI: {pdf_uri}")


pypdfium2_renderer = PyPdfium2Renderer()
