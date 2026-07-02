"""Tests that img2img (input images present) calls route to /images/edits, not /images/generations.

Azure/OpenAI's Images API splits generation and editing across two REST routes, and only
/images/edits accepts the 'image' parameter — /images/generations rejects it with a 400
"Unknown parameter". The args factory maps input images to httpx-style file tuples under
"image"; the worker must send them as a multipart body with every scalar arg as a
(None, value) file part (any JSON body is dropped once 'files' is set), and it must route
that one call through a sync Portkey client because portkey_ai's AsyncAPIClient never
forwards 'files' to httpx.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

import pytest
from portkey_ai.api_resources.utils import GenericResponse

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.plugins.gateway.gateway_img_gen_worker import GatewayImgGenWorker

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
_PNG_FILE_TUPLE = ("image_0.png", _PNG_BYTES, "image/png")
_PNG_FILE_TUPLE_2 = ("image_1.png", _PNG_BYTES, "image/png")

# Production gateway config style: the explicit endpoint_path key on the model spec,
# with no leading slash (httpx's base_url merge makes the two forms equivalent).
_GENERATIONS_ENDPOINT_PATH = "openai/deployments/gpt-image-1-2025-04-15/images/generations?api-version=2025-04-01-preview"
_EDITS_ENDPOINT_PATH = "openai/deployments/gpt-image-1-2025-04-15/images/edits?api-version=2025-04-01-preview"


def _make_worker(mocker: MockerFixture, *, endpoint_path: str = _GENERATIONS_ENDPOINT_PATH) -> tuple[GatewayImgGenWorker, Any]:
    worker = object.__new__(GatewayImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.model_id = "gpt-image-1"
    mock_model.name = "gpt-image-1"
    mock_model.desc = "test-gateway-img-model"
    mock_model.extra_headers = {"endpoint_path": endpoint_path}
    mock_model.rules = mocker.MagicMock()
    worker.inference_model = mock_model

    mock_post = mocker.AsyncMock()
    mock_options = mocker.MagicMock()
    mock_options.post = mock_post
    mock_client = mocker.MagicMock()
    mock_client.with_options.return_value = mock_options
    mock_client.base_url = "https://gateway.example.com/v1"
    mock_client.api_key = "test-api-key"
    mock_client.debug = False
    worker.portkey_client = mock_client
    return worker, mock_post


def _patch_sync_portkey(mocker: MockerFixture) -> tuple[Any, Any]:
    """Patch the sync Portkey class the edit branch instantiates; return (class mock, its post mock)."""
    mock_portkey_cls = mocker.patch("pipelex.plugins.gateway.gateway_img_gen_worker.Portkey")
    mock_sync_post = mock_portkey_cls.return_value.with_options.return_value.post
    return mock_portkey_cls, mock_sync_post


def _make_img_gen_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.img_gen_prompt.positive_text = "test prompt"
    job.job_report.img_gen_tokens_usage = None
    return job


def _patch_args(mocker: MockerFixture, *, args_dict: dict[str, Any]) -> None:
    mocker.patch(
        "pipelex.plugins.gateway.gateway_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
        new_callable=mocker.AsyncMock,
        return_value=args_dict,
    )
    mocker.patch(
        "pipelex.plugins.gateway.gateway_img_gen_worker.GatewayDeck.get_config_id",
        return_value="cfg-1",
    )


def _make_success_response() -> GenericResponse:
    b64_json = base64.b64encode(_PNG_BYTES).decode("ascii")
    return GenericResponse.model_validate({"data": [{"b64_json": b64_json}], "output_format": "png", "size": "1024x1024"})


@pytest.mark.asyncio(loop_scope="class")
class TestGatewayImgGenWorkerEditRouting:
    """When 'image' is present in args_dict, the worker must post to /images/edits with a multipart body via the sync client."""

    async def test_with_input_image_routes_to_edits_with_multipart_fields(self, mocker: MockerFixture) -> None:
        worker, mock_async_post = _make_worker(mocker)
        mock_portkey_cls, mock_sync_post = _patch_sync_portkey(mocker)
        mock_sync_post.return_value = _make_success_response()
        _patch_args(mocker, args_dict={"prompt": "edit me", "n": 1, "size": "1024x1024", "image": [_PNG_FILE_TUPLE]})

        await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        # The edit call goes through a throwaway sync client built from the async client's credentials
        # (portkey_ai's AsyncAPIClient silently drops 'files'); the async client must not be posted to.
        mock_async_post.assert_not_called()
        sync_client_kwargs = mock_portkey_cls.call_args.kwargs
        assert sync_client_kwargs["base_url"] == "https://gateway.example.com/v1"
        assert sync_client_kwargs["api_key"] == "test-api-key"

        call_kwargs = mock_sync_post.call_args.kwargs
        assert call_kwargs["url"] == _EDITS_ENDPOINT_PATH
        assert "prompt" not in call_kwargs
        assert "image" not in call_kwargs

        files: dict[str, Any] = dict(call_kwargs["files"])
        assert files["prompt"] == (None, "edit me")
        assert files["n"] == (None, "1")
        assert files["size"] == (None, "1024x1024")
        assert files["image"] == _PNG_FILE_TUPLE

    async def test_with_multiple_input_images_sends_bracketed_array_field_name(self, mocker: MockerFixture) -> None:
        """Multiple input images must travel as 'image[]' parts (OpenAI multipart array convention);
        repeated bare 'image' parts are collapsed to one by the server, silently dropping the others.
        """
        worker, mock_async_post = _make_worker(mocker)
        _, mock_sync_post = _patch_sync_portkey(mocker)
        mock_sync_post.return_value = _make_success_response()
        _patch_args(mocker, args_dict={"prompt": "edit me", "image": [_PNG_FILE_TUPLE, _PNG_FILE_TUPLE_2]})

        await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        mock_async_post.assert_not_called()
        multipart_fields: list[tuple[str, Any]] = mock_sync_post.call_args.kwargs["files"]
        image_parts = [field for field in multipart_fields if field[0] == "image[]"]
        assert image_parts == [("image[]", _PNG_FILE_TUPLE), ("image[]", _PNG_FILE_TUPLE_2)]
        assert all(field[0] != "image" for field in multipart_fields)
        assert ("prompt", (None, "edit me")) in multipart_fields

    async def test_without_input_image_routes_to_generations_as_before(self, mocker: MockerFixture) -> None:
        worker, mock_async_post = _make_worker(mocker)
        mock_portkey_cls, _ = _patch_sync_portkey(mocker)
        mock_async_post.return_value = _make_success_response()
        _patch_args(mocker, args_dict={"prompt": "generate me", "n": 1})

        await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        mock_portkey_cls.assert_not_called()
        call_kwargs = mock_async_post.call_args.kwargs
        assert call_kwargs["url"] == _GENERATIONS_ENDPOINT_PATH
        assert "files" not in call_kwargs
        assert call_kwargs["prompt"] == "generate me"
        assert call_kwargs["n"] == 1

    async def test_with_input_image_but_no_generations_segment_raises(self, mocker: MockerFixture) -> None:
        """A model whose endpoint doesn't follow the generations/edits split must fail loud, not silently mis-route."""
        worker, _ = _make_worker(mocker, endpoint_path="/some/other/route")
        _patch_args(mocker, args_dict={"prompt": "edit me", "image": [_PNG_FILE_TUPLE]})

        with pytest.raises(ImgGenParameterError):
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
