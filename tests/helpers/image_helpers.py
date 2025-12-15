"""Image helpers for tests."""

import base64
import tempfile
from io import BytesIO
from pathlib import Path

import shortuuid
from PIL import Image

from pipelex import log
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.tools.misc.file_utils import ensure_path
from pipelex.tools.misc.terminal_utils import print_to_stderr


def save_generated_image(generated_image: GeneratedImage, topic: str, output_dir: str | None = None) -> str | None:
    """Save a generated image to the output directory.

    Handles different URL formats:

    - HTTP URLs: Returns None (not saved locally)
    - Data URI format: data:image/{format};base64,{base64_data}
    - File path: Opens existing file
    - Raw base64: Decodes and opens

    Args:
        generated_image: The generated image with URL
        topic: Topic name used for the filename
        output_dir: Directory to save the image to, defaults to system temp directory

    Returns:
        The path where the image was saved, or None for HTTP URLs
    """
    url = generated_image.url

    # HTTP URLs are not saved locally
    if url.startswith("http"):
        return None

    # Decode image from various formats
    if url.startswith("data:image/"):
        # Data URI format: data:image/{format};base64,{base64_data}
        base64_data = url.split(",", 1)[1]
        image = Image.open(BytesIO(base64.b64decode(base64_data)))
    elif Path(url).exists():
        # File path format
        image = Image.open(url)
    else:
        # Assume raw base64 (fallback)
        image = Image.open(BytesIO(base64.b64decode(url)))

    # Resolve output directory
    resolved_output_dir = output_dir or tempfile.gettempdir()

    # Save to directory with unique filename
    ensure_path(resolved_output_dir)
    image_id = shortuuid.uuid()[:8]
    safe_topic = topic.replace(" ", "_")
    image_name = f"{resolved_output_dir}/{safe_topic}_{image_id}"

    if image.format:
        extension = f".{image.format.lower()}"
    else:
        log.warning(f"Image format not found for image '{image_name}'")
        extension = ""

    output_path = f"{image_name}{extension}"
    image.save(output_path)
    print_to_stderr(f"✓ Image saved to: {output_path}\n")

    return output_path
