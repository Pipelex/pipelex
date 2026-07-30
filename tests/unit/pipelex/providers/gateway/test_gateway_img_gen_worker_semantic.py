"""Tests for Gateway ImgGen worker provider_metadata + semantic UserActionKind."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from portkey_ai.api_resources import exceptions as portkey_exc

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenModelNotFoundError, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.providers.gateway.gateway_img_gen_worker import GatewayImgGenWorker


def _make_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://api.portkey.ai/v1/images/generations")
    return httpx.Response(status_code=status_code, request=request, headers={"x-request-id": "pk-1"})


def _make_status_error(exc_cls: type[portkey_exc.APIStatusError], status_code: int, body: dict[str, Any] | None = None) -> portkey_exc.APIStatusError:
    request = httpx.Request("POST", "https://api.portkey.ai/v1/images/generations")
    response = _make_response(status_code)
    return exc_cls(message=f"http {status_code}", request=request, response=response, body=body or {})


def _make_worker(mocker: MockerFixture) -> GatewayImgGenWorker:
    worker = object.__new__(GatewayImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.model_id = "gpt-image-1"
    mock_model.name = "gpt-image-1"
    mock_model.desc = "test-gateway-img-model"
    mock_model.extra_headers = {"endpoint_path": "/gpt-image-1"}
    mock_model.rules = mocker.MagicMock()
    worker.inference_model = mock_model

    mock_post = mocker.AsyncMock()
    mock_options = mocker.MagicMock()
    mock_options.post = mock_post
    mock_client = mocker.MagicMock()
    mock_client.with_options.return_value = mock_options
    worker.portkey_client = mock_client
    return worker


def _make_img_gen_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.img_gen_prompt.positive_text = "test prompt"
    job.job_report.img_gen_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestGatewayImgGenWorkerSemantic:
    """Each Portkey APIError branch carries semantic UserActionKind + provider_metadata."""

    @pytest.mark.parametrize(
        ("exc_cls", "status_code", "expected_category", "expected_kind"),
        [
            (portkey_exc.RateLimitError, 429, InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
            (portkey_exc.AuthenticationError, 401, InferenceErrorCategory.CONFIGURATION, UserActionKind.CHECK_CREDENTIALS),
            (portkey_exc.PermissionDeniedError, 403, InferenceErrorCategory.CONFIGURATION, UserActionKind.CHECK_CREDENTIALS),
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
        worker.portkey_client.with_options.return_value.post.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.providers.gateway.gateway_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )
        mocker.patch(
            "pipelex.providers.gateway.gateway_img_gen_worker.GatewayDeck.get_config_id",
            return_value="cfg-1",
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is expected_kind
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.provider == "gateway"
        assert exc_info.value.provider_metadata.status_code == status_code

    async def test_genuine_not_found_404_raises_img_gen_model_not_found_error(self, mocker: MockerFixture) -> None:
        """A genuine unknown-model 404 specializes to ImgGenModelNotFoundError (CONFIGURATION, CHANGE_MODEL)."""
        worker = _make_worker(mocker)
        sdk_exc = _make_status_error(portkey_exc.NotFoundError, 404)
        worker.portkey_client.with_options.return_value.post.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.providers.gateway.gateway_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )
        mocker.patch(
            "pipelex.providers.gateway.gateway_img_gen_worker.GatewayDeck.get_config_id",
            return_value="cfg-1",
        )

        with pytest.raises(ImgGenModelNotFoundError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        assert exc_info.value.model_handle == "gpt-image-1"
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 404

    async def test_quota_keywords_in_rate_limit_message_is_check_billing(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        # The classify path inspects str(exc); the constructor message becomes the str repr.
        request = httpx.Request("POST", "https://api.portkey.ai/v1/images/generations")
        response = _make_response(429)
        sdk_exc = portkey_exc.RateLimitError(
            message="insufficient_quota: your credits are exhausted",
            request=request,
            response=response,
            body={"error": {"message": "insufficient_quota: your credits are exhausted"}},
        )
        worker.portkey_client.with_options.return_value.post.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.providers.gateway.gateway_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )
        mocker.patch(
            "pipelex.providers.gateway.gateway_img_gen_worker.GatewayDeck.get_config_id",
            return_value="cfg-1",
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CAPACITY
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_BILLING
