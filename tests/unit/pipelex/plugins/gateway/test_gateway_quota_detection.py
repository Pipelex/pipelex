"""Tests for Gateway worker Portkey error classification and quota detection."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
from portkey_ai.api_resources import exceptions as portkey_exceptions

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ExtractJobFailureError, ImgGenGenerationError, InferenceErrorCategory, SearchJobFailureError
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.gateway.gateway_extract_worker import GatewayExtractWorker
from pipelex.plugins.gateway.gateway_factory import GatewayFactory
from pipelex.plugins.gateway.gateway_img_gen_worker import GatewayImgGenWorker
from pipelex.plugins.gateway.gateway_protocols import GatewayExtractProtocol
from pipelex.plugins.gateway.gateway_search_worker import GatewaySearchWorker
from tests.unit.pipelex.plugins.gateway.test_data import GatewayQuotaDetectionTestData


def _make_portkey_exception(exception_type_name: str, status_code: int, message: str) -> portkey_exceptions.APIError:
    """Create a Portkey exception by type name for testing."""
    request = httpx.Request("POST", "https://api.portkey.ai/v1/test")
    response = httpx.Response(status_code=status_code, request=request)

    exception_map: dict[str, type[portkey_exceptions.APIError]] = {
        "RateLimitError": portkey_exceptions.RateLimitError,
        "AuthenticationError": portkey_exceptions.AuthenticationError,
        "PermissionDeniedError": portkey_exceptions.PermissionDeniedError,
        "BadRequestError": portkey_exceptions.BadRequestError,
        "NotFoundError": portkey_exceptions.NotFoundError,
        "APIStatusError": portkey_exceptions.APIStatusError,
    }

    if exception_type_name == "APITimeoutError":
        return portkey_exceptions.APITimeoutError(request=request)
    if exception_type_name == "APIConnectionError":
        return portkey_exceptions.APIConnectionError(message=message, request=request)

    exc_class = exception_map.get(exception_type_name)
    if exc_class is None:
        msg = f"Unknown portkey exception type: {exception_type_name}"
        raise ValueError(msg)
    return exc_class(message, request=request, response=response, body=None)  # type: ignore[call-arg]  # pyright: ignore[reportCallIssue]


def _make_gateway_extract_worker(mocker: MockerFixture) -> GatewayExtractWorker:
    """Create a minimal GatewayExtractWorker with mocked internals."""
    worker = object.__new__(GatewayExtractWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-gateway-extract"
    mock_model.model_id = "mistral-doc-ai"
    mock_model.name = "mistral-doc-ai"
    mock_model.tag = "test-extract-tag"
    mock_model.extra_headers = {}
    worker.inference_model = mock_model

    mock_client = mocker.MagicMock()
    worker.portkey_client = mock_client

    return worker


def _make_gateway_img_gen_worker(mocker: MockerFixture) -> GatewayImgGenWorker:
    """Create a minimal GatewayImgGenWorker with mocked internals."""
    worker = object.__new__(GatewayImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-gateway-imggen"
    mock_model.model_id = "gpt-image-1"
    mock_model.name = "gpt-image-1"
    mock_model.tag = "test-imggen-tag"
    mock_model.extra_headers = {}
    mock_model.rules = mocker.MagicMock()
    worker.inference_model = mock_model

    mock_client = mocker.MagicMock()
    worker.portkey_client = mock_client

    return worker


def _make_gateway_search_worker(mocker: MockerFixture) -> GatewaySearchWorker:
    """Create a minimal GatewaySearchWorker with mocked internals."""
    worker = object.__new__(GatewaySearchWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-gateway-search"
    mock_model.model_id = "linkup/standard"
    mock_model.name = "linkup-standard"
    mock_model.tag = "test-search-tag"
    mock_model.extra_headers = {}
    worker.inference_model = mock_model

    mock_client = mocker.MagicMock()
    worker.portkey_client = mock_client

    return worker


@pytest.mark.asyncio(loop_scope="class")
class TestGatewayQuotaDetection:
    """Tests for Portkey error classification across gateway workers."""

    # ---- Classification method tests (direct unit tests) ----

    @pytest.mark.parametrize(
        ("_topic", "exception_type_name", "status_code", "error_message", "expected_category"),
        GatewayQuotaDetectionTestData.CLASSIFY_CASES,
    )
    async def test_classify_error_category(
        self,
        _topic: str,
        exception_type_name: str,
        status_code: int,
        error_message: str,
        expected_category: InferenceErrorCategory,
    ) -> None:
        """GatewayFactory.classify_error_category returns correct category for Portkey errors."""
        exc = _make_portkey_exception(exception_type_name, status_code, error_message)

        result = GatewayFactory.classify_error_category(exc)

        assert result is expected_category

    async def test_classify_unhandled_4xx_status_error_is_configuration(self) -> None:
        """A generic 4xx APIStatusError is non-retryable CONFIGURATION, not TRANSIENT."""
        exc = _make_portkey_exception("APIStatusError", 409, "Conflict")

        assert GatewayFactory.classify_error_category(exc) is InferenceErrorCategory.CONFIGURATION

    async def test_user_action_for_unhandled_4xx_is_change_input(self) -> None:
        """A generic 4xx APIStatusError yields a corrective CHANGE_INPUT action, not WAIT_AND_RETRY."""
        exc = _make_portkey_exception("APIStatusError", 409, "Conflict")

        action = GatewayFactory.make_user_action_from_portkey_error(exc)

        assert action.kind is UserActionKind.CHANGE_INPUT

    # ---- Full flow tests: verify the exception propagates with category ----

    async def test_imggen_worker_propagates_rate_limit_as_transient(self, mocker: MockerFixture) -> None:
        """GatewayImgGenWorker raises ImgGenGenerationError with TRANSIENT for rate limit."""
        worker = _make_gateway_img_gen_worker(mocker)
        sdk_exc = _make_portkey_exception("RateLimitError", 429, "Rate limit exceeded")

        mock_options = mocker.MagicMock()
        mock_options.post = mocker.AsyncMock(side_effect=sdk_exc)
        worker.portkey_client.with_options = mocker.MagicMock(return_value=mock_options)  # type: ignore[method-assign]

        mocker.patch(
            "pipelex.plugins.gateway.gateway_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )
        mocker.patch(
            "pipelex.plugins.gateway.gateway_img_gen_worker.GatewayDeck.get_config_id",
            return_value="test-config",
        )

        img_gen_job = mocker.MagicMock()
        img_gen_job.job_report.img_gen_tokens_usage = None

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=img_gen_job, nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.__cause__ is sdk_exc

    async def test_search_worker_propagates_auth_error_as_configuration(self, mocker: MockerFixture) -> None:
        """GatewaySearchWorker raises SearchJobFailureError with CONFIGURATION for auth error."""
        worker = _make_gateway_search_worker(mocker)
        sdk_exc = _make_portkey_exception("AuthenticationError", 401, "Invalid API key")

        mock_options = mocker.MagicMock()
        mock_options.post = mocker.AsyncMock(side_effect=sdk_exc)
        worker.portkey_client.with_options = mocker.MagicMock(return_value=mock_options)  # type: ignore[method-assign]

        mocker.patch(
            "pipelex.plugins.gateway.gateway_search_worker.GatewayDeck.get_config_id",
            return_value="test-config",
        )

        with pytest.raises(SearchJobFailureError) as exc_info:
            await worker._call_relay(model="linkup/standard", content='{"query": "test"}')  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.__cause__ is sdk_exc

    async def test_extract_worker_propagates_quota_as_capacity(self, mocker: MockerFixture) -> None:
        """GatewayExtractWorker raises ExtractJobFailureError with CAPACITY for quota exhaustion."""
        worker = _make_gateway_extract_worker(mocker)
        sdk_exc = _make_portkey_exception("RateLimitError", 429, "You have exceeded your quota allocation")

        mock_options = mocker.MagicMock()
        mock_options.post = mocker.AsyncMock(side_effect=sdk_exc)
        worker.portkey_client.with_options = mocker.MagicMock(return_value=mock_options)  # type: ignore[method-assign]

        mocker.patch(
            "pipelex.plugins.gateway.gateway_extract_worker.GatewayDeck.get_config_id",
            return_value="test-config",
        )
        mocker.patch(
            "pipelex.plugins.gateway.gateway_extract_worker.GatewayFactory.make_error_summary_from_portkey_error",
            return_value="Quota exhausted",
        )
        mocker.patch(
            "pipelex.plugins.gateway.gateway_extract_worker.GatewayFactory.make_extras",
            return_value=({}, {"messages": [{"role": "user", "content": "test"}]}),
        )
        mocker.patch(
            "pipelex.plugins.gateway.gateway_extract_worker.make_base64_url_from_any_uri",
            new_callable=mocker.AsyncMock,
            return_value="data:application/pdf;base64,dGVzdA==",
        )

        extract_job = mocker.MagicMock()
        extract_job.extract_input.image_uri = None
        extract_job.extract_input.document_uri = "/tmp/test.pdf"  # noqa: S108
        extract_job.job_params.max_nb_images = 0
        extract_job.job_params.should_caption_images = False

        mocker.patch(
            "pipelex.plugins.gateway.gateway_extract_worker.GatewayExtractProtocol.make_from_model_handle",
            return_value=GatewayExtractProtocol.MISTRAL_DOC_AI,
        )
        mocker.patch(
            "pipelex.plugins.gateway.gateway_extract_worker.get_storage_provider",
        )

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_document(extract_job=extract_job)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CAPACITY
        assert exc_info.value.__cause__ is sdk_exc
