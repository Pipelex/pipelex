"""Tests for Bedrock worker ClientError exception handling and error categorization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.plugins.bedrock.bedrock_llm_worker import BedrockLLMWorker
from tests.unit.pipelex.plugins.bedrock.test_data import BedrockLLMErrorHandlingTestData


def _make_bedrock_client_error(error_code: str, error_message: str) -> ClientError:
    """Create a botocore ClientError with the given error code and message."""
    return ClientError(
        error_response={"Error": {"Code": error_code, "Message": error_message}},
        operation_name="Converse",
    )


def _make_bedrock_llm_worker(mocker: MockerFixture) -> BedrockLLMWorker:
    """Create a minimal BedrockLLMWorker with mocked internals."""
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
    """Create a mock LLM job."""
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
class TestBedrockWorkerErrorHandling:
    """Tests for Bedrock worker ClientError exception handling and error categorization."""

    # ---- ClientError tests ----

    @pytest.mark.parametrize(
        ("_topic", "error_code", "error_message", "expected_category", "expected_action_substring"),
        BedrockLLMErrorHandlingTestData.CLIENT_ERROR_CASES,
    )
    async def test_client_error_classification(
        self,
        mocker: MockerFixture,
        _topic: str,
        error_code: str,
        error_message: str,
        expected_category: InferenceErrorCategory,
        expected_action_substring: str | None,
    ) -> None:
        """ClientError is caught and categorized correctly by the Bedrock LLM worker."""
        worker = _make_bedrock_llm_worker(mocker)
        sdk_exc = _make_bedrock_client_error(error_code, error_message)
        worker.bedrock_client_for_text.chat.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        # Patch BedrockFactory.make_simple_message to return a mock
        mock_message = mocker.MagicMock()
        mock_message.to_dict_list = mocker.MagicMock(return_value=[{"role": "user", "content": "test"}])
        mocker.patch(
            "pipelex.plugins.bedrock.bedrock_llm_worker.BedrockFactory.make_simple_message",
            return_value=mock_message,
        )

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        if expected_action_substring:
            assert exc_info.value.user_action is not None
            assert expected_action_substring in exc_info.value.user_action.detail.lower()

    # ---- to_error_report() integration ----

    async def test_error_report_transient_is_retryable(self, mocker: MockerFixture) -> None:
        """to_error_report() for TRANSIENT Bedrock errors has retryable=True."""
        worker = _make_bedrock_llm_worker(mocker)
        sdk_exc = _make_bedrock_client_error("ThrottlingException", "Rate exceeded for model")
        worker.bedrock_client_for_text.chat.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mock_message = mocker.MagicMock()
        mock_message.to_dict_list = mocker.MagicMock(return_value=[{"role": "user", "content": "test"}])
        mocker.patch(
            "pipelex.plugins.bedrock.bedrock_llm_worker.BedrockFactory.make_simple_message",
            return_value=mock_message,
        )

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "transient"
        assert report.retryable is True
        assert report.error_type == "LLMCompletionError"

    async def test_error_report_capacity_not_retryable(self, mocker: MockerFixture) -> None:
        """to_error_report() for CAPACITY Bedrock errors has retryable=False."""
        worker = _make_bedrock_llm_worker(mocker)
        sdk_exc = _make_bedrock_client_error("ServiceQuotaExceededException", "Service quota exceeded")
        worker.bedrock_client_for_text.chat.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mock_message = mocker.MagicMock()
        mock_message.to_dict_list = mocker.MagicMock(return_value=[{"role": "user", "content": "test"}])
        mocker.patch(
            "pipelex.plugins.bedrock.bedrock_llm_worker.BedrockFactory.make_simple_message",
            return_value=mock_message,
        )

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "capacity"
        assert report.retryable is False

    async def test_error_report_configuration_not_retryable(self, mocker: MockerFixture) -> None:
        """to_error_report() for CONFIGURATION Bedrock errors has retryable=False."""
        worker = _make_bedrock_llm_worker(mocker)
        sdk_exc = _make_bedrock_client_error("AccessDeniedException", "Access denied")
        worker.bedrock_client_for_text.chat.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mock_message = mocker.MagicMock()
        mock_message.to_dict_list = mocker.MagicMock(return_value=[{"role": "user", "content": "test"}])
        mocker.patch(
            "pipelex.plugins.bedrock.bedrock_llm_worker.BedrockFactory.make_simple_message",
            return_value=mock_message,
        )

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "configuration"
        assert report.retryable is False
