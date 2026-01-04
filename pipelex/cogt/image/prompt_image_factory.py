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
        base_64: bytes | None = None,
        base_64_str: str | None = None,
    ) -> PromptImage:
        """Create a PromptImage from the provided input.

        Args:
            uri: A URI string (file path, HTTP URL, pipelex-storage://, or data: URL)
            base_64: Raw base64-encoded bytes
            base_64_str: Base64 string (with or without data: prefix)

        Returns:
            A PromptImage instance (PromptImageUri or PromptImageBase64)

        Raises:
            PromptImageFactoryError: If no valid input is provided
        """
        if base_64:
            return PromptImageBase64(base_64=base_64)
        if base_64_str:
            stripped_base_64_str = strip_base64_str_if_needed(base_64_str)
            return PromptImageBase64(base_64=stripped_base_64_str.encode())
        if uri:
            return PromptImageUri(uri=uri)
        msg = "PromptImageFactory requires one of: uri, base_64, or base_64_str"
        raise PromptImageFactoryError(msg)
