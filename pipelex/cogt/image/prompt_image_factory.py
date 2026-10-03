"""Factory for creating PromptImage instances."""

from pipelex.cogt.exceptions import PromptImageFactoryError
from pipelex.cogt.image.prompt_image import (
    PromptImage,
    PromptImageBase64,
    PromptImageBinary,
    PromptImageUri,
)
from pipelex.tools.misc.base64_utils import (
    extract_base64_str_from_base64_url_if_possible,
    strip_base64_str_if_needed,
)


class PromptImageFactory:
    @classmethod
    def make_prompt_image(
        cls, *, uri: str | None = None, base64_data: str | None = None, raw_bytes: bytes | None = None, mime_type: str | None = None
    ) -> PromptImage:
        """Create a PromptImage from the provided input.

        Args:
            uri: A URI string (file path, HTTP URL, pipelex-storage://, or data: URL)
            base64_data: Base64 string (with or without data: prefix)
            raw_bytes: Raw binary image data
            mime_type: The image's MIME type when it is known (only used with a uri other than a data URL,
                whose bytes carry their own type)

        Returns:
            A PromptImage instance (PromptImageUri, PromptImageBase64, or PromptImageBinary)

        Raises:
            PromptImageFactoryError: If no valid input is provided
        """
        if raw_bytes:
            return PromptImageBinary(raw_bytes=raw_bytes)
        if base64_data:
            stripped_base64_data = strip_base64_str_if_needed(base64_data)
            return PromptImageBase64(base64_data=stripped_base64_data)
        if uri:
            # Check if it's a data URL and extract base64 data to avoid URL_MAX_LENGTH validation
            extracted = extract_base64_str_from_base64_url_if_possible(uri)
            if extracted is not None:
                extracted_base64_data, _mime_type = extracted
                return PromptImageBase64(base64_data=extracted_base64_data)
            return PromptImageUri(uri=uri, mime_type=mime_type)
        msg = "PromptImageFactory requires one of: uri, base64_data, or raw_bytes"
        raise PromptImageFactoryError(msg)
