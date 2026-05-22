"""Canonical provider identifiers for inference plugins.

One value per provider plugin. The string values are the literals previously
hard-coded in each ``extract_*_metadata`` function, so serialized payloads
(``ProviderErrorMetadata.provider`` in CLI JSON and Temporal error details)
round-trip unchanged.
"""

from pipelex.types import StrEnum


class ProviderName(StrEnum):
    """Identifies the inference provider an SDK error originated from."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    MISTRAL = "mistral"
    AZURE = "azure"
    BEDROCK = "bedrock"
    FAL = "fal"
    HUGGINGFACE = "huggingface"
    GATEWAY = "gateway"
    LINKUP = "linkup"
    DOCLING = "docling"
    PYPDFIUM2 = "pypdfium2"

    @property
    def is_local_file_extractor(self) -> bool:
        """Whether this provider runs in-process against the file system (no HTTP).

        Local extractors surface builtin exceptions (``FileNotFoundError``,
        ``ValueError`` …) rather than SDK HTTP errors, so the Classify step
        interprets those exception types differently for them.
        """
        match self:
            case ProviderName.DOCLING | ProviderName.PYPDFIUM2:
                return True
            case (
                ProviderName.OPENAI
                | ProviderName.ANTHROPIC
                | ProviderName.GOOGLE
                | ProviderName.MISTRAL
                | ProviderName.AZURE
                | ProviderName.BEDROCK
                | ProviderName.FAL
                | ProviderName.HUGGINGFACE
                | ProviderName.GATEWAY
                | ProviderName.LINKUP
            ):
                return False
