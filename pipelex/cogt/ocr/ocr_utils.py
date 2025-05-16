import os
import uuid
from typing import List, Optional

import pdf2image
import requests
from PIL import Image


class PDFToImageError(ValueError):
    pass


def merge_markdown_pages(markdown_pages: List[str], separator: str = "\n") -> str:
    """
    Merge a list of markdown pages into a single markdown string.
    """
    return separator.join(markdown_pages)


def pdf_path_to_images(pdf_path: str, dpi: int = 175) -> List[Image.Image]:
    images = pdf2image.convert_from_path(  # type: ignore[reportUnknownMemberType]
        pdf_path=pdf_path,
        dpi=dpi,
        fmt="png",
    )
    return images


def pdf_url_to_images(pdf_url: str, dpi: int = 175) -> List[Image.Image]:
    pdf = requests.get(pdf_url)
    images = pdf2image.convert_from_bytes(pdf.content, dpi=dpi, fmt="png")  # type: ignore[reportUnknownMemberType]
    return images


def pdf_to_image_paths(
    pdf_path: Optional[str] = None,
    pdf_url: Optional[str] = None,
    dpi: int = 175,
    output_dir: str = "ocr_tmp",
) -> List[str]:
    # Extract the base name without extension and replace spaces with underscores
    if pdf_path:
        base_name = os.path.basename(pdf_path)
        base_name_no_ext = os.path.splitext(base_name)[0]
        # Use provided output_dir or default to "ocr/base_name"

        # Create the folder if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        images = pdf_path_to_images(pdf_path, dpi)
    elif pdf_url:
        images = pdf_url_to_images(pdf_url, dpi)
        base_name_no_ext = f"pdf_from_bytes_{uuid.uuid4()}"
    else:
        raise ValueError("Either pdf_path or pdf_url must be provided")

    # Save images to the folder and return their paths
    image_paths: List[str] = []
    for i, image in enumerate(images):
        image_path = os.path.join(output_dir, f"{base_name_no_ext}_{i}.png")
        image.save(image_path)
        image_paths.append(image_path)

    return image_paths
