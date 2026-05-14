"""Tests for Gateway extract worker provider_metadata + semantic UserActionKind."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from portkey_ai.api_resources import exceptions as portkey_exc

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ExtractJobFailureError, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.gateway.gateway_extract_worker import GatewayExtractWorker


def _make_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://api.portkey.ai/v1/chat/completions")
    return httpx.Response(status_code=status_code, request=request, headers={"x-request-id": "pk-extract-1"})


def _make_status_error(exc_cls: type[portkey_exc.APIStatusError], status_code: int, body: dict[str, Any] | None = None) -> portkey_exc.APIStatusError:
    request = httpx.Request("POST", "https://api.portkey.ai/v1/chat/completions")
    response = _make_response(status_code)
    return exc_cls(message=f"http {status_code}", request=request, response=response, body=body or {})


def _make_worker(mocker: MockerFixture) -> GatewayExtractWorker:
    worker = object.__new__(GatewayExtractWorker)
    mock_model = mocker.MagicMock()
    mock_model.model_id = "azure/document-intel"
    mock_model.name = "azure-doc-intel"
    mock_model.tag = "azure-doc-intel"
    mock_model.desc = "test-gateway-extract"
    mock_model.extra_headers = {}
    mock_model.is_caption_supported_for_extract = False
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


def _make_extract_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.extract_input.document_uri = "https://example.com/page"
    job.extract_input.image_uri = None
    job.job_params.max_nb_images = None
    job.job_params.render_js = False
    job.job_params.include_raw_html = False
    job.job_params.should_caption_images = False
    job.job_report.extract_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestGatewayExtractWorkerSemantic:
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
    async def test_status_error_carries_semantic_user_action_via_web_fetch(
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
            "pipelex.plugins.gateway.gateway_extract_worker.GatewayDeck.get_config_id",
            return_value="linkup-fetch",
        )
        mocker.patch(
            "pipelex.plugins.gateway.gateway_extract_worker.GatewayExtractProtocol.make_from_model_handle",
            return_value=mocker.MagicMock(),
        )

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_web_fetch(extract_job=_make_extract_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is expected_kind
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.provider == "gateway"
        assert exc_info.value.provider_metadata.status_code == status_code
        assert exc_info.value.provider_metadata.request_id == "pk-extract-1"
        assert exc_info.value.__cause__ is sdk_exc
