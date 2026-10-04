"""The classifier reads a contributed service error code ahead of the status ladder, and the renderer gives its advice.

A service that refuses a request itself does so on statuses the ladder reads as a provider rejecting
the prompt. Its plugin's contributed code decides instead: the category, the action and the advice
are the entry's, and a model-not-found entry selects the family's `*ModelNotFoundError`. A process
with no vocabulary, or a code nobody contributed, falls through to the ladder unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.exceptions import ExtractJobFailureError, ExtractModelNotFoundError, InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserActionKind
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.cogt.inference.service_error_vocabulary import ServiceErrorCode, ServiceErrorVocabulary

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_ACCESSOR = "pipelex.cogt.inference.error_classify.get_optional_service_error_vocabulary"

_TOO_LARGE = ServiceErrorCode(
    code="svc-too-large",
    category=InferenceErrorCategory.CONTENT,
    user_action_kind=UserActionKind.CHANGE_INPUT,
    detail="The request was over the service's limit — send less.",
)
_UNKNOWN_MODEL = ServiceErrorCode(
    code="svc-unknown-model",
    category=InferenceErrorCategory.CONFIGURATION,
    user_action_kind=UserActionKind.CHANGE_MODEL,
    detail="The service does not serve that model.",
    is_model_not_found=True,
)
_NOT_CONFIGURED = ServiceErrorCode(
    code="svc-not-configured",
    category=InferenceErrorCategory.CONFIGURATION,
    user_action_kind=UserActionKind.CONTACT_SUPPORT,
    detail="The service is not configured for this — contact support.",
)


def _vocabulary() -> ServiceErrorVocabulary:
    return ServiceErrorVocabulary({entry.code: entry for entry in (_TOO_LARGE, _UNKNOWN_MODEL, _NOT_CONFIGURED)})


def _metadata(*, status_code: int | None, code: str | None, message: str = "refused") -> ProviderErrorMetadata:
    return ProviderErrorMetadata(
        provider=ProviderName.GATEWAY,
        sdk_exception_type="HTTPStatusError",
        message=message,
        status_code=status_code,
        provider_error_code=code,
    )


class TestClassification:
    @pytest.mark.parametrize("entry", [_TOO_LARGE, _UNKNOWN_MODEL, _NOT_CONFIGURED], ids=lambda entry: entry.code)
    def test_a_contributed_code_decides_ahead_of_the_ladder(self, mocker: MockerFixture, entry: ServiceErrorCode) -> None:
        mocker.patch(_ACCESSOR, return_value=_vocabulary())

        classification = classify_inference_error(_metadata(status_code=400, code=entry.code))

        assert classification.service_error_code == entry
        assert classification.category == entry.category
        assert classification.user_action_kind == entry.user_action_kind
        assert classification.is_model_not_found == entry.is_model_not_found

    def test_it_runs_ahead_of_the_quota_rules(self, mocker: MockerFixture) -> None:
        """A 402 the quota rules would call billing is the service's own refusal when it carries a contributed code."""
        mocker.patch(_ACCESSOR, return_value=_vocabulary())

        classification = classify_inference_error(_metadata(status_code=402, code=_NOT_CONFIGURED.code))

        assert classification.category == InferenceErrorCategory.CONFIGURATION
        assert classification.user_action_kind == UserActionKind.CONTACT_SUPPORT

    def test_a_code_nobody_contributed_takes_the_ladder(self, mocker: MockerFixture) -> None:
        mocker.patch(_ACCESSOR, return_value=_vocabulary())

        classification = classify_inference_error(_metadata(status_code=400, code="svc-unheard-of"))

        assert classification.service_error_code is None
        assert classification.category == InferenceErrorCategory.CONTENT
        assert classification.user_action_kind == UserActionKind.CHANGE_INPUT

    @pytest.mark.parametrize("vocabulary", [None, ServiceErrorVocabulary({})], ids=["no-vocabulary", "empty-vocabulary"])
    def test_without_the_contribution_the_ladder_reads_the_status(self, mocker: MockerFixture, vocabulary: ServiceErrorVocabulary | None) -> None:
        mocker.patch(_ACCESSOR, return_value=vocabulary)

        classification = classify_inference_error(_metadata(status_code=400, code=_NOT_CONFIGURED.code))

        assert classification.service_error_code is None
        assert classification.category == InferenceErrorCategory.CONTENT

    def test_a_statusless_failure_never_reads_the_vocabulary(self, mocker: MockerFixture) -> None:
        """A transport failure carries no code a service rendered; it stays a transient network error."""
        accessor = mocker.patch(_ACCESSOR, return_value=_vocabulary())
        metadata = ProviderErrorMetadata(provider=ProviderName.GATEWAY, sdk_exception_type="ConnectTimeout", message="timed out")

        classification = classify_inference_error(metadata)

        assert classification.category == InferenceErrorCategory.TRANSIENT
        accessor.assert_not_called()


class TestRendering:
    def test_the_entry_s_advice_is_rendered(self, mocker: MockerFixture) -> None:
        mocker.patch(_ACCESSOR, return_value=_vocabulary())
        metadata = _metadata(status_code=413, code=_TOO_LARGE.code, message="body over 10 MB")

        error = render_inference_error(
            metadata=metadata,
            classification=classify_inference_error(metadata),
            family=InferenceErrorFamily.LLM,
            model_desc="some-model",
            model_handle="some-model",
        )

        assert isinstance(error, LLMCompletionError)
        assert error.user_action is not None
        assert error.user_action.detail == _TOO_LARGE.detail
        assert error.error_category == InferenceErrorCategory.CONTENT
        assert "body over 10 MB" in str(error)

    def test_a_model_not_found_entry_selects_the_family_s_not_found_class(self, mocker: MockerFixture) -> None:
        mocker.patch(_ACCESSOR, return_value=_vocabulary())
        metadata = _metadata(status_code=400, code=_UNKNOWN_MODEL.code)

        error = render_inference_error(
            metadata=metadata,
            classification=classify_inference_error(metadata),
            family=InferenceErrorFamily.EXTRACT,
            model_desc="some-model",
            model_handle="some-handle",
        )

        assert isinstance(error, ExtractModelNotFoundError)
        assert error.user_action is not None
        assert error.user_action.detail == _UNKNOWN_MODEL.detail

    def test_an_entry_without_the_flag_renders_the_failure_class(self, mocker: MockerFixture) -> None:
        mocker.patch(_ACCESSOR, return_value=_vocabulary())
        metadata = _metadata(status_code=400, code=_NOT_CONFIGURED.code)

        error = render_inference_error(
            metadata=metadata,
            classification=classify_inference_error(metadata),
            family=InferenceErrorFamily.EXTRACT,
            model_desc="some-model",
            model_handle="some-handle",
        )

        assert isinstance(error, ExtractJobFailureError)
        assert not isinstance(error, ExtractModelNotFoundError)
