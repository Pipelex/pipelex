from __future__ import annotations

from pipelex.types import StrEnum


class GatewayExtractProtocol(StrEnum):
    MISTRAL_DOC_AI = "mistral-doc-ai"
    AZURE_DOC_INTEL = "azure-doc-intel"

    @classmethod
    def make_from_model_handle(cls, model_handle: str) -> GatewayExtractProtocol:
        match model_handle:
            case "mistral-document-ai-2505":
                return cls.MISTRAL_DOC_AI
            case "azure-document-intelligence":
                return cls.AZURE_DOC_INTEL
            case _:
                msg = f"Invalid model ID: {model_handle}"
                raise ValueError(msg)
