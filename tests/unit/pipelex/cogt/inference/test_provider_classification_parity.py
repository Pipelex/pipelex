"""Meta-test: every ``ProviderName`` is wired into the Extract step.

Adding a new ``ProviderName`` enum value without a matching ``extract_*_metadata``
function would let the worker compile but produce a useless metadata envelope.
This test fails fast in that case by walking the enum against a registry.
"""

from collections.abc import Callable

import pytest
from pydantic import BaseModel, ValidationError

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
    extract_typesafe_metadata,
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
    ProviderName.TYPESAFE: extract_typesafe_metadata,
    ProviderName.DOCLING: extract_local_extract_metadata,
    ProviderName.PYPDFIUM2: extract_local_extract_metadata,
}


class _Verdict(BaseModel):
    """A structure a model's answer must fit, as instructor validates it."""

    score: int


# The model's answer, which a ValidationError's own text quotes and no metadata message may carry.
_MODEL_ANSWER = "zebra-quartz-ledger-5521"


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

    @pytest.mark.parametrize("provider", list(ProviderName))
    def test_extract_fn_writes_a_refused_answer_without_the_answer(self, provider: ProviderName) -> None:
        """The validation error that ends instructor's re-asks quotes the model's answer, which the message never carries."""
        extract_fn = _PROVIDER_TO_EXTRACT_FN[provider]
        with pytest.raises(ValidationError) as refusal:
            _Verdict.model_validate({"score": _MODEL_ANSWER})
        assert _MODEL_ANSWER in str(refusal.value)

        validation_error = refusal.value
        metadata = extract_fn(validation_error, provider=provider) if provider.is_local_file_extractor else extract_fn(validation_error)

        assert metadata.message == "score: Input should be a valid integer, unable to parse string as an integer"
