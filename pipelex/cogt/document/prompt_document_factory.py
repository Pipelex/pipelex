"""Factory for creating PromptDocument instances."""

from pipelex.cogt.document.prompt_document import (
    PromptDocument,
    PromptDocumentBase64,
    PromptDocumentBinary,
    PromptDocumentUri,
)
from pipelex.cogt.exceptions import PromptDocumentFactoryError
from pipelex.tools.misc.base64_utils import (
    extract_base64_str_from_base64_url_if_possible,
    strip_base64_str_if_needed,
)


class PromptDocumentFactory:
    @classmethod
    def make_prompt_document(
        cls,
        uri: str | None = None,
        base64_data: str | None = None,
        raw_bytes: bytes | None = None,
        mime_type: str | None = None,
    ) -> PromptDocument:
        """Create a PromptDocument from the provided input.

        Args:
            uri: A URI string (file path, HTTP URL, pipelex-storage://, or data: URL)
            base64_data: Base64 string (with or without data: prefix)
            raw_bytes: Raw binary document data
            mime_type: Optional MIME type for the document (only used with uri)

        Returns:
            A PromptDocument instance (PromptDocumentUri, PromptDocumentBase64, or PromptDocumentBinary)

        Raises:
            PromptDocumentFactoryError: If no valid input is provided
        """
        if raw_bytes:
            return PromptDocumentBinary(raw_bytes=raw_bytes)
        if base64_data:
            stripped_base64_data = strip_base64_str_if_needed(base64_data)
            return PromptDocumentBase64(base64_data=stripped_base64_data)
        if uri:
            # Check if it's a data URL and extract base64 data to avoid URL_MAX_LENGTH validation
            extracted = extract_base64_str_from_base64_url_if_possible(uri)
            if extracted is not None:
                extracted_base64_data, _mime_type = extracted
                return PromptDocumentBase64(base64_data=extracted_base64_data)
            return PromptDocumentUri(uri=uri, mime_type=mime_type)
        msg = "PromptDocumentFactory requires one of: uri, base64_data, or raw_bytes"
        raise PromptDocumentFactoryError(msg)
