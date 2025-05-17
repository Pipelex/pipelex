import pathlib
from typing import List

import pypdfium2 as pdfium
from PIL import Image
from pypdfium2.raw import FPDFBitmap_BGRA

PdfInput = str | pathlib.Path | bytes


def render_pdf_pages(input_pdf: PdfInput, dpi: float = 300) -> List[Image.Image]:
    pdf_doc = pdfium.PdfDocument(input_pdf)
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
