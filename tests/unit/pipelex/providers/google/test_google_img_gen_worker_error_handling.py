"""Tests for Google ImgGen worker provider_metadata + semantic UserActionKind values.

The existing ``test_google_worker_error_handling.py`` covers categorization on both
LLM and ImgGen workers. This module adds the upgrade-A/B/C assertions for the
ImgGen worker specifically: provider_metadata population + semantic UserActionKind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from google.genai import errors as genai_errors

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenModelNotFoundError, InferenceErrorCategory, find_inference_error_category_in_chain
from pipelex.cogt.img_gen.img_gen_gemini_mapping import ResolvedGeminiImageConfig
from pipelex.cogt.img_gen.img_gen_model_rules import AspectRatioTaxonomy, ImgGenArgTopic
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.errors.problem import PipelexProblem, ProblemDiagnostics, ProblemView, ProviderDiagnostics
from pipelex.providers.google.google_img_gen_worker import GoogleImgGenWorker
from tests.unit.pipelex.cogt.test_data import DirectProviderQuotaTestData


def _make_google_client_error(code: int, message: str, status: str = "ERROR") -> genai_errors.ClientError:
    response_json = {"message": message, "status": status, "error": {"status": status, "code": code, "message": message}}
    return genai_errors.ClientError(code, response_json, None)


def _make_google_server_error(code: int, message: str) -> genai_errors.ServerError:
    response_json = {"message": message, "status": "INTERNAL"}
    return genai_errors.ServerError(code, response_json, None)


def _make_worker(mocker: MockerFixture) -> GoogleImgGenWorker:
    worker = object.__new__(GoogleImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "imagen-3.0-generate-002"
    mock_model.name = "imagen-3.0-generate-002"
    mock_model.rules = {ImgGenArgTopic.ASPECT_RATIO: AspectRatioTaxonomy.GEMINI_3_FLASH}
    worker.inference_model = mock_model

    mock_async_client = mocker.MagicMock()
    mock_async_client.models.generate_content = mocker.AsyncMock()
    worker.genai_async_client = mock_async_client

    mocker.patch(
        "pipelex.providers.google.google_img_gen_worker.ImgGenGeminiMapping.resolve_image_config",
        return_value=ResolvedGeminiImageConfig(aspect_ratio="1:1", image_size=None, width=1024, height=1024),
    )
    return worker


def _make_img_gen_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.job_params.aspect_ratio = None
    job.job_params.output_format = None
    job.img_gen_prompt.positive_text = "a cute cat"
    job.job_report.img_gen_tokens_usage = None
    return job


def _diagnostics_of(problem: PipelexProblem) -> ProblemDiagnostics:
    """The operator's diagnostics of a problem built in the operator view."""
    assert problem.diagnostics is not None
    return problem.diagnostics


def _provider_of(problem: PipelexProblem) -> ProviderDiagnostics:
    """What the provider answered, from the operator's diagnostics."""
    provider = _diagnostics_of(problem).provider
    assert provider is not None
    return provider


