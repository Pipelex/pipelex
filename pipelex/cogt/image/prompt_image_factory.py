"""Factory for creating PromptImage instances."""

from pipelex.cogt.exceptions import PromptImageFactoryError
from pipelex.cogt.image.prompt_image import (
    PromptImage,
    PromptImageBase64,
    PromptImageUri,
)
from pipelex.tools.misc.base64_utils import strip_base64_str_if_needed


class PromptImageFactory:
    @classmethod
    def make_prompt_image(
        cls,
        uri: str | None = None,
        base64_bytes: bytes | None = None,
        base64_str: str | None = None,
    ) -> PromptImage:
        """Create a PromptImage from the provided input.

        Args:
            uri: A URI string (file path, HTTP URL, pipelex-storage://, or data: URL)
            base64_bytes: Raw base64-encoded bytes
            base64_str: Base64 string (with or without data: prefix)

        Returns:
            A PromptImage instance (PromptImageUri or PromptImageBase64)

        Raises:
            PromptImageFactoryError: If no valid input is provided
        """
        if base64_bytes:
            return PromptImageBase64(base64_bytes=base64_bytes)
        if base64_str:
            stripped_base64_str = strip_base64_str_if_needed(base64_str)
            return PromptImageBase64(base64_bytes=stripped_base64_str.encode())
        if uri:
            return PromptImageUri(uri=uri)
        msg = "PromptImageFactory requires one of: uri, base64_bytes, or base64_str"
        raise PromptImageFactoryError(msg)
