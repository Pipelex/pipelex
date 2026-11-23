"""The classifier reads a contributed service error code ahead of the status ladder, and the renderer gives its advice.

A service that refuses a request itself does so on statuses the ladder reads as a provider rejecting
the prompt. Its plugin's contributed code decides instead: the category, the action and the advice
are the entry's, and a model-not-found entry selects the family's `*ModelNotFoundError`. A process
with no vocabulary, or a code nobody contributed, falls through to the ladder unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.exceptions import ExtractJobFailureError, ExtractModelNotFoundError, InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserActionKind
from pipelex.cogt.inference.error_classify import InferenceErrorFamily, classify_inference_error
from pipelex.cogt.inference.error_render import render_inference_error
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.cogt.inference.service_error_vocabulary import ServiceErrorCode, ServiceErrorVocabulary
from pipelex.errors.problem import ProblemView

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_ACCESSOR = "pipelex.cogt.inference.error_classify.get_optional_service_error_vocabulary"

_TOO_LARGE = ServiceErrorCode(
    code="svc-too-large",
    category=InferenceErrorCategory.CONTENT,
    user_action_kind=UserActionKind.CHANGE_INPUT,
    error_code=CoreCode.INPUT_TOO_LARGE,
    detail="The request was over the service's limit — send less.",
)
_UNKNOWN_MODEL = ServiceErrorCode(
    code="svc-unknown-model",
    category=InferenceErrorCategory.CONFIGURATION,
    user_action_kind=UserActionKind.CHANGE_MODEL,
    error_code=CoreCode.MODEL_UNAVAILABLE,
    detail="The service does not serve that model.",
    is_model_not_found=True,
)
_NOT_CONFIGURED = ServiceErrorCode(
    code="svc-not-configured",
    category=InferenceErrorCategory.CONFIGURATION,
    user_action_kind=UserActionKind.CONTACT_SUPPORT,
    error_code=CoreCode.RUNTIME_MISCONFIGURED,
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

        classification = classify_inference_error(_metadata(status_code=400, code=entry.code), family=InferenceErrorFamily.LLM)

        assert classification.service_error_code == entry
        assert classification.category == entry.category
        assert classification.user_action_kind == entry.user_action_kind
        assert classification.is_model_not_found == entry.is_model_not_found
        assert classification.error_code == entry.error_code

    def test_it_runs_ahead_of_the_quota_rules(self, mocker: MockerFixture) -> None:
        """A 402 the quota rules would call billing is the service's own refusal when it carries a contributed code."""
        mocker.patch(_ACCESSOR, return_value=_vocabulary())

        classification = classify_inference_error(_metadata(status_code=402, code=_NOT_CONFIGURED.code), family=InferenceErrorFamily.LLM)

        assert classification.category == InferenceErrorCategory.CONFIGURATION
        assert classification.user_action_kind == UserActionKind.CONTACT_SUPPORT

    def test_a_code_nobody_contributed_takes_the_ladder(self, mocker: MockerFixture) -> None:
        mocker.patch(_ACCESSOR, return_value=_vocabulary())

        classification = classify_inference_error(_metadata(status_code=400, code="svc-unheard-of"), family=InferenceErrorFamily.LLM)

        assert classification.service_error_code is None
        assert classification.category == InferenceErrorCategory.CONTENT
        assert classification.user_action_kind == UserActionKind.CHANGE_INPUT

    @pytest.mark.parametrize("vocabulary", [None, ServiceErrorVocabulary({})], ids=["no-vocabulary", "empty-vocabulary"])
    def test_without_the_contribution_the_ladder_reads_the_status(self, mocker: MockerFixture, vocabulary: ServiceErrorVocabulary | None) -> None:
        mocker.patch(_ACCESSOR, return_value=vocabulary)

        classification = classify_inference_error(_metadata(status_code=400, code=_NOT_CONFIGURED.code), family=InferenceErrorFamily.LLM)

        assert classification.service_error_code is None
        assert classification.category == InferenceErrorCategory.CONTENT

    def test_a_statusless_failure_never_reads_the_vocabulary(self, mocker: MockerFixture) -> None:
        """A transport failure carries no code a service rendered; it stays a transient network error."""
        accessor = mocker.patch(_ACCESSOR, return_value=_vocabulary())
        metadata = ProviderErrorMetadata(provider=ProviderName.GATEWAY, sdk_exception_type="ConnectTimeout", message="timed out")

        classification = classify_inference_error(metadata, family=InferenceErrorFamily.LLM)

        assert classification.category == InferenceErrorCategory.TRANSIENT
        accessor.assert_not_called()