@pytest.mark.asyncio(loop_scope="class")
class TestGoogleImgGenWorkerErrorHandling:
    """Asserts metadata + user_action.kind for every classification branch."""

    async def test_not_found_404_is_change_model_with_metadata(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_google_client_error(404, "Model gemini-99 not found", status="NOT_FOUND")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenModelNotFoundError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        assert exc_info.value.model_handle == "imagen-3.0-generate-002"
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 404
        assert exc_info.value.provider_metadata.provider == "google"

    async def test_auth_401_is_check_credentials(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_google_client_error(401, "Invalid credentials", status="UNAUTHENTICATED")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_CREDENTIALS
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 401

    async def test_forbidden_403_is_check_credentials(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_google_client_error(403, "Permission denied", status="PERMISSION_DENIED")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_CREDENTIALS

    async def test_per_minute_throttle_whose_words_name_a_quota_waits_its_delay(self, mocker: MockerFixture) -> None:
        """Gemini's throttle says "quota" and "billing" and is a rate limit, carrying the wait its `RetryInfo` asks for."""
        worker = _make_worker(mocker)
        sdk_exc = genai_errors.ClientError(429, DirectProviderQuotaTestData.GOOGLE_PER_MINUTE_THROTTLE_BODY, None)
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.retry_after_seconds == DirectProviderQuotaTestData.GOOGLE_RETRY_DELAY_SECONDS

    async def test_prepay_depleted_402_is_check_billing(self, mocker: MockerFixture) -> None:
        """Gemini answers a Prepay balance at zero with a 402, a spent quota by its status."""
        worker = _make_worker(mocker)
        sdk_exc = genai_errors.ClientError(402, DirectProviderQuotaTestData.GOOGLE_PREPAY_DEPLETED_BODY, None)
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CAPACITY
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_BILLING

    async def test_generic_rate_limit_429_is_wait_and_retry(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_google_client_error(429, "Too many requests, please slow down")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY

    async def test_content_policy_400_is_change_input(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_google_client_error(400, "Your request was rejected due to content_policy_violation")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONTENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT

    async def test_generic_400_is_change_input(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_google_client_error(400, "Invalid parameter: temperature must be between 0 and 2")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONTENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT

    async def test_unhandled_4xx_is_change_input(self, mocker: MockerFixture) -> None:
        """A ClientError with an unhandled 4xx status is non-retryable CONFIGURATION, not TRANSIENT."""
        worker = _make_worker(mocker)
        sdk_exc = _make_google_client_error(409, "Conflict: resource already exists")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT

    async def test_server_error_500_is_an_unknown_outcome(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_google_server_error(500, "Internal server error")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.AMBIGUOUS
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 500

    @pytest.mark.parametrize(
        ("exc_class", "expected_sdk_type", "expected_category"),
        [
            # Never sent: the connection was not opened, so the image was not generated.
            (httpx.ConnectError, "ConnectError", InferenceErrorCategory.TRANSIENT),
            (httpx.ConnectTimeout, "ConnectTimeout", InferenceErrorCategory.TRANSIENT),
            # Dropped after the request left: the image may exist and be billed.
            (httpx.ReadError, "TransportError", InferenceErrorCategory.AMBIGUOUS),
            (httpx.RemoteProtocolError, "TransportError", InferenceErrorCategory.AMBIGUOUS),
        ],
    )
    async def test_httpx_transport_error_is_wrapped_by_whether_it_was_sent(
        self,
        mocker: MockerFixture,
        exc_class: type[httpx.TransportError],
        expected_sdk_type: str,
        expected_category: InferenceErrorCategory,
    ) -> None:
        """A direct httpx.TransportError from generate_content() is caught and routed through the categorizer as an
        ImgGenGenerationError: transient when the request was never sent, an unknown outcome when it may have been.
        """
        worker = _make_worker(mocker)
        request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1/models/imagen-3.0-generate-002:generateContent")
        sdk_exc = exc_class("transport failure", request=request)
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.provider == "google"
        assert exc_info.value.provider_metadata.status_code is None
        assert exc_info.value.provider_metadata.sdk_exception_type == expected_sdk_type
        assert exc_info.value.__cause__ is sdk_exc

    @pytest.mark.builds_problems_without_required_params(
        reason="calls the worker below its public method, whose enrichment names the model and the provider"
    )
    async def test_the_operator_problem_carries_the_provider_facts(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_google_client_error(429, "Resource has been exhausted", status="RESOURCE_EXHAUSTED")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        problem = error.to_problem(view=ProblemView.OPERATOR)
        assert find_inference_error_category_in_chain(error) == "transient"
        assert problem.is_retryable is True
        # The provider's `name` is the backend the error names, which the worker leaves to its caller to fill.
        assert _provider_of(problem).name is None
        assert _provider_of(problem).status == 429
