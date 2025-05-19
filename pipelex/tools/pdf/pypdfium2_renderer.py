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

            # pil_img.show()
            images.append(pil_img)  # pyright: ignore[reportUnknownArgumentType]
            page.close()
        pdf_doc.close()
        return images

    # ---- public async façade -----------------------------------------
    async def render_pdf_pages(self, pdf_input: PdfInput, dpi: int = 300) -> List[Image.Image]:
        """Render *one* page and return PNG bytes."""
        async with self._pdfium_lock:
            return await asyncio.to_thread(self._render_pdf_pages_sync, pdf_input, dpi)


pypdfium2_renderer = PyPdfium2Renderer()
