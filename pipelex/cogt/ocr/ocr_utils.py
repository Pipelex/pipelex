from typing import List, Optional

import shortuuid

from pipelex.tools.misc.file_fetching_helpers import fetch_file_from_url_httpx
from pipelex.tools.pdf.pypdfium2_renderer import PdfInput, pypdfium2_renderer
from pipelex.tools.utils.path_utils import ensure_path


def merge_markdown_pages(markdown_pages: List[str], separator: str = "\n") -> str:
    """
    Merge a list of markdown pages into a single markdown string.
    """
    return separator.join(markdown_pages)


async def pdf_to_saved_page_screenshot_paths(
    pdf_path: Optional[str] = None,
    pdf_url: Optional[str] = None,
    dpi: int = 175,
) -> List[str]:
    pdf_input: PdfInput
    if pdf_url:
        pdf_input = fetch_file_from_url_httpx(pdf_url)
    elif pdf_path:
        pdf_input = pdf_path
    else:
        raise RuntimeError("Either pdf_path or pdf_url must be provided")

    temp_directory_name = shortuuid.uuid()
    temp_directory_path = f"temp/{temp_directory_name}"
    ensure_path(temp_directory_path)

    images = await pypdfium2_renderer.render_pdf_pages(pdf_input=pdf_input, dpi=dpi)

    # Save images to the folder and return their paths
    image_paths: List[str] = []
    for i, image in enumerate(images):
        image_path = f"{temp_directory_path}/page_{i}.png"
        image.save(image_path)
        image_paths.append(image_path)

    return image_paths
