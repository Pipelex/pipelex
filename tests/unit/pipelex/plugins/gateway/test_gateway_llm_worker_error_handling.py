from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

import httpx
import openai
import pytest

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.gateway.gateway_completions_llm_worker import GatewayCompletionsLLMWorker
from pipelex.plugins.gateway.gateway_responses_llm_worker import GatewayResponsesLLMWorker

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_GatewayLLMWorker: TypeAlias = GatewayCompletionsLLMWorker | GatewayResponsesLLMWorker


def _openai_not_found(message: str) -> openai.NotFoundError:
    """Build an openai.NotFoundError whose str() carries the given 404 body text."""
    request = httpx.Request("POST", "https://gateway.test/v1/chat/completions")
    response = httpx.Response(status_code=404, request=request)
    return openai.NotFoundError(message, response=response, body=None)


def _make_gateway_worker(worker_class: type[_GatewayLLMWorker], mocker: MockerFixture) -> _GatewayLLMWorker:
    """Build a gateway LLM worker bypassing __init__ — _classify_sdk_error only needs inference_model."""
    worker = object.__new__(worker_class)
    mock_model = mocker.MagicMock()
    mock_model.desc = "gpt-4o @ pipelex_gateway"
    mock_model.model_id = "gpt-4o"
    mock_model.name = "gpt-4o-handle"
    worker.inference_model = mock_model
    return worker


@pytest.mark.parametrize("worker_class", [GatewayCompletionsLLMWorker, GatewayResponsesLLMWorker])
class TestGatewayLLMWorkerErrorHandling:
    def test_propagation_race_404_demoted_to_transient(
        self,
        worker_class: type[_GatewayLLMWorker],
        mocker: MockerFixture,
    ) -> None:
        """A 404 carrying the deployment-propagation-race phrase becomes a retryable TRANSIENT
        LLMCompletionError instead of the permanent LLMModelNotFoundError the shared classifier gives.
        """
        worker = _make_gateway_worker(worker_class, mocker)
        sdk_exc = _openai_not_found("Error code: 404 - the specified deployment could not be found")

        result = worker._classify_sdk_error(sdk_exc=sdk_exc)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert isinstance(result, LLMCompletionError)
        assert not isinstance(result, LLMModelNotFoundError)
        assert result.error_category is InferenceErrorCategory.TRANSIENT
        assert result.error_category.is_retryable is True
        assert result.user_action is not None
        assert result.user_action.kind is UserActionKind.WAIT_AND_RETRY

    def test_genuine_404_stays_model_not_found(
        self,
        worker_class: type[_GatewayLLMWorker],
        mocker: MockerFixture,
    ) -> None:
        """A genuine unknown-model 404 (no propagation-race phrase) stays a non-retryable LLMModelNotFoundError."""
        worker = _make_gateway_worker(worker_class, mocker)
        sdk_exc = _openai_not_found("Error code: 404 - the model gpt-99 does not exist")

        result = worker._classify_sdk_error(sdk_exc=sdk_exc)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert isinstance(result, LLMModelNotFoundError)
        assert result.error_category is InferenceErrorCategory.CONFIGURATION
        assert result.error_category.is_retryable is False
        assert result.user_action is not None
        assert result.user_action.kind is UserActionKind.CHANGE_MODEL
        assert result.model_handle == "gpt-4o-handle"
