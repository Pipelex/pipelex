"""Tests for Bedrock LLM worker provider_metadata + semantic UserActionKind."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.providers.bedrock.bedrock_llm_worker import BedrockLLMWorker


def _make_bedrock_client_error(error_code: str, error_message: str, status_code: int | None = None, request_id: str | None = None) -> ClientError:
    response: dict[str, Any] = {"Error": {"Code": error_code, "Message": error_message}}
    metadata: dict[str, Any] = {}
    if status_code is not None:
        metadata["HTTPStatusCode"] = status_code
    if request_id is not None:
        metadata["RequestId"] = request_id
    if metadata:
        response["ResponseMetadata"] = metadata
    return ClientError(error_response=cast("Any", response), operation_name="Converse")


def _make_worker(mocker: MockerFixture) -> BedrockLLMWorker:
    worker = object.__new__(BedrockLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "anthropic.claude-3"
    mock_model.name = "anthropic.claude-3"
    mock_model.thinking_mode = None
    mock_model.max_tokens = 4096
    worker.inference_model = mock_model
    worker.default_max_tokens = 4096

    mock_client = mocker.MagicMock()
    mock_client.chat = mocker.AsyncMock()
    worker.bedrock_client_for_text = mock_client
    return worker


def _make_llm_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.applied_job_params = None
    job.job_params.temperature = 0.5
    job.job_params.max_tokens = None
    job.job_params.reasoning_effort = None
    job.job_params.reasoning_budget = None
    job.job_report.llm_tokens_usage = None
    job.llm_prompt.system_text = "system"
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestBedrockWorkerSemantic:
    """Each Bedrock ClientError branch carries semantic UserActionKind + provider_metadata."""

    @pytest.mark.parametrize(
        ("error_code", "error_message", "status_code", "expected_category", "expected_kind"),
        [
            ("ServiceQuotaExceededException", "Quota exceeded", 400, InferenceErrorCategory.CAPACITY, UserActionKind.CHECK_BILLING),
            ("ThrottlingException", "Quota limit exceeded for this account", 429, InferenceErrorCategory.CAPACITY, UserActionKind.CHECK_BILLING),
            ("ThrottlingException", "Rate exceeded", 429, InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
            ("AccessDeniedException", "Not authorized", 403, InferenceErrorCategory.CONFIGURATION, UserActionKind.CHECK_CREDENTIALS),
            ("ValidationException", "Invalid request", 400, InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
            ("ModelNotReadyException", "Model not ready", 503, InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
            ("ServiceUnavailableException", "Service unavailable", 503, InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
            # Unhandled error code on a 4xx status: non-retryable client error, not TRANSIENT.
            ("UnknownAWSException", "Mystery client failure", 409, InferenceErrorCategory.CONFIGURATION, UserActionKind.CHANGE_INPUT),
            ("UnknownAWSException", "Mystery failure", 500, InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
        ],
    )
    async def test_client_error_carries_semantic_user_action(
        self,
        mocker: MockerFixture,
        error_code: str,
        error_message: str,
        status_code: int,
        expected_category: InferenceErrorCategory,
        expected_kind: UserActionKind,
    ) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_bedrock_client_error(error_code, error_message, status_code=status_code, request_id="aws-req-1")
        worker.bedrock_client_for_text.chat.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mock_message = mocker.MagicMock()
        mock_message.to_dict_list = mocker.MagicMock(return_value=[{"role": "user", "content": "test"}])
        mocker.patch(
            "pipelex.providers.bedrock.bedrock_llm_worker.BedrockFactory.make_simple_message",
            return_value=mock_message,
        )

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is expected_kind
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.provider == "bedrock"
        assert exc_info.value.provider_metadata.sdk_exception_type == "ClientError"
        assert exc_info.value.provider_metadata.status_code == status_code
        assert exc_info.value.provider_metadata.request_id == "aws-req-1"
        assert exc_info.value.provider_metadata.provider_error_code == error_code
        assert exc_info.value.__cause__ is sdk_exc

    async def test_resource_not_found_raises_llm_model_not_found_error(self, mocker: MockerFixture) -> None:
        """A ResourceNotFoundException specializes to LLMModelNotFoundError (CONFIGURATION, CHANGE_MODEL)."""
        worker = _make_worker(mocker)
        sdk_exc = _make_bedrock_client_error("ResourceNotFoundException", "Model not found", status_code=404, request_id="aws-req-1")
        worker.bedrock_client_for_text.chat.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mock_message = mocker.MagicMock()
        mock_message.to_dict_list = mocker.MagicMock(return_value=[{"role": "user", "content": "test"}])
        mocker.patch(
            "pipelex.providers.bedrock.bedrock_llm_worker.BedrockFactory.make_simple_message",
            return_value=mock_message,
        )

        with pytest.raises(LLMModelNotFoundError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        assert exc_info.value.model_handle == "anthropic.claude-3"
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 404
        assert exc_info.value.__cause__ is sdk_exc
