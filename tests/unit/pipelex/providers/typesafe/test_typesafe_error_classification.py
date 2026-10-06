import pytest
from httpx2 import Headers
from typesafe_sdk import TypeSafeAPIError, TypeSafeAuthenticationError, TypeSafeInternalServerError, TypeSafeRateLimitError

from pipelex.cogt.exceptions import InferenceErrorCategory, JudgmentJobFailureError, JudgmentModelNotFoundError
from pipelex.cogt.inference.error_classification import (
    TYPESAFE_API_USAGE_ERROR_TYPE,
    TYPESAFE_AUTHENTICATION_ERROR_TYPE,
    TYPESAFE_MALFORMED_REQUEST_CODE,
    TYPESAFE_MAX_TOKENS_EXCEEDED_ERROR_TYPE,
    UserActionKind,
    extract_typesafe_metadata,
)
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.providers.typesafe.typesafe_error_classification import classify_typesafe_error
from tests.unit.pipelex.providers.typesafe.test_data import TestData, rebuild_recorded_exception


class TestTypesafeErrorClassification:
    @pytest.mark.parametrize(
        ("recorded", "status_code", "provider_error_code", "category", "user_action_kind", "is_model_not_found"),
        [
            pytest.param(
                TestData.WRONG_KEY,
                401,
                TYPESAFE_AUTHENTICATION_ERROR_TYPE,
                InferenceErrorCategory.CONFIGURATION,
                UserActionKind.CHECK_CREDENTIALS,
                False,
                id="wrong_key_is_credentials",
            ),
            pytest.param(
                TestData.STATE_TOO_LARGE,
                400,
                TYPESAFE_MAX_TOKENS_EXCEEDED_ERROR_TYPE,
                InferenceErrorCategory.CONTENT,
                UserActionKind.CHANGE_INPUT,
                False,
                id="oversized_state_is_the_callers_content",
            ),
            pytest.param(
                TestData.UNKNOWN_MODEL,
                400,
                TYPESAFE_API_USAGE_ERROR_TYPE,
                InferenceErrorCategory.CONFIGURATION,
                UserActionKind.CHANGE_MODEL,
                True,
                id="unknown_model_is_a_missing_model",
            ),
            pytest.param(
                TestData.MALFORMED_QUESTION,
                400,
                TYPESAFE_MALFORMED_REQUEST_CODE,
                InferenceErrorCategory.CONFIGURATION,
                UserActionKind.CONTACT_SUPPORT,
                False,
                id="illegal_question_is_a_pipelex_defect",
            ),
            pytest.param(
                TestData.TOO_MANY_LEVELS,
                400,
                TYPESAFE_MALFORMED_REQUEST_CODE,
                InferenceErrorCategory.CONFIGURATION,
                UserActionKind.CONTACT_SUPPORT,
                False,
                id="scale_past_the_cap_is_a_pipelex_defect",
            ),
            pytest.param(
                TestData.EMPTY_QUESTIONS,
                None,
                None,
                InferenceErrorCategory.CONFIGURATION,
                UserActionKind.CONTACT_SUPPORT,
                False,
                id="client_side_refusal_is_a_pipelex_defect",
            ),
            pytest.param(
                TestData.TIMEOUT,
                None,
                None,
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
                False,
                id="timeout_is_transient",
            ),
        ],
    )
    def test_each_recorded_refusal_gets_its_own_verdict(
        self,
        recorded: str,
        status_code: int | None,
        provider_error_code: str | None,
        category: InferenceErrorCategory,
        user_action_kind: UserActionKind,
        is_model_not_found: bool,
    ) -> None:
        """Four different verdicts share status 400 on this API, and only the body tells them apart."""
        metadata = extract_typesafe_metadata(rebuild_recorded_exception(recorded))
        classification = classify_typesafe_error(metadata)

        assert metadata.provider is ProviderName.TYPESAFE
        assert metadata.status_code == status_code
        assert metadata.provider_error_code == provider_error_code
        assert classification.category is category
        assert classification.user_action_kind is user_action_kind
        assert classification.is_model_not_found is is_model_not_found

    @pytest.mark.parametrize(
        ("exception", "category", "user_action_kind"),
        [
            pytest.param(
                TypeSafeRateLimitError(status=429, body={"detail": "Rate limit exceeded"}, headers=Headers()),
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
                id="rate_limit",
            ),
            pytest.param(
                TypeSafeInternalServerError(status=503, body={"detail": "Service Unavailable"}, headers=Headers()),
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
                id="unavailable",
            ),
            pytest.param(
                TypeSafeAuthenticationError(status=401, body={"detail": "Not authenticated"}, headers=Headers()),
                InferenceErrorCategory.CONFIGURATION,
                UserActionKind.CHECK_CREDENTIALS,
                id="unauthenticated",
            ),
        ],
    )
    def test_a_bare_sentence_off_a_400_goes_to_the_status_ladder(
        self,
        exception: TypeSafeAPIError,
        category: InferenceErrorCategory,
        user_action_kind: UserActionKind,
    ) -> None:
        """Only a `400` with a bare-sentence detail is a malformed request; any other status keeps its own verdict."""
        metadata = extract_typesafe_metadata(exception)
        classification = classify_typesafe_error(metadata)

        assert metadata.provider_error_code is None
        assert classification.category is category
        assert classification.user_action_kind is user_action_kind

    def test_a_rate_limit_carries_its_retry_after(self) -> None:
        exception = TypeSafeRateLimitError(status=429, body={"detail": "Rate limit exceeded"}, headers=Headers({"retry-after": "3"}))
        assert extract_typesafe_metadata(exception).retry_after_seconds == 3.0

    def test_an_api_error_carries_its_request_id(self) -> None:
        """On the error path the request id is a plain attribute, read without the guard the success path needs."""
        metadata = extract_typesafe_metadata(rebuild_recorded_exception(TestData.UNKNOWN_MODEL))
        assert metadata.request_id == "req_01a0b97aa532770083aece1331cb7c76"

    def test_a_client_side_refusal_has_no_request_id(self) -> None:
        metadata = extract_typesafe_metadata(rebuild_recorded_exception(TestData.EMPTY_QUESTIONS))
        assert metadata.request_id is None
        assert metadata.sdk_exception_type == "TypeSafeError"

    @pytest.mark.parametrize(
        ("recorded", "expected_class"),
        [
            pytest.param(TestData.UNKNOWN_MODEL, JudgmentModelNotFoundError, id="unknown_model"),
            pytest.param(TestData.STATE_TOO_LARGE, JudgmentJobFailureError, id="state_too_large"),
        ],
    )
    def test_the_verdict_selects_the_judgment_family_class(self, recorded: str, expected_class: type[Exception]) -> None:
        """An unknown model renders as the family's model-not-found error; every other refusal as its job failure."""
        metadata = extract_typesafe_metadata(rebuild_recorded_exception(recorded))
        rendered = render_inference_error(
            metadata=metadata,
            classification=classify_typesafe_error(metadata),
            family=InferenceErrorFamily.JUDGMENT,
            model_desc="jev-does-not-exist",
            model_handle="jev-does-not-exist",
        )
        assert type(rendered) is expected_class
