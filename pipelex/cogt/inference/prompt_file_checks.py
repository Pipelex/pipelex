"""The per-file checks every inference family runs on the files a prompt carries, before a provider sees them.

Whether a model reads images or documents at all is the family's own question, raised with the family's
own capability error. What these checks answer is the next one: given a model that reads files, is each
file one it reads? The file is the caller's and changes from run to run, so a format the model does not
read is a content error. Only a known format is refused; an unknown one is left to the provider.
"""

from collections.abc import Sequence

from pipelex.cogt.document.prompt_document import PromptDocument
from pipelex.cogt.exceptions import PromptDocumentFormatError, PromptImageFormatError
from pipelex.cogt.image.prompt_image import PromptImage
from pipelex.tools.misc.filetype_utils import (
    IMAGE_FORMAT_KEY,
    describe_file_format,
    describe_format_keys,
    format_key_from_mime_type,
)


def check_prompt_images_are_images(*, model_name: str, prompt_images: Sequence[PromptImage]) -> None:
    """Refuse a prompt image whose known format is not an image.

    Run setup refuses a non-image given to an Image input, but an image the run produced itself never
    went through setup: this is the line that catches it before the provider.
    """
    for image_index, prompt_image in enumerate(prompt_images, start=1):
        mime_type = prompt_image.known_mime_type()
        format_key = format_key_from_mime_type(mime_type=mime_type)
        if format_key is None or format_key == IMAGE_FORMAT_KEY:
            continue
        msg = (
            f"Prompt image {image_index} given to model '{model_name}' is "
            f"{describe_file_format(format_key=format_key, mime_type=mime_type)}, not an image."
        )
        raise PromptImageFormatError(msg)


def check_prompt_documents_are_read(*, model_name: str, supported_document_types: set[str], prompt_documents: Sequence[PromptDocument]) -> None:
    """Refuse a prompt document whose known format is not among the formats the model reads."""
    for document_index, prompt_document in enumerate(prompt_documents, start=1):
        mime_type = prompt_document.known_mime_type()
        format_key = format_key_from_mime_type(mime_type=mime_type)
        if format_key is None or format_key in supported_document_types:
            continue
        msg = (
            f"Prompt document {document_index} given to model '{model_name}' is "
            f"{describe_file_format(format_key=format_key, mime_type=mime_type)}, which it does not read: "
            f"it reads {describe_format_keys(format_keys=supported_document_types)}."
        )
        raise PromptDocumentFormatError(msg)
