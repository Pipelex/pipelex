"""Tests for Gateway search worker provider_metadata + semantic UserActionKind."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from portkey_ai.api_resources import exceptions as portkey_exc

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.gateway.gateway_exceptions import GatewaySearchResponseError
from pipelex.plugins.gateway.gateway_search_worker import GatewaySearchWorker


def _make_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://api.portkey.ai/v1/chat/completions")
    return httpx.Response(status_code=status_code, request=request, headers={"x-request-id": "pk-search-1"})


def _make_status_error(exc_cls: type[portkey_exc.APIStatusError], status_code: int) -> portkey_exc.APIStatusError:
    request = httpx.Request("POST", "https://api.portkey.ai/v1/chat/completions")
    response = _make_response(status_code)
    return exc_cls(message=f"http {status_code}", request=request, response=response, body={})


def _make_worker(mocker: MockerFixture) -> GatewaySearchWorker:
    worker = object.__new__(GatewaySearchWorker)
    mock_model = mocker.MagicMock()
    mock_model.model_id = "linkup/standard"
    mock_model.name = "linkup-sourced-answer"
    mock_model.desc = "test-gateway-search"
    mock_model.extra_headers = {}
    worker.inference_model = mock_model

    mock_tenacity_cfg = mocker.MagicMock()
    mock_tenacity_cfg.wait_multiplier = 0.0
    mock_tenacity_cfg.wait_max = 0.0
    mock_tenacity_cfg.wait_exp_base = 1.0
    mock_tenacity_cfg.max_retries = 1
    worker._tenacity_config = mock_tenacity_cfg  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    mock_post = mocker.AsyncMock()
    mock_options = mocker.MagicMock()
    mock_options.post = mock_post
    mock_client = mocker.MagicMock()
    mock_client.with_options.return_value = mock_options
    worker.portkey_client = mock_client
    return worker


def _make_search_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.query = "test search query"
    job.job_params.search_setting.include_images = False
    job.job_params.search_setting.include_inline_citations = False
    job.job_params.search_setting.max_results = 10
    job.job_params.include_domains = None
    job.job_params.exclude_domains = None
    job.job_params.from_date = None
    job.job_params.to_date = None
    job.job_report.search_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestGatewaySearchWorkerSemantic:
    """Each Portkey APIError branch carries semantic UserActionKind + provider_metadata."""

    @pytest.mark.parametrize(
        ("exc_cls", "status_code", "expected_category", "expected_kind"),
        [
            (portkey_exc.RateLimitError, 429, InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
            (portkey_exc.AuthenticationError, 401, InferenceErrorCategory.CONFIGURATION, UserActionKind.CHECK_CREDENTIALS),
            (portkey_exc.PermissionDeniedError, 403, InferenceErrorCategory.CONFIGURATION, UserActionKind.CHECK_CREDENTIALS),
            (portkey_exc.NotFoundError, 404, InferenceErrorCategory.CONFIGURATION, UserActionKind.CHANGE_MODEL),
            (portkey_exc.BadRequestError, 400, InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
        ],
    )
    async def test_status_error_carries_semantic_user_action(
        self,
        mocker: MockerFixture,
        exc_cls: type[portkey_exc.APIStatusError],
        status_code: int,
        expected_category: InferenceErrorCategory,
        expected_kind: UserActionKind,
    ) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_status_error(exc_cls, status_code)
        client: Any = worker.portkey_client
        client.with_options.return_value.post.side_effect = sdk_exc

        mocker.patch(
            "pipelex.plugins.gateway.gateway_search_worker.GatewayDeck.get_config_id",
            return_value="linkup-sourced-answer",
        )

        with pytest.raises(GatewaySearchResponseError) as exc_info:
            await worker._search_sourced_answer(search_job=_make_search_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is expected_kind
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.provider == "gateway"
        assert exc_info.value.provider_metadata.status_code == status_code
        assert exc_info.value.provider_metadata.request_id == "pk-search-1"
        assert exc_info.value.__cause__ is sdk_exc