class TestRendering:
    def test_the_entry_s_advice_is_rendered(self, mocker: MockerFixture) -> None:
        mocker.patch(_ACCESSOR, return_value=_vocabulary())
        metadata = _metadata(status_code=413, code=_TOO_LARGE.code, message="body over 10 MB")

        error = render_inference_error(
            metadata=metadata,
            classification=classify_inference_error(metadata, family=InferenceErrorFamily.LLM),
            family=InferenceErrorFamily.LLM,
            model_desc="some-model",
            model_handle="some-model",
        )

        assert isinstance(error, LLMCompletionError)
        assert error.resolve_error_code() == CoreCode.INPUT_TOO_LARGE
        assert error.user_action is not None
        assert error.user_action.detail == _TOO_LARGE.detail
        assert error.error_category == InferenceErrorCategory.CONTENT
        assert "body over 10 MB" in str(error)

    def test_a_model_not_found_entry_selects_the_family_s_not_found_class(self, mocker: MockerFixture) -> None:
        mocker.patch(_ACCESSOR, return_value=_vocabulary())
        metadata = _metadata(status_code=400, code=_UNKNOWN_MODEL.code)

        error = render_inference_error(
            metadata=metadata,
            classification=classify_inference_error(metadata, family=InferenceErrorFamily.LLM),
            family=InferenceErrorFamily.EXTRACT,
            model_desc="some-model",
            model_handle="some-handle",
        )

        assert isinstance(error, ExtractModelNotFoundError)
        assert error.resolve_error_code() == CoreCode.MODEL_UNAVAILABLE
        assert error.user_action is not None
        assert error.user_action.detail == _UNKNOWN_MODEL.detail

    def test_an_entry_without_the_flag_renders_the_failure_class(self, mocker: MockerFixture) -> None:
        mocker.patch(_ACCESSOR, return_value=_vocabulary())
        metadata = _metadata(status_code=400, code=_NOT_CONFIGURED.code)

        error = render_inference_error(
            metadata=metadata,
            classification=classify_inference_error(metadata, family=InferenceErrorFamily.LLM),
            family=InferenceErrorFamily.EXTRACT,
            model_desc="some-model",
            model_handle="some-handle",
        )

        assert isinstance(error, ExtractJobFailureError)
        assert not isinstance(error, ExtractModelNotFoundError)
        assert error.resolve_error_code() == CoreCode.RUNTIME_MISCONFIGURED


_TOO_LARGE_WITH_FACTS = ServiceErrorCode(
    code="svc-files-too-large",
    category=InferenceErrorCategory.CONTENT,
    user_action_kind=UserActionKind.CHANGE_INPUT,
    error_code=CoreCode.INPUT_TOO_LARGE,
    detail="The files were over the provider's limit — use smaller files.",
    body_params={"input": "reference", "size": "size_bytes", "limit": "limit_bytes"},
)


def _render_with_body(mocker: MockerFixture, *, body: object) -> LLMCompletionError:
    mocker.patch(_ACCESSOR, return_value=ServiceErrorVocabulary({_TOO_LARGE_WITH_FACTS.code: _TOO_LARGE_WITH_FACTS}))
    metadata = ProviderErrorMetadata(
        provider=ProviderName.ANTHROPIC,
        sdk_exception_type="APIStatusError",
        message="the files add up to 26168984 bytes",
        status_code=413,
        provider_error_code=_TOO_LARGE_WITH_FACTS.code,
        body=body,
    )
    error = render_inference_error(
        metadata=metadata,
        classification=classify_inference_error(metadata, family=InferenceErrorFamily.LLM),
        family=InferenceErrorFamily.LLM,
        model_desc="some-model",
        model_handle="some-model",
    )
    assert isinstance(error, LLMCompletionError)
    return error


