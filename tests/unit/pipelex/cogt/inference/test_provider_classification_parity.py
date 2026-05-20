"""Meta-test: every ``ProviderName`` is wired into the Extract step.

Adding a new ``ProviderName`` enum value without a matching ``extract_*_metadata``
function would let the worker compile but produce a useless metadata envelope.
This test fails fast in that case by walking the enum against a registry.
"""

from collections.abc import Callable

import pytest

from pipelex.cogt.inference.error_classification import (
    ProviderErrorMetadata,
    extract_anthropic_metadata,
    extract_azure_metadata,
    extract_bedrock_metadata,
    extract_fal_metadata,
    extract_gateway_metadata,
    extract_google_metadata,
    extract_huggingface_metadata,
    extract_linkup_metadata,
    extract_local_extract_metadata,
    extract_mistral_metadata,
    extract_openai_metadata,
)
from pipelex.cogt.inference.provider_name import ProviderName

# One ``extract_*_metadata`` function per provider. Local file extractors share
# ``extract_local_extract_metadata`` because they all surface builtin exceptions
# rather than SDK objects.
_PROVIDER_TO_EXTRACT_FN: dict[ProviderName, Callable[..., ProviderErrorMetadata]] = {
    ProviderName.OPENAI: extract_openai_metadata,
    ProviderName.ANTHROPIC: extract_anthropic_metadata,
    ProviderName.GOOGLE: extract_google_metadata,
    ProviderName.MISTRAL: extract_mistral_metadata,
    ProviderName.AZURE: extract_azure_metadata,
    ProviderName.BEDROCK: extract_bedrock_metadata,
    ProviderName.FAL: extract_fal_metadata,
    ProviderName.HUGGINGFACE: extract_huggingface_metadata,
    ProviderName.GATEWAY: extract_gateway_metadata,
    ProviderName.LINKUP: extract_linkup_metadata,
    ProviderName.DOCLING: extract_local_extract_metadata,
    ProviderName.PYPDFIUM2: extract_local_extract_metadata,
}


class TestProviderClassificationParity:
    """Walk the registry against the enum to catch unwired providers."""

    def test_every_provider_name_has_an_extract_fn(self) -> None:
        """Every ``ProviderName`` value must map to an ``extract_*_metadata`` function."""
        missing = sorted(provider for provider in ProviderName if provider not in _PROVIDER_TO_EXTRACT_FN)
        assert not missing, f"ProviderName values missing from _PROVIDER_TO_EXTRACT_FN: {missing}"

    @pytest.mark.parametrize("provider", list(ProviderName))
    def test_extract_fn_populates_envelope_for_each_provider(self, provider: ProviderName) -> None:
        """Each ``extract_*_metadata`` function must populate provider, sdk_exception_type, and message."""
        extract_fn = _PROVIDER_TO_EXTRACT_FN[provider]
        sentinel_exc = RuntimeError("synthetic SDK error for parity check")
        metadata = extract_fn(sentinel_exc, provider=provider) if provider.is_local_file_extractor else extract_fn(sentinel_exc)
        assert metadata.provider is provider
        assert metadata.sdk_exception_type == "RuntimeError"
        assert metadata.message == "synthetic SDK error for parity check"
