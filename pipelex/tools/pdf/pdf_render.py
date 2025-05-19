# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import List, Optional

from PIL import Image

from pipelex.tools.misc.file_fetching_helpers import fetch_file_from_url_httpx
from pipelex.tools.pdf.pypdfium2_renderer import PdfInput, pypdfium2_renderer


async def render_pdf_pages_to_images(
    pdf_path: Optional[str] = None,
    pdf_url: Optional[str] = None,
    dpi: int = 175,
) -> List[Image.Image]:
    pdf_input: PdfInput
    if pdf_url:
        pdf_input = fetch_file_from_url_httpx(pdf_url)
    elif pdf_path:
        pdf_input = pdf_path
    else:
        raise RuntimeError("Either pdf_path or pdf_url must be provided")

    images = await pypdfium2_renderer.render_pdf_pages(pdf_input=pdf_input, dpi=dpi)
    return images