class TestParamsFromBody:
    def test_the_body_s_facts_render_the_code_s_sentence(self, mocker: MockerFixture) -> None:
        """A nested `error` section, as the Anthropic client keeps the body, gives the parameters the code's sentence names."""
        body = {
            "error": {"message": "too large", "code": "svc-files-too-large", "reference": "doc.pdf", "size_bytes": 26168984, "limit_bytes": 14999985}
        }

        problem = _render_with_body(mocker, body=body).to_problem(view=ProblemView.CALLER)

        assert problem.detail == "The input 'doc.pdf' reaches 26168984, past the limit of 14999985."
        assert problem.params is not None
        assert problem.params.as_wire() == {"input": "doc.pdf", "size": 26168984, "limit": 14999985}

    def test_a_top_level_field_is_read_where_the_openai_client_leaves_it(self, mocker: MockerFixture) -> None:
        body = {"message": "too large", "code": "svc-files-too-large", "reference": "doc.pdf", "size_bytes": 10, "limit_bytes": 5}

        error = _render_with_body(mocker, body=body)

        assert error.given_params == {"input": "doc.pdf", "size": 10, "limit": 5}

    @pytest.mark.parametrize(
        "body",
        [None, "not json", {"error": {"code": "svc-files-too-large"}}, {"error": {"reference": None, "size_bytes": None}}],
        ids=["no-body", "text-body", "no-facts", "null-facts"],
    )
    def test_a_body_without_the_facts_gives_no_parameters(self, mocker: MockerFixture, body: object) -> None:
        error = _render_with_body(mocker, body=body)

        assert error.given_params == {}

    def test_an_entry_reading_none_gives_none(self) -> None:
        assert _TOO_LARGE.params_from_body(body={"error": {"reference": "doc.pdf"}}) == {}

    def test_an_empty_string_is_left_out_like_null(self) -> None:
        assert _TOO_LARGE_WITH_FACTS.params_from_body(body={"error": {"reference": "", "size_bytes": 10}}) == {"size": 10}

    def test_a_model_not_found_entry_reads_nothing_from_the_body(self) -> None:
        with pytest.raises(ValueError, match="whose parameters the runtime states"):
            ServiceErrorCode(
                code="svc-nf",
                category=InferenceErrorCategory.CONFIGURATION,
                user_action_kind=UserActionKind.CHANGE_MODEL,
                error_code=CoreCode.MODEL_UNAVAILABLE,
                detail="advice",
                is_model_not_found=True,
                body_params={"model": "model_id"},
            )

    @pytest.mark.parametrize(
        ("error_code", "body_params", "named"),
        [
            (CoreCode.MODEL_CONTEXT_EXCEEDED, {"limit": "lim", "count": "n"}, "limit"),
            (CoreCode.MODEL_CONTEXT_EXCEEDED, {"model": "model_id"}, "model"),
        ],
    )
    def test_a_parameter_the_runtime_states_is_refused(self, error_code: CoreCode, body_params: dict[str, str], named: str) -> None:
        with pytest.raises(ValueError, match=f"reads {named} from the error body, which the runtime states itself"):
            ServiceErrorCode(
                code="svc-owned",
                category=InferenceErrorCategory.CONTENT,
                user_action_kind=UserActionKind.CHANGE_INPUT,
                error_code=error_code,
                detail="advice",
                body_params=body_params,
            )

    def test_an_entry_naming_a_parameter_its_code_does_not_declare_is_refused(self) -> None:
        with pytest.raises(ValueError, match="does not declare"):
            ServiceErrorCode(
                code="svc-bad",
                category=InferenceErrorCategory.CONTENT,
                user_action_kind=UserActionKind.CHANGE_INPUT,
                error_code=CoreCode.INPUT_TOO_LARGE,
                detail="advice",
                body_params={"host": "host"},
            )
